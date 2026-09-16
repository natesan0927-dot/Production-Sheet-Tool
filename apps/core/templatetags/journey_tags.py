from django import template

from apps.core.journey import build_journey

register = template.Library()


@register.inclusion_tag("partials/journey_stepper.html")
def journey_stepper(obj):
    data = build_journey(obj)
    if data is None:
        return {"stages": None}
    return data
