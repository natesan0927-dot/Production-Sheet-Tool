"""Serving uploaded documents.

Django's `static()` helper does nothing when DEBUG is off, so in production
there is no route for /media/ at all and every uploaded file 404s. These are
signed CAFs, invoices, measurements and payment receipts, so they need a route
— and they need one that asks who is looking first. A customer's paperwork
should not be readable by anyone who happens to have the URL.

When an S3-compatible bucket is configured the storage backend hands out its
own signed, expiring links and this view is not used.
"""

from pathlib import Path

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.views.decorators.http import require_GET


@require_GET
@login_required
def serve_upload(request, path):
    root = Path(settings.MEDIA_ROOT).resolve()
    try:
        target = (root / path).resolve()
    except (OSError, ValueError):
        raise Http404

    # `resolve()` collapses any ../ in the path, so this catches an attempt to
    # walk out of the media folder — and refuses symlinks pointing outside it.
    if root not in target.parents or not target.is_file():
        raise Http404

    # as_attachment=False so a PDF opens in the browser tab the app links to.
    return FileResponse(target.open("rb"), as_attachment=False, filename=target.name)
