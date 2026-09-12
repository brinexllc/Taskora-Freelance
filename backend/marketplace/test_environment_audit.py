from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from config.environment import boolean, validate_environment


class EnvironmentAuditTests(SimpleTestCase):
    def test_bool_typos_never_silently_disable_protection(self):
        for value in ['flase', 'enabled', '', '2']:
            with self.assertRaises(ImproperlyConfigured):
                boolean({'FLAG': value}, 'FLAG')
        self.assertFalse(boolean({}, 'FLAG'))

    def test_production_requires_each_setting_and_never_debugs_by_default(self):
        valid = {'TASKORA_ENV': 'production', 'DJANGO_SECRET_KEY': 'test-only-strong-key-'+'x'*60,
                 'DATABASE_URL': 'postgresql://local-test@db.example.test/app',
                 'DJANGO_ALLOWED_HOSTS': 'api.example.test', 'FRONTEND_URL': 'https://app.example.test',
                 'PUBLIC_API_URL': 'https://api.example.test/api', 'CORS_ALLOWED_ORIGINS': 'https://app.example.test',
                 'CSRF_TRUSTED_ORIGINS': 'https://app.example.test', 'PRIVATE_MEDIA_ROOT': '/private/volume'}
        self.assertEqual(validate_environment(valid), 'production')
        for key in valid:
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                validate_environment({k: v for k,v in valid.items() if k != key})
        for key,value in [('DJANGO_DEBUG','true'), ('DATABASE_URL','sqlite:///tmp/file'), ('DJANGO_ALLOWED_HOSTS','*'),
                          ('PUBLIC_API_URL','http://localhost:8000/api'), ('CORS_ALLOW_ALL_ORIGINS','true')]:
            with self.subTest(key=key), self.assertRaises(ImproperlyConfigured):
                validate_environment({**valid, key:value})
        with self.assertRaises(ImproperlyConfigured):
            validate_environment({**valid, 'REAL_MONEY_ENABLED':'true', 'PAYME_TEST_MODE':'true'})
        self.assertEqual(validate_environment(valid, testing=True), 'test')
        self.assertEqual(validate_environment({}, testing=True), 'test')
        self.assertEqual(validate_environment({'TASKORA_ENV': 'local'}), 'local')
        with self.assertRaises(ImproperlyConfigured):
            validate_environment({})
