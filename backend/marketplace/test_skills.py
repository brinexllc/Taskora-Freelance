from .tests import BaseTests
from .models import Profile, Project, Skill


class SkillDirectoryTests(BaseTests):
    def test_profile_relations_validation_and_search(self):
        user = self.account('skill_worker', 'freelancer')
        self.as_user(user)
        inactive = Skill.objects.create(name='Inactive skill', active=False)
        denied = self.client.patch('/api/auth/me/', {'skills': [inactive.name]}, format='json')
        self.assertEqual(denied.status_code, 400)
        self.assertEqual(user.profile.skills.count(), 0)
        Skill.objects.get_or_create(name='React Native')
        updated = self.client.patch('/api/auth/me/', {'skills': ['React', 'React Native', 'React']}, format='json')
        self.assertEqual(updated.status_code, 200, updated.data)
        self.assertCountEqual(updated.data['profile']['skills'], ['React', 'React Native'])
        self.assertEqual(Profile.objects.filter(skills__name='React', user=user).count(), 1)
        self.as_user()
        found = self.client.get('/api/profiles/', {'search': 'React'})
        self.assertEqual(found.status_code, 200, found.data)
        self.assertEqual(found.data['count'], 1)
        exact = self.client.get('/api/profiles/', {'skill': 'React Native'})
        self.assertEqual(exact.data['count'], 1)

    def test_project_relations_publication_and_skill_filter(self):
        user = self.account('skill_customer', 'client')
        self.as_user(user)
        payload = {'title': 'Directory project', 'description': 'Check relational skill filters',
                   'category': 'development', 'skills': ['React', 'Django'], 'deadline': '2099-01-01',
                   'budget_min': 1000, 'budget_max': 2000}
        self.assertEqual(self.post('projects', {**payload, 'skills': ['Unknown skill']}).status_code, 400)
        draft = self.post('projects', {**payload, 'skills': []})
        self.assertEqual(draft.status_code, 201)
        self.assertEqual(self.post(f"projects/{draft.data['id']}/publish").status_code, 400)
        created = self.post('projects', payload)
        self.assertEqual(created.status_code, 201, created.data)
        project = Project.objects.get(pk=created.data['id'])
        self.assertCountEqual(project.skills.values_list('name', flat=True), payload['skills'])
        self.assertEqual(self.post(f'projects/{project.pk}/publish').status_code, 200)
        self.as_user()
        found = self.client.get('/api/projects/', {'skill': 'React', 'search': 'Django'})
        self.assertEqual(found.status_code, 200, found.data)
        self.assertEqual(found.data['count'], 1)
        self.assertEqual(found.data['results'][0]['proposal_count'], 0)
