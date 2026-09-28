"""A page that answers "are you awake?" and nothing else.

Used by an uptime monitor and by the host's own health check. It deliberately
touches nothing: no database, no session, no template. A hosted database on a
free plan is metered by how long it is kept awake, so a ping that queried it
every few minutes would keep it awake all day and use up the month's allowance
in a couple of weeks. This one lets the database sleep.

It is a middleware, sitting ahead of everything else, rather than a view. A
view runs only after Django has checked the request's Host header against
ALLOWED_HOSTS, and a health check does not always announce the site's public
name — it can arrive addressed to the host's internal name. Django would refuse
that with a 400, the host would read it as the site being down, and the deploy
would never go live. Every other address, the login page included, is still
checked as strictly as before.
"""

from django.http import HttpResponse


class HealthCheckMiddleware:
    PATH = "/healthz/"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # request.path is read straight from the request line; it does not
        # validate the Host header the way request.get_host() does.
        if request.path == self.PATH and request.method in ("GET", "HEAD"):
            response = HttpResponse("ok", content_type="text/plain")
            response["Cache-Control"] = "no-store"
            return response
        return self.get_response(request)
