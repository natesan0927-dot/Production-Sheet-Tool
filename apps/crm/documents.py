"""Opening a document straight in the phone's own viewer app.

On Android, tapping a document used to download it. The person then had to
open it from the download notification, and pressing back from the viewer
dropped them on the home screen, because Android returns to whatever launched
the viewer, and that was the notification shade.

Now the app hands the document to Android directly, as an "open with" request,
so a PDF viewer, Drive or a photo app opens it on top of Titans, and back comes
straight back here. The viewer app cannot sign in, so it is given a short-lived
link that works without one: it names one document and one person, and whatever
that person may open is checked again when the viewer fetches it. When no app on
the phone can open that kind of file, Android falls back to downloading it, as
before.

Only the document addresses below can be opened this way; a link can never
stand in for a signed-in session anywhere else in the app.
"""

import copy
import re
from urllib.parse import quote, unquote, urlsplit

from django.contrib.auth.decorators import login_required
from django.core import signing
from django.http import Http404, HttpResponseRedirect, QueryDict
from django.urls import Resolver404, resolve, reverse
from django.utils.http import content_disposition_header

from apps.accounts.models import User

# Every address that hands over a document: uploaded files and the PDFs the app draws.
DOCUMENTS = {
    "crm:lead_file",
    "crm:payment_receipt",
    "crm:installer_receipt",
    "crm:caf_download",
    "crm:warranty_download",
    "crm:handover_download",
    "crm:ledger_pdf",
    "crm:outstanding_pdf",
    "monitoring:report_pdf",
    "monitoring:report_to_date",
    "monitoring:report_excel",
}

SALT = "titans.open-document"
LINK_MINUTES = 10


class IntentRedirect(HttpResponseRedirect):
    """Android's "open with" address. Django only redirects to web addresses unless told otherwise."""

    allowed_schemes = ["intent"]


def _document(address):
    """(view, args, kwargs, query) for one of the document addresses, or 404."""
    parts = urlsplit(address or "")
    if parts.scheme or parts.netloc or not parts.path.startswith("/"):
        raise Http404
    try:
        match = resolve(parts.path)
    except Resolver404:
        raise Http404
    if match.view_name not in DOCUMENTS:
        raise Http404
    return match, QueryDict(parts.query)


def _as(request, user, query):
    """The same request, made by `user`, with `query` as its query string."""
    asked = copy.copy(request)
    asked.user = user
    asked.GET = query
    return asked


def _fetch(request, address, user):
    match, query = _document(address)
    return match.func(_as(request, user, query), *match.args, **match.kwargs)


def _filename(response):
    header = response.get("Content-Disposition", "")
    spelled = re.search(r"filename\*=utf-8''([^;]+)", header, re.IGNORECASE)
    if spelled:
        return unquote(spelled.group(1))
    plain = re.search(r'filename="((?:[^"\\]|\\.)*)"', header)
    return plain.group(1).replace('\\"', '"') if plain else "document"


@login_required
def open_document(request):
    """Hand a document to the phone's own apps, or download it if none can open it.

    The document is fetched first as the person asking, so a document they may
    not see gives them the usual refusal and no link is ever made for it.
    """
    address = request.GET.get("u", "")
    response = _fetch(request, address, request.user)
    if response.status_code != 200:
        return response
    filename = _filename(response)
    kind = (response.get("Content-Type") or "application/octet-stream").split(";")[0].strip()
    response.close()

    token = signing.dumps({"u": request.user.pk, "a": address}, salt=SALT)
    link = request.build_absolute_uri(reverse("crm:document_link", args=[token, filename]))
    fallback = request.build_absolute_uri(address)
    scheme, rest = link.split("://", 1)
    return IntentRedirect(
        f"intent://{rest}#Intent;scheme={scheme};action=android.intent.action.VIEW;type={kind};"
        f"S.browser_fallback_url={quote(fallback, safe='')};end"
    )


def document_link(request, token, filename):
    """The document itself, for the viewer app the phone opened it in. No sign-in: the link is the permission."""
    try:
        asked = signing.loads(token, salt=SALT, max_age=LINK_MINUTES * 60)
    except signing.BadSignature:
        raise Http404("This link has expired. Open the document again from the app.")
    user = User.objects.filter(pk=asked.get("u"), is_active=True).first()
    if user is None:
        raise Http404
    response = _fetch(request, asked.get("a"), user)
    if response.status_code != 200:
        raise Http404
    # Shown in the viewer rather than saved, under its own name.
    response["Content-Disposition"] = content_disposition_header(False, _filename(response))
    response["Cache-Control"] = "private, no-store"
    response["Referrer-Policy"] = "no-referrer"
    response["X-Robots-Tag"] = "noindex, nofollow"
    return response
