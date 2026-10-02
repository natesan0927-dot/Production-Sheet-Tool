/* Titans Windows CRM — service worker.

   Deliberately cautious. This is a system of record: showing someone a stale
   lead, or letting them think an upload went through when it did not, would be
   worse than showing nothing. So:

   - Pages and anything under /media/ are never served from cache. They always
     go to the network, and only fall back to an offline notice if there is no
     connection at all.
   - Only the shell — CSS, JS, fonts, icons — is cached, and it is refreshed in
     the background whenever the network has something newer.

   Bump VERSION to retire the old cache after a deploy. */

const VERSION = "titans-v1";
const SHELL = [
  "/static/css/app.css",
  "/static/js/app.js",
  "/static/js/guide.js",
  "/static/branding/titans_logo.png",
  "/static/branding/icon-192.png",
  "/static/branding/favicon.png",
  "/offline/",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(VERSION).then((cache) => cache.addAll(SHELL)).then(() => self.skipWaiting())
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys()
      .then((names) => Promise.all(names.filter((name) => name !== VERSION).map((name) => caches.delete(name))))
      .then(() => self.clients.claim())
  );
});

/* Notifications. The server pushes one for every update a person gets (see
   apps/crm/push.py); it is shown like any app's notification, and tapping it
   opens the page it is about, in the app if the app is already open. */
self.addEventListener("push", (event) => {
  let data = {};
  try {
    data = event.data ? event.data.json() : {};
  } catch (e) {
    data = { body: event.data ? event.data.text() : "" };
  }
  event.waitUntil(
    self.registration.showNotification(data.title || "Titans Windows", {
      body: data.body || "You have a new update.",
      icon: "/static/branding/icon-192.png",
      badge: "/static/branding/badge-96.png",
      tag: data.tag || undefined,
      renotify: Boolean(data.tag),
      // An urgent enquiry stays until it is tapped, and buzzes harder.
      requireInteraction: Boolean(data.urgent),
      vibrate: data.urgent ? [300, 120, 300, 120, 300] : [120, 60, 120],
      data: { url: data.url || "/notifications/" },
    })
  );
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const target = new URL((event.notification.data && event.notification.data.url) || "/", self.location.origin).href;
  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((windows) => {
      const open = windows.find((client) => client.url.startsWith(self.location.origin));
      if (open) {
        return open
          .focus()
          .then((client) => (client && client.navigate ? client.navigate(target) : client))
          .catch(() => self.clients.openWindow(target));
      }
      return self.clients.openWindow(target);
    })
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Uploaded files and anything a person is about to act on come from the
  // network, full stop.
  if (url.pathname.startsWith("/media/")) return;

  // Opening a document in the phone's viewer is a hand-off to Android that the
  // browser has to make itself, so it is left entirely alone.
  if (url.pathname.startsWith("/open/")) return;

  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request).catch(() => caches.match("/offline/"))
    );
    return;
  }

  // The shell: serve what we have, and quietly pick up anything newer.
  event.respondWith(
    caches.match(request).then((cached) => {
      const live = fetch(request)
        .then((response) => {
          if (response && response.status === 200 && response.type === "basic") {
            const copy = response.clone();
            caches.open(VERSION).then((cache) => cache.put(request, copy));
          }
          return response;
        })
        .catch(() => cached);
      return cached || live;
    })
  );
});
