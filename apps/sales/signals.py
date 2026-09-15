"""
Cross-stage automation for the sales app. Most stage-to-stage automation in
this project (measurement -> quotation -> order -> production -> dispatch ->
installation -> handover -> warranty) is implemented as explicit service-layer
calls at the point of the state change (see apps.sales.services,
apps.production.services, apps.logistics.services, apps.aftersales.services)
so the chain stays easy to trace and debug. This module is reserved for
signal-based hooks that don't have one obvious call site (e.g. reacting to
admin-initiated changes to Order made outside the normal views).
"""

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.sales.models import Payment


@receiver(post_save, sender=Payment)
def notify_on_full_payment(sender, instance, created, **kwargs):
    if not created:
        return
    order = instance.order
    if order.due_amount() <= 0:
        from apps.core.notifications import notify

        if order.salesperson:
            notify(order.salesperson, f"Order {order.order_number} is now fully paid", url=order.get_absolute_url(), related_object=order)
