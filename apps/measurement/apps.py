from django.apps import AppConfig


class MeasurementConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.measurement"

    def ready(self):
        from apps.measurement import exports  # noqa: F401
