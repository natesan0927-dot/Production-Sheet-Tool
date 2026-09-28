from datetime import timedelta

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


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


class PasswordResetCode(models.Model):
    """A one-time code that lets someone who forgot their password choose a new one.

    Only a hash is kept, so reading the table does not hand out working codes.
    A code is short-lived, gives five tries, and is spent the moment it is used.
    """

    LIFETIME = timedelta(minutes=15)
    MAX_TRIES = 5
    MAX_PER_HOUR = 3

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="reset_codes")
    code_hash = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    tries = models.PositiveSmallIntegerField(default=0)
    used_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Reset code for {self.user.username} at {self.created_at:%d %b %H:%M}"

    @property
    def is_usable(self):
        return self.used_at is None and self.expires_at > timezone.now() and self.tries < self.MAX_TRIES
