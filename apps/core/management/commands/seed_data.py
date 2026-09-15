from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.core.demo_data import DEMO_PASSWORD, DEMO_USERS
from apps.core.models import (
    AccessoryType, CompanyProfile, GlassType, HardwareType, InstallationChecklistItem, LeadSource, LeadStatus,
    LostReason, PaymentTermStep, PaymentTermTemplate, ProductionStageTemplate, ProfileSeries, QCChecklistItem,
    ServiceCategory,
)

ROLES = [
    "Super Admin", "Management", "Sales Manager", "Salesperson", "Measurement Staff", "Quotation Staff",
    "Admin Staff", "Production Manager", "Production Staff", "Quality Control", "Dispatch Staff",
    "Installation Team", "Service/Maintenance Staff",
]

LEAD_STATUSES = [
    ("New", False, False, True, "secondary"),
    ("Assigned", False, False, False, "info"),
    ("Contacted", False, False, False, "info"),
    ("Site Visit Required", False, False, False, "info"),
    ("Measurement Pending", False, False, False, "warning"),
    ("Measurement Completed", False, False, False, "warning"),
    ("Quotation Pending", False, False, False, "warning"),
    ("Quotation Sent", False, False, False, "primary"),
    ("Follow-up", False, False, False, "primary"),
    ("Negotiation", False, False, False, "primary"),
    ("Won", True, False, False, "success"),
    ("Lost", False, True, False, "danger"),
    ("On Hold", False, False, False, "dark"),
]

LEAD_SOURCES = [
    "Website", "Phone", "WhatsApp", "Instagram", "Facebook", "Google", "IndiaMART", "TradeIndia",
    "Justdial", "Referral", "Walk-in", "Architect", "Builder", "Existing Customer", "Other",
]

LOST_REASONS = ["Price too high", "Quality concerns", "Delivery timeline", "Design mismatch", "Relationship with competitor", "Other"]

PRODUCTION_STAGES = [
    "Production Planning", "Material Allocation", "Profile Cutting", "Steel Reinforcement", "Welding",
    "Cleaning", "Corner Finishing", "Machining", "Hardware Installation", "Glass Preparation",
    "Glass Installation", "Beading", "Final Assembly", "Quality Check", "Packing", "Ready for Dispatch",
]

QC_CHECKLIST = [
    "Dimensions", "Profile", "Colour", "Glass", "Hardware", "Handle", "Locking",
    "Welding Quality", "Surface Finish", "Glass Condition", "Accessories", "Quantity", "Overall Appearance",
]

INSTALLATION_CHECKLIST = [
    "Site readiness verified", "Frame alignment checked", "Sealant applied", "Hardware operation tested",
    "Mesh fitted", "Site cleaned up after installation", "Customer walkthrough completed",
]

SERVICE_CATEGORIES = ["General Service", "Hardware Repair", "Glass Replacement", "Sealant / Leakage", "Handle / Lock Repair", "Other"]

GLASS_TYPES = ["Single", "Double", "Toughened", "Laminated", "Clear", "Frosted", "Other"]
HARDWARE_TYPES = ["Handle", "Lock", "Hinge", "Roller", "Espagnolette", "Other"]
ACCESSORY_TYPES = ["Mesh", "Reinforcement", "Silicone", "Beading", "Coupler", "Connector", "Other"]


