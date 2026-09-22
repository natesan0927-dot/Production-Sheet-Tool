from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.crm.models import FollowUp, Lead, SalesTarget

PASSWORD = "Demo@123"

DEMO_USERS = [
    ("demo_sales1", "Arun", "Kumar", Role.SALESPERSON),
    ("demo_sales2", "Priya", "Raman", Role.SALESPERSON),
    ("demo_measure", "Vignesh", "S", Role.MEASUREMENT),
    ("demo_quotation", "Deepa", "R", Role.QUOTATION),
    ("demo_accounts", "Lakshmi", "N", Role.ACCOUNTS),
    ("demo_production", "Karthik", "M", Role.PRODUCTION),
    ("demo_field", "Suresh", "P", Role.FIELD_MANAGER),
    ("demo_admin", "Titans", "Admin", Role.SUPER_ADMIN),
]

DEMO_LEADS = [
    ("Ravi Shankar", "9840012345", "Anna Nagar, Chennai", "reference", 12, "450000", "brickwork"),
    ("Meena Krishnan", "9840067890", "Velachery, Chennai", "website", 8, "280000", "plastering"),
    ("Sandeep Rao", "9840055512", "Porur, Chennai", "walk_in", 20, "760000", "painting"),
    ("Fathima Begum", "9840033322", "Adyar, Chennai", "architect", 6, "195000", "foundation"),
]


class Command(BaseCommand):
    help = "Create the demo users and a few sample leads."

    def handle(self, *args, **options):
        for username, first, last, role in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={"first_name": first, "last_name": last, "role": role},
            )
            user.first_name, user.last_name, user.role = first, last, role
            if role == Role.SUPER_ADMIN:
                user.is_staff = user.is_superuser = True
            user.set_password(PASSWORD)
            user.save()
            self.stdout.write(f"{'created' if created else 'updated'} {username} ({user.get_role_display()})")

        sales1 = User.objects.get(username="demo_sales1")
        sales2 = User.objects.get(username="demo_sales2")

        if not Lead.objects.exists():
            for index, (name, phone, location, source, qty, value, site_stage) in enumerate(DEMO_LEADS):
                lead = Lead.objects.create(
                    customer_name=name,
                    phone=phone,
                    site_location=location,
                    lead_source=source,
                    assigned_to=sales1 if index % 2 == 0 else sales2,
                    approx_quantity=qty,
                    expected_value=Decimal(value),
                    site_stage=site_stage,
                    created_by=sales1,
                )
                FollowUp.objects.create(
                    lead=lead,
                    date=timezone.localdate() + timedelta(days=index - 1),
                    note="Call the customer",
                    created_by=lead.assigned_to,
                )
            self.stdout.write(f"created {len(DEMO_LEADS)} sample leads")

        month = timezone.localdate().replace(day=1)
        for person in (sales1, sales2):
            SalesTarget.objects.get_or_create(
                salesperson=person, month=month, defaults={"amount": Decimal("1500000")}
            )

        self.stdout.write(self.style.SUCCESS(f"Demo data ready. Password for every demo account: {PASSWORD}"))
