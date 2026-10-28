from django.apps import AppConfig


class GamesConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'games'
    verbose_name = "Öyinlar"

    def ready(self):
        from . import prize_escrow  # noqa: F401 — pre_delete signalini röyxatdan ötkazadi
