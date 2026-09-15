from django.contrib.contenttypes.models import ContentType


def notify(recipient, verb, message="", url="", related_object=None):
    """Create an in-app notification. Safe to call with recipient=None (no-op)."""
    from apps.core.models import Notification

    if recipient is None:
        return None

    kwargs = dict(recipient=recipient, verb=verb, message=message, url=url)
    if related_object is not None:
        kwargs["content_type"] = ContentType.objects.get_for_model(type(related_object))
        kwargs["object_id"] = related_object.pk

    return Notification.objects.create(**kwargs)


def notify_many(recipients, verb, message="", url="", related_object=None):
    for recipient in recipients:
        notify(recipient, verb, message=message, url=url, related_object=related_object)
