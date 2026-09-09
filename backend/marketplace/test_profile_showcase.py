from decimal import Decimal

from django.test import override_settings

from .auth_serializers import ProfileUpdateSerializer
from .models import Profile
from .tests import BaseTests


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ProfileShowcaseTests(BaseTests):
    def setUp(self):
        super().setUp()
        self.worker = self.account('showcase_worker', 'freelancer')
        self.as_user(self.worker)

    def update(self, data):
        return self.client.patch('/api/auth/me/', data, format='json')

    def test_saved_showcase_is_public_and_partial_updates_preserve_it(self):
        result = self.update({
            'professional_title': 'Frontend developer', 'location': 'Tashkent',
            'spoken_languages': ['English — B2', 'Русский — свободно'],
            'portfolio': [{'title': 'Marketplace', 'url': 'https://example.com/work'}],
            'services': [{'title': 'Landing page', 'price': '1500000.50', 'delivery_days': 7}],
        })
        self.assertEqual(result.status_code, 200, result.data)
        stale = Profile.objects.get(user=self.worker)
        form = ProfileUpdateSerializer(stale, data={'about': 'New biography'}, partial=True)
        self.assertTrue(form.is_valid(), form.errors)
        Profile.objects.filter(pk=stale.pk).update(balance=Decimal('450000'))
        form.save()
        stale.refresh_from_db()
        self.assertEqual(stale.balance, Decimal('450000'))
        self.as_user()
        public = self.client.get(f'/api/profiles/{stale.pk}/').data
        self.assertEqual(public['portfolio'][0]['title'], 'Marketplace')
        self.assertEqual(public['services'][0]['price'], '1500000.50')
        self.assertEqual(public['professional_title'], 'Frontend developer')
        self.assertEqual(public['location'], 'Tashkent')
        self.assertEqual(public['spoken_languages'], ['English — B2', 'Русский — свободно'])
        self.assertIsNone(public['on_time_percent'])
        self.assertNotIn('balance', public)

    def test_invalid_content_cannot_replace_existing_portfolio(self):
        self.assertEqual(self.update({'portfolio': [{'title': 'Original'}]}).status_code, 200)
        for data in [
            {'portfolio': [{'title': 'Bad', 'url': 'javascript:alert(1)'}]},
            {'portfolio': [{'title': 'Bad', 'url': 'ftp://example.com/work'}]},
            {'portfolio': [{'title': 'Bad', 'image': 'data:image/svg+xml;base64,abc'}]},
            {'portfolio': [{'title': 'Extra'}] * 10},
            {'services': [{'title': 'Bad', 'price': '-1', 'delivery_days': 1}]},
            {'services': [{'title': 'Bad', 'price': '1', 'delivery_days': 0}]},
            {'services': [{'title': 'Bad', 'price': '1', 'delivery_days': 366}]},
            {'services': [{'title': 'Extra', 'price': '1', 'delivery_days': 1}] * 7},
            {'spoken_languages': ['English'] * 11},
            {'spoken_languages': ['a' * 81]},
        ]:
            with self.subTest(data=data):
                self.assertEqual(self.update(data).status_code, 400)
        self.worker.profile.refresh_from_db()
        self.assertEqual(self.worker.profile.portfolio[0]['title'], 'Original')

    def test_only_owner_can_edit_and_lists_can_be_cleared(self):
        self.assertEqual(self.update({'portfolio': [{'title': 'Original'}]}).status_code, 200)
        outsider = self.account('showcase_other', 'freelancer')
        self.as_user(outsider)
        response = self.client.patch(f'/api/profiles/{self.worker.profile.pk}/', {'portfolio': []}, format='json')
        self.assertEqual(response.status_code, 405)
        self.worker.profile.refresh_from_db()
        self.assertEqual(len(self.worker.profile.portfolio), 1)
        self.as_user(self.worker)
        self.assertEqual(self.update({'portfolio': [], 'services': []}).status_code, 200)
        self.worker.profile.refresh_from_db()
        self.assertEqual(self.worker.profile.portfolio, [])
