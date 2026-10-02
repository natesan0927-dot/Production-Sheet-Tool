"""The area a location is in — "Anna Nagar, Chennai" — for the site-visit timeline.

Looked up from OpenStreetMap's free address service (Nominatim) once a stop is
saved, on a background thread, so the sales executive never waits for it. If the
service cannot be reached the stop still has its exact location and map link;
the area is simply left out. Its terms ask for no more than one request a
second, a name that says who is asking, and credit, which the timeline gives.
"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request

from django.conf import settings
from django.db import connection, transaction

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_last = [0.0]

# Most specific first: the first of each group found makes up the name.
AREA = ("neighbourhood", "suburb", "quarter", "village", "hamlet", "residential", "road")
TOWN = ("city", "town", "municipality", "city_district", "county", "state_district")


def describe(latitude, longitude):
    """"Anna Nagar, Chennai" for a point, or "" if it cannot be had."""
    url = settings.PLACES_LOOKUP_URL
    if not url:
        return ""
    query = urllib.parse.urlencode({"format": "jsonv2", "lat": latitude, "lon": longitude, "zoom": 16, "addressdetails": 1})
    request = urllib.request.Request(
        f"{url}?{query}",
        headers={"User-Agent": settings.PLACES_USER_AGENT, "Accept-Language": "en"},
    )
    with _lock:
        wait = 1.0 - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        try:
            with urllib.request.urlopen(request, timeout=8) as response:
                found = json.loads(response.read().decode("utf-8", "replace") or "{}")
        except Exception:
            logger.warning("Could not look up the area for a site stop", exc_info=True)
            return ""
        finally:
            _last[0] = time.monotonic()
    address = found.get("address") or {}
    parts = [next((address[key] for key in group if address.get(key)), "") for group in (AREA, TOWN)]
    parts = [part for part in parts if part]
    if len(parts) == 2 and parts[0] == parts[1]:
        parts = parts[:1]
    return ", ".join(parts)[:200]


def fill_in(model, pk, latitude_field="latitude", longitude_field="longitude", place_field="place"):
    """Once saved, look up the area for a row's location and store it — in the background."""
    def run():
        try:
            row = model.objects.filter(pk=pk).values(latitude_field, longitude_field).first()
            if row and row[latitude_field] is not None:
                place = describe(row[latitude_field], row[longitude_field])
                if place:
                    model.objects.filter(pk=pk).update(**{place_field: place})
        except Exception:
            logger.warning("Could not store the area for a site stop", exc_info=True)
        finally:
            if not settings.PLACES_INLINE:
                connection.close()

    def start():
        if settings.PLACES_INLINE:
            run()
        else:
            threading.Thread(target=run, name="place-lookup").start()

    if settings.PLACES_LOOKUP_URL:
        transaction.on_commit(start)
