import io
from django.core.management import call_command
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class CatalogMigrationTests(TransactionTestCase):
    def test_legacy_categories_normalized_duplicates_and_ids_survive(self):
        old=[('marketplace','0008_clickfiscalreceipt')]
        executor=MigrationExecutor(connection)
        new=executor.loader.graph.leaf_nodes('marketplace')
        executor.migrate(old)
        apps=executor.loader.project_state(old).apps
        Project=apps.get_model('marketplace','Project')
        Skill=apps.get_model('marketplace','Skill')
        Category=apps.get_model('marketplace','Category')
        Category.objects.get_or_create(slug='other',defaults={'name':'Другое'})
        original=Skill.objects.get_or_create(name='React')[0]
        duplicate=Skill.objects.create(name='  REACT ')
        synonym=Skill.objects.create(name='ReactJS')
        project=Project.objects.create(title='Legacy project',description='Preserve',category='unmapped-old',budget_min=100,budget_max=200)
        project.skills.add(duplicate,synonym)
        ids=(original.pk,duplicate.pk,synonym.pk,project.pk)
        try:
            executor=MigrationExecutor(connection);executor.migrate(new)
            from .models import AuditLog, Category as CurrentCategory, Project as CurrentProject, Skill as CurrentSkill
            restored=CurrentProject.objects.get(pk=ids[3])
            self.assertEqual(restored.category.slug,'unmapped-old')
            self.assertEqual(restored.legacy_category,'unmapped-old')
            self.assertFalse(restored.category.active)
            self.assertTrue(AuditLog.objects.filter(action='legacy_category_review').exists())
            self.assertEqual(CurrentSkill.objects.get(pk=ids[1]).merged_into_id,ids[0])
            self.assertEqual(restored.skills.count(),2)
            call_command('seed_catalog','--apply',stdout=io.StringIO())
            self.assertEqual(CurrentSkill.objects.get(pk=ids[2]).merged_into_id,ids[0])
            self.assertEqual(list(restored.skills.values_list('pk',flat=True)),[ids[0]])
            self.assertTrue(CurrentCategory.objects.filter(slug='unmapped-old').exists())
        finally:
            MigrationExecutor(connection).migrate(new)
