from django.apps import AppConfig


class AppConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'juke_auth'

    def ready(self):
        import juke_auth.signals  # noqa: F401
