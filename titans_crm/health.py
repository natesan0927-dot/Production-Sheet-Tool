"""A page that answers "are you awake?" and nothing else.

Used by an uptime monitor and by the host's own health check. It deliberately
touches nothing: no database, no session, no template. A hosted database on a
free plan is metered by how long it is kept awake, so a ping that queried it
every few minutes would keep it awake all day and use up the month's allowance
in a couple of weeks. This one lets the database sleep.
"""

from django.http import HttpResponse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET


@never_cache
@require_GET
def healthz(request):
    return HttpResponse("ok", content_type="text/plain")
