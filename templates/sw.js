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

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;

  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  // Uploaded files and anything a person is about to act on come from the
  // network, full stop.
  if (url.pathname.startsWith("/media/")) return;

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
