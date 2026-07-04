// Caches the app shell so the router loads offline. Map tiles and the Leaflet
// CDN are cross-origin and pass straight through to the network (no offline map).
const C = "bike-v1";
const ASSETS = [
  "./",
  "./index.html",
  "./graph.json",
  "./manifest.webmanifest",
  "./icon.svg",
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(caches.open(C).then((c) => c.addAll(ASSETS)));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((ks) =>
      Promise.all(ks.filter((k) => k !== C).map((k) => caches.delete(k)))
    )
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);
  if (url.origin === location.origin) {
    // cache-first for our own files
    e.respondWith(caches.match(e.request).then((r) => r || fetch(e.request)));
  }
  // cross-origin (tiles, Leaflet) -> let the browser hit the network normally
});
