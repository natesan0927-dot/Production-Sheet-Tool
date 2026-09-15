from django.apps import AppConfig


class AftersalesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.aftersales"

    def ready(self):
        from apps.aftersales import exports  # noqa: F401
