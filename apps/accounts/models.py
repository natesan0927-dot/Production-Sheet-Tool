from django.contrib.auth.models import AbstractUser
from django.db import models


class Role(models.TextChoices):
    SALESPERSON = "salesperson", "Sales Executive"
    MEASUREMENT = "measurement", "Measurement Staff"
    QUOTATION = "quotation", "Quotation Staff"
    ACCOUNTS = "accounts", "Accounts Department"
    PRODUCTION = "production", "Production Staff"
    FIELD_MANAGER = "field_manager", "Field Manager"
    SUPER_ADMIN = "super_admin", "Super Admin"


class User(AbstractUser):
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.SALESPERSON)
    phone = models.CharField(max_length=20, blank=True)
    # Empty means "use whatever this role sees by default"; the Super Admin can
    # override it per employee from Settings → Stage Access.
    visible_stages = models.JSONField(default=list, blank=True)

    # The walkthrough plays once, on the first sign-in. Both are set whether the
    # person watched it or skipped it; the Guide tab replays it on demand.
    intro_seen_at = models.DateTimeField(null=True, blank=True)
    tour_seen_at = models.DateTimeField(null=True, blank=True)

    # A new account starts on the shared default password and cannot get past
    # the change-password screen until it has picked one of its own.
    must_change_password = models.BooleanField(default=False)

    class Meta:
        ordering = ["first_name", "username"]

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_super_admin(self):
        return self.role == Role.SUPER_ADMIN

    def has_role(self, *roles):
        """Super Admin can reach every stage, so they match any role check."""
        return self.role == Role.SUPER_ADMIN or self.role in roles

    @property
    def display_name(self):
        return self.get_full_name() or self.username
