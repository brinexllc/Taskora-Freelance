from django.apps import AppConfig


class MarketplaceConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marketplace"
    verbose_name = "Маркетплейс"

    def ready(self):
        from . import fees  # noqa: F401 — register configuration checks
        from . import security_signals  # noqa: F401 — invalidate changed contact evidence
