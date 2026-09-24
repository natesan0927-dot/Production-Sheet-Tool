"""Create the real staff accounts. Safe to run more than once.

    python manage.py seed_employees

Everyone starts on the shared default password and is made to choose their own
at first sign-in. Running it again leaves existing people exactly as they are —
it only fills in anyone missing, so it never resets a password someone has set.
"""

from django.core.management.base import BaseCommand

from apps.accounts.forms import DEFAULT_PASSWORD
from apps.accounts.models import Role, User

# (sign-in name, first name, last name, role)
STAFF = [
    ("rahul", "Rahul", "", Role.SALESPERSON),
    ("natesan", "Natesan", "", Role.SALESPERSON),
    ("prema", "Prema", "", Role.SALESPERSON),
    ("balasubramaniam", "Balasubramaniam", "", Role.SALESPERSON),
    ("sowmiya", "Sowmiya", "", Role.SALESPERSON),
    ("yogesh", "Yogesh", "", Role.MEASUREMENT),
    ("venkatesan", "Venkatesan", "", Role.MEASUREMENT),
    # No names were given for these, so each role gets one account to start with.
    ("quotation", "Quotation", "Staff", Role.QUOTATION),
    ("production", "Production", "Staff", Role.PRODUCTION),
    ("fieldmanager", "Field", "Manager", Role.FIELD_MANAGER),
    ("accounts", "Accounts", "Team", Role.ACCOUNTS),
    ("admin", "Titans", "Admin", Role.SUPER_ADMIN),
]


class Command(BaseCommand):
    help = "Create the Titans Windows staff accounts on the default password."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset-passwords",
            action="store_true",
            help="Also put everyone listed back on the default password.",
        )

    def handle(self, *args, **options):
        created = 0
        for username, first, last, role in STAFF:
            person, is_new = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role},
            )
            if is_new or options["reset_passwords"]:
                person.first_name, person.last_name, person.role = first, last, role
                person.is_active = True
                person.set_password(DEFAULT_PASSWORD)
                person.must_change_password = True
                if role == Role.SUPER_ADMIN:
                    person.is_staff = person.is_superuser = True
                person.save()
                created += is_new
                self.stdout.write(f"{'created' if is_new else 'reset '} {username:<16} {person.get_role_display()}")
            else:
                self.stdout.write(f"kept    {username:<16} {person.get_role_display()}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\n{created} new account(s). Everyone new signs in with the password "
                f"{DEFAULT_PASSWORD} and is asked to change it."
            )
        )
