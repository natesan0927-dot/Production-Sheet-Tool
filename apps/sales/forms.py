from django import forms
from django.forms import inlineformset_factory

from apps.sales.models import Order, Payment, Quotation, QuotationItem, SalesTarget


class QuotationForm(forms.ModelForm):
    class Meta:
        model = Quotation
        fields = ["payment_terms", "delivery_period", "warranty_text", "terms_text", "tax_percent"]
        widgets = {
            "warranty_text": forms.Textarea(attrs={"rows": 2}),
            "terms_text": forms.Textarea(attrs={"rows": 3}),
        }


QuotationItemFormSet = inlineformset_factory(
    Quotation, QuotationItem,
    fields=["description", "dimensions", "quantity", "unit_rate", "glass", "hardware", "accessories"],
    extra=1, can_delete=True,
)


class QuotationReviseForm(forms.Form):
    reason = forms.CharField(widget=forms.Textarea(attrs={"rows": 2}), label="Reason for revision")


class OrderConfirmForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            "final_order_value", "discount", "tax", "payment_terms", "advance_amount",
            "balance_amount", "expected_delivery_date", "expected_installation_date", "special_instructions",
        ]
        widgets = {
            "expected_delivery_date": forms.DateInput(attrs={"type": "date"}),
            "expected_installation_date": forms.DateInput(attrs={"type": "date"}),
            "special_instructions": forms.Textarea(attrs={"rows": 2}),
        }


class PaymentForm(forms.ModelForm):
    class Meta:
        model = Payment
        fields = ["amount", "mode", "date", "reference"]
        widgets = {"date": forms.DateInput(attrs={"type": "date"})}


class SalesTargetForm(forms.ModelForm):
    class Meta:
        model = SalesTarget
        fields = ["salesperson", "team_name", "branch", "product_category", "year", "month", "target_amount"]