class Command(BaseCommand):
    help = "Seed default roles and configurable master data for Titans Windows CRM."

    def handle(self, *args, **options):
        company = CompanyProfile.load()
        if not company.logo:
            self._seed_logo(company)

        for name in ROLES:
            Group.objects.get_or_create(name=name)
        self.stdout.write(self.style.SUCCESS(f"Roles ready ({len(ROLES)})"))

        self._seed_demo_users()
        self._seed_superuser()

        for i, (name, is_won, is_lost, is_default, color) in enumerate(LEAD_STATUSES):
            LeadStatus.objects.get_or_create(
                name=name, defaults={"sequence": i, "is_won": is_won, "is_lost": is_lost, "is_default": is_default, "color": color}
            )

        for name in LEAD_SOURCES:
            LeadSource.objects.get_or_create(name=name)

        for name in LOST_REASONS:
            LostReason.objects.get_or_create(name=name)

        for i, name in enumerate(PRODUCTION_STAGES):
            ProductionStageTemplate.objects.get_or_create(name=name, defaults={"sequence": i})

        for i, name in enumerate(QC_CHECKLIST):
            QCChecklistItem.objects.get_or_create(name=name, defaults={"sequence": i})

        for i, name in enumerate(INSTALLATION_CHECKLIST):
            InstallationChecklistItem.objects.get_or_create(name=name, defaults={"sequence": i})

        for name in SERVICE_CATEGORIES:
            ServiceCategory.objects.get_or_create(name=name)

        for name in GLASS_TYPES:
            GlassType.objects.get_or_create(name=name)
        for name in HARDWARE_TYPES:
            HardwareType.objects.get_or_create(name=name)
        for name in ACCESSORY_TYPES:
            AccessoryType.objects.get_or_create(name=name)

        ProfileSeries.objects.get_or_create(series="60mm Casement", brand="Generic", colour="White")

        template, created = PaymentTermTemplate.objects.get_or_create(name="Standard (50/40/10)", defaults={"is_default": True})
        if created:
            PaymentTermStep.objects.bulk_create([
                PaymentTermStep(template=template, label="Advance", percent=50, trigger="On order confirmation", sequence=1),
                PaymentTermStep(template=template, label="Before Dispatch", percent=40, trigger="Before dispatch", sequence=2),
                PaymentTermStep(template=template, label="After Installation", percent=10, trigger="After installation", sequence=3),
            ])

        self.stdout.write(self.style.SUCCESS("Master data seeded successfully."))

    def _seed_logo(self, company):
        from pathlib import Path

        from django.conf import settings
        from django.core.files import File

        source = Path(settings.BASE_DIR) / "static" / "branding" / "titans_logo.png"
        if not source.exists():
            return
        with open(source, "rb") as f:
            company.logo.save("titans_logo.png", File(f), save=True)
        self.stdout.write(self.style.SUCCESS("Company logo set from static/branding/titans_logo.png"))

    def _seed_demo_users(self):
        from apps.accounts.models import User

        for username, group_name, first_name, last_name, is_staff in DEMO_USERS:
            user, created = User.objects.get_or_create(
                username=username,
                defaults={
                    "first_name": first_name, "last_name": last_name, "is_active": True, "is_staff": is_staff,
                    "employee_id": username.upper(),
                },
            )
            user.set_password(DEMO_PASSWORD)
            user.is_active = True
            user.is_staff = is_staff
            user.save()
            group = Group.objects.get(name=group_name)
            user.groups.set([group])
        self.stdout.write(self.style.SUCCESS(f"Demo accounts ready ({len(DEMO_USERS)}), password: {DEMO_PASSWORD}"))

    def _seed_superuser(self):
        """
        Creates a real admin account from environment variables, so a host
        with no interactive shell (e.g. Render's free plan) still ends up
        with a proper login -- this only ever CREATES the account once; if
        it already exists (or was since edited by hand), it's left alone.
        """
        import os

        from apps.accounts.models import User

        username = os.environ.get("DJANGO_SUPERUSER_USERNAME")
        password = os.environ.get("DJANGO_SUPERUSER_PASSWORD")
        if not username or not password:
            return
        if User.objects.filter(username=username).exists():
            self.stdout.write(f"Superuser '{username}' already exists -- left untouched.")
            return
        email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
        User.objects.create_superuser(username=username, email=email, password=password)
        self.stdout.write(self.style.SUCCESS(f"Superuser '{username}' created from environment variables."))
