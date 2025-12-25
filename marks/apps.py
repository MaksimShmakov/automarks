from django.apps import AppConfig
from django.db.models.signals import post_migrate


def create_default_groups(sender, **kwargs):
                                                           
    from django.contrib.auth.models import Group
    groups = ["Администратор", "Маркетолог", "Аналитик"]
    for group_name in groups:
        Group.objects.get_or_create(name=group_name)


class MarksConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "marks"

    def ready(self):
        post_migrate.connect(create_default_groups, sender=self)
