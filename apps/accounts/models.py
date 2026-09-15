from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models

mobile_validator = RegexValidator(r"^\+?\d{7,15}$", "Enter a valid mobile number.")


class Department(models.Model):
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class User(AbstractUser):
    """
    Employee account. Every employee has an Employee ID, username, password,
    name, mobile, email, department, designation, role (Django Group) and an
    active/inactive status (AbstractUser.is_active).
    """

    employee_id = models.CharField(max_length=20, unique=True, blank=True, null=True)
    mobile = models.CharField(max_length=20, blank=True, validators=[mobile_validator])
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name="employees")
    designation = models.CharField(max_length=100, blank=True)
    photo = models.ImageField(upload_to="employees/", blank=True, null=True)

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        full = self.get_full_name()
        return full if full else self.username

    @property
    def role_names(self):
        return list(self.groups.values_list("name", flat=True))

    def has_role(self, *names):
        if self.is_superuser:
            return True
        return self.groups.filter(name__in=names).exists()
