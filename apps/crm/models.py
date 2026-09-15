from django.conf import settings
from django.db import models
from django.urls import reverse
from simple_history.models import HistoricalRecords

from apps.core.models import Competitor, LeadSource, LeadStatus, LostReason


class Customer(models.Model):
    CUSTOMER_TYPE_CHOICES = [
        ("individual", "Individual"),
        ("villa", "Villa"),
        ("apartment", "Apartment"),
        ("builder", "Builder"),
        ("architect", "Architect"),
        ("interior_designer", "Interior Designer"),
        ("contractor", "Contractor"),
        ("commercial", "Commercial"),
        ("government", "Government"),
        ("dealer", "Dealer"),
        ("other", "Other"),
    ]
    STATUS_CHOICES = [("active", "Active"), ("inactive", "Inactive")]

    customer_code = models.CharField(max_length=20, unique=True, blank=True)
    customer_name = models.CharField(max_length=150)
    company_name = models.CharField(max_length=150, blank=True)
    contact_person = models.CharField(max_length=150, blank=True)
    mobile_number = models.CharField(max_length=20)
    alternate_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    city = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    pincode = models.CharField(max_length=10, blank=True)
    project_name = models.CharField(max_length=150, blank=True)
    project_address = models.TextField(blank=True)
    customer_type = models.CharField(max_length=20, choices=CUSTOMER_TYPE_CHOICES, default="individual")
    lead_source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True, blank=True)
    assigned_salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="customers"
    )
    created_date = models.DateTimeField(auto_now_add=True)
    customer_status = models.CharField(max_length=10, choices=STATUS_CHOICES, default="active")
    notes = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_date"]

    def __str__(self):
        return f"{self.customer_name} ({self.customer_code})"

    def save(self, *args, **kwargs):
        if not self.customer_code:
            from apps.core.numbering import get_next_number

            self.customer_code = get_next_number("customer")
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("crm:customer_detail", args=[self.pk])


class Lead(models.Model):
    PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")]

    lead_id = models.CharField(max_length=20, unique=True, blank=True)
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="leads")
    contact_number = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    project_name = models.CharField(max_length=150, blank=True)
    project_location = models.CharField(max_length=200, blank=True)
    lead_source = models.ForeignKey(LeadSource, on_delete=models.SET_NULL, null=True, blank=True)
    requirement = models.TextField(blank=True)
    approximate_quantity = models.PositiveIntegerField(null=True, blank=True)
    expected_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    expected_closing_date = models.DateField(null=True, blank=True)
    assigned_salesperson = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_leads"
    )
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default="medium")
    status = models.ForeignKey(LeadStatus, on_delete=models.PROTECT, related_name="leads")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="leads_created"
    )
    created_date = models.DateTimeField(auto_now_add=True)
    remarks = models.TextField(blank=True)

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created_date"]

    def __str__(self):
        return f"{self.lead_id} - {self.customer.customer_name}"

    def save(self, *args, **kwargs):
        creating = self._state.adding
        if not self.lead_id:
            from apps.core.numbering import get_next_number

            self.lead_id = get_next_number("lead")
        if not self.status_id:
            default_status = LeadStatus.objects.filter(is_default=True).first() or LeadStatus.objects.order_by("sequence").first()
            self.status = default_status
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("crm:lead_detail", args=[self.pk])

    @property
    def is_won(self):
        return bool(self.status and self.status.is_won)

    @property
    def is_lost(self):
        return bool(self.status and self.status.is_lost)

    @property
    def latest_quotation(self):
        return self.quotations.order_by("-version").first() if hasattr(self, "quotations") else None


class LeadAssignment(models.Model):
    METHOD_CHOICES = [
        ("manual", "Manual"),
        ("round_robin", "Round Robin"),
        ("location", "Location Based"),
        ("product", "Product Based"),
        ("workload", "Workload Based"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="assignments")
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    method = models.CharField(max_length=15, choices=METHOD_CHOICES, default="manual")
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ["-assigned_at"]

    def __str__(self):
        return f"{self.lead.lead_id} -> {self.assigned_to}"


class FollowUp(models.Model):
    TYPE_CHOICES = [
        ("phone_call", "Phone Call"),
        ("whatsapp", "WhatsApp"),
        ("email", "Email"),
        ("site_visit", "Site Visit"),
        ("meeting", "Meeting"),
        ("negotiation", "Negotiation"),
        ("price_discussion", "Price Discussion"),
        ("technical_discussion", "Technical Discussion"),
        ("other", "Other"),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name="followups")
    type = models.CharField(max_length=25, choices=TYPE_CHOICES, default="phone_call")
    date = models.DateField()
    time = models.TimeField(null=True, blank=True)
    discussion = models.TextField(blank=True)
    customer_response = models.TextField(blank=True)
    next_followup_date = models.DateField(null=True, blank=True)
    next_action = models.CharField(max_length=255, blank=True)
    remarks = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_done = models.BooleanField(default=True)

    class Meta:
        ordering = ["-date", "-created_at"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.lead.lead_id} ({self.date})"


class CommunicationLog(models.Model):
    TYPE_CHOICES = FollowUp.TYPE_CHOICES + [("note", "Note")]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="communications")
    lead = models.ForeignKey(Lead, on_delete=models.SET_NULL, null=True, blank=True, related_name="communications")
    type = models.CharField(max_length=25, choices=TYPE_CHOICES, default="note")
    date = models.DateTimeField()
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    notes = models.TextField(blank=True)
    next_action = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date"]

    def __str__(self):
        return f"{self.get_type_display()} - {self.customer.customer_name}"


class LostLeadDetail(models.Model):
    REASON_CATEGORY_CHOICES = [
        ("price", "Price Issue"),
        ("quality", "Quality Issue"),
        ("delivery", "Delivery Issue"),
        ("design", "Design Issue"),
        ("relationship", "Relationship Issue"),
        ("project_cancelled", "Project Cancelled"),
        ("customer_postponed", "Customer Postponed"),
        ("other", "Other"),
    ]

    lead = models.OneToOneField(Lead, on_delete=models.CASCADE, related_name="lost_detail")
    lost_date = models.DateField()
    reason = models.ForeignKey(LostReason, on_delete=models.SET_NULL, null=True, blank=True)
    reason_category = models.CharField(max_length=25, choices=REASON_CATEGORY_CHOICES, default="other")
    competitor = models.ForeignKey(Competitor, on_delete=models.SET_NULL, null=True, blank=True)
    competitor_product = models.CharField(max_length=150, blank=True)
    competitor_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    customer_quoted_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    detailed_narration = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Lost - {self.lead.lead_id}"
