from django.core.management.base import BaseCommand

from marketplace.models import Project, Skill
from django.db import transaction


PROJECTS = [
    {
        "title": "Лендинг для нового финтех-продукта",
        "description": "Ищем разработчика, который соберёт быстрый адаптивный лендинг по готовому дизайну и подключит форму заявки.",
        "category": Project.Category.DEVELOPMENT,
        "budget_min": 1200,
        "budget_max": 1800,
        "skills": ["React", "Next.js", "Tailwind"],
        "client_name": "Алексей Морозов",
        "client_company": "NorthPay",
        "featured": True,
    },
    {
        "title": "Айдентика для кофейного бренда",
        "description": "Нужны логотип, базовая система упаковки и компактный брендбук для сети кофеен нового формата.",
        "category": Project.Category.DESIGN,
        "budget_min": 850,
        "budget_max": 1200,
        "skills": ["Figma", "Branding", "Illustrator"],
        "client_name": "Дарья Волкова",
        "client_company": "Soma Coffee",
    },
    {
        "title": "SEO-стратегия для SaaS-сервиса",
        "description": "Провести аудит, собрать семантическое ядро и подготовить дорожную карту роста на ближайшие шесть месяцев.",
        "category": Project.Category.MARKETING,
        "budget_min": 700,
        "budget_max": 950,
        "skills": ["SEO", "Analytics", "Strategy"],
        "client_name": "Михаил Ким",
        "client_company": "Flowdesk",
    },
]


class Command(BaseCommand):
    help = "Добавляет демонстрационные проекты Taskora без создания дублей."

    @transaction.atomic
    def handle(self, *args, **options):
        created_count = 0
        for data in PROJECTS:
            defaults = {key: value for key, value in data.items() if key != 'skills'}
            project, created = Project.objects.get_or_create(title=data["title"], defaults=defaults)
            if created:
                project.skills.set([Skill.objects.get_or_create(name=name)[0] for name in data['skills']])
            created_count += int(created)
        self.stdout.write(self.style.SUCCESS(f"Создано проектов: {created_count}"))
