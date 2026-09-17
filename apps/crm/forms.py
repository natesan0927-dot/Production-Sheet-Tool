from django import forms

from apps.core.models import LeadSource
from apps.crm.models import Customer, FollowUp, Lead, LostLeadDetail


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        exclude = ["customer_code", "created_date"]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 2}),
            "project_address": forms.Textarea(attrs={"rows": 2}),
            "notes": forms.Textarea(attrs={"rows": 2}),
        }


class LeadCreateForm(forms.ModelForm):
    """
    A lead can be created either against an existing customer, or by
    capturing a brand-new customer's details in the same form -- once saved,
    that information automatically flows into every later stage (measurement,
    quotation, order, CAF...) without ever being retyped.
    """

    customer = forms.ModelChoiceField(queryset=Customer.objects.all(), required=False, label="Existing Customer")
    new_customer_name = forms.CharField(max_length=150, required=False, label="Customer Name")
    new_customer_mobile = forms.CharField(max_length=20, required=False, label="Mobile Number")
    new_customer_alternate_number = forms.CharField(max_length=20, required=False, label="Alternate Number")
    new_customer_email = forms.EmailField(required=False, label="Email")
    new_customer_type = forms.ChoiceField(choices=Customer.CUSTOMER_TYPE_CHOICES, required=False, initial="individual")
    new_customer_company_name = forms.CharField(max_length=150, required=False, label="Company Name")
    new_customer_contact_person = forms.CharField(max_length=150, required=False, label="Contact Person")
    new_customer_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), required=False, label="Address")
    new_customer_city = forms.CharField(max_length=100, required=False, label="City")
    new_customer_state = forms.CharField(max_length=100, required=False, label="State")
    new_customer_pincode = forms.CharField(max_length=10, required=False, label="Pincode")
    new_customer_project_address = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 2}), required=False, label="Project Address"
    )

    class Meta:
        model = Lead
        fields = [
            "customer", "contact_number", "email", "project_name", "project_location",
            "lead_source", "requirement", "approximate_quantity", "expected_value",
            "expected_closing_date", "assigned_salesperson", "priority", "remarks",
        ]
        widgets = {
            "requirement": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
            "expected_closing_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("customer") and not cleaned.get("new_customer_name"):
            raise forms.ValidationError("Select an existing customer or enter a new customer's name.")
        if not cleaned.get("customer") and not cleaned.get("new_customer_mobile"):
            raise forms.ValidationError("Mobile number is required for a new customer.")
        return cleaned

    def save(self, commit=True):
        lead = super().save(commit=False)
        if not self.cleaned_data.get("customer"):
            customer = Customer.objects.create(
                customer_name=self.cleaned_data["new_customer_name"],
                mobile_number=self.cleaned_data["new_customer_mobile"],
                alternate_number=self.cleaned_data.get("new_customer_alternate_number", ""),
                email=self.cleaned_data.get("new_customer_email", ""),
                customer_type=self.cleaned_data.get("new_customer_type") or "individual",
                company_name=self.cleaned_data.get("new_customer_company_name", ""),
                contact_person=self.cleaned_data.get("new_customer_contact_person", ""),
                address=self.cleaned_data.get("new_customer_address", ""),
                city=self.cleaned_data.get("new_customer_city", ""),
                state=self.cleaned_data.get("new_customer_state", ""),
                pincode=self.cleaned_data.get("new_customer_pincode", ""),
                project_name=self.cleaned_data.get("project_name", ""),
                project_address=self.cleaned_data.get("new_customer_project_address", ""),
                lead_source=self.cleaned_data.get("lead_source"),
                assigned_salesperson=self.cleaned_data.get("assigned_salesperson"),
            )
            lead.customer = customer
        else:
            lead.customer = self.cleaned_data["customer"]
        if commit:
            lead.save()
        return lead


class LeadUpdateForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            "contact_number", "email", "project_name", "project_location", "lead_source",
            "requirement", "approximate_quantity", "expected_value", "expected_closing_date",
            "assigned_salesperson", "priority", "status", "remarks",
        ]
        widgets = {
            "requirement": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
            "expected_closing_date": forms.DateInput(attrs={"type": "date"}),
        }


class LeadAssignForm(forms.Form):
    assigned_to = forms.ModelChoiceField(queryset=None, label="Assign to")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.accounts.models import User

        self.fields["assigned_to"].queryset = User.objects.filter(is_active=True).order_by("first_name")


class FollowUpForm(forms.ModelForm):
    """
    Only one date is collected -- the next follow-up reminder date. `date`
    (when this interaction happened) is set to today automatically in the
    view, and `time` defaults to 9am, so reps don't have to set either by
    hand every time.
    """

    class Meta:
        model = FollowUp
        fields = ["type", "time", "discussion", "customer_response", "next_followup_date", "next_action", "remarks"]
        widgets = {
            "time": forms.TimeInput(attrs={"type": "time"}),
            "next_followup_date": forms.DateInput(attrs={"type": "date"}),
            "discussion": forms.Textarea(attrs={"rows": 2}),
            "customer_response": forms.Textarea(attrs={"rows": 2}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["next_followup_date"].required = True
        self.fields["next_followup_date"].label = "Next Follow-up Reminder Date"


class LostLeadForm(forms.ModelForm):
    class Meta:
        model = LostLeadDetail
        fields = [
            "lost_date", "reason", "reason_category", "competitor", "competitor_product",
            "competitor_price", "customer_quoted_price", "detailed_narration",
        ]
        widgets = {
            "lost_date": forms.DateInput(attrs={"type": "date"}),
            "detailed_narration": forms.Textarea(attrs={"rows": 3}),
        }
