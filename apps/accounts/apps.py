from django.apps import AppConfig


def ensure_deployment_accounts(sender, **kwargs):
    from decouple import config
    from .default_users import DEFAULT_USERS, ensure_default_users

    if all(config(item['env'], default='') for item in DEFAULT_USERS):
        ensure_default_users()


class AccountsConfig (AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'apps.accounts'

    def ready(self):
        from django.db.models.signals import post_migrate
        post_migrate.connect(
            ensure_deployment_accounts,
            sender=self,
            dispatch_uid='accounts.ensure_deployment_accounts',
        )
