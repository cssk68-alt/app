// Service Worker – Mein Sparplan PWA
// Bug 4 Fix: Network-First für /data/* (frische ETF-Daten), Cache-First für statische Assets.
// Zusatz: Truncation-Fix (originale Datei fehlte die letzten 5 schließenden Klammern).

const CACHE_NAME = 'sparplan-v18-20260525-v14';
const FORCE_RELOAD = true;

const STATIC_ASSETS = [
  './',
  './index.html',
  './manifest.json',
  './icon-180.png',
  './icon-192.png',
  './icon-512.png',
];

// Datenpfade: werden NICHT im Install vorab gecacht,
// damit der erste Fetch immer fresh vom Server kommt.
const DATA_PATHS = [
  './data/geo_weights.json',
  './data/holdings.json',
  './data/sectors.json',
  './data/static_meta.json',
];

// Installation: nur statische Assets vorab cachen (keine Daten-Files!)
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Aktivierung: alte Caches löschen, offene Clients zum Reload anstossen
self.addEventListener('activate', event => {
  event.waitUntil((async () => {
    const keys = await caches.keys();
    await Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)));
    await self.clients.claim();
    if (FORCE_RELOAD) {
      const clients = await self.clients.matchAll({ type: 'window', includeUncontrolled: true });
      for (const c of clients) c.postMessage({ type: 'force-reload', cache: CACHE_NAME });
    }
  })());
});

// Hilfsfunktion: ist die angefragte URL ein Datenpfad?
function isDataRequest(url) {
  const path = new URL(url).pathname;
  return path.includes('/data/');
}

// Fetch-Handler:
//   /data/*  → Network-First: frisch vom Server, Fallback auf Cache (Offline-Support)
//   Alles andere → Cache-First: schnell aus Cache, Fallback auf Network
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  if (isDataRequest(event.request.url)) {
    // Network-First für ETF-Daten: Sonntags-Update sofort sichtbar
    event.respondWith(
      fetch(event.request)
        .then(response => {
          if (!response || response.status !== 200 || response.type === 'opaque') {
            return response;
          }
          // Frische Antwort in Cache schreiben (als Offline-Fallback)
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => {
          // Netzwerk nicht erreichbar → gecachte Version ausliefern
          return caches.match(event.request);
        })
    );
  } else {
    // Cache-First für statische Assets (index.html, Icons, manifest)
    event.respondWith(
      caches.match(event.request).then(cached => {
        if (cached) return cached;
        return fetch(event.request).then(response => {
          if (!response || response.status !== 200 || response.type === 'opaque') {
            return response;
          }
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        });
      })
    );
  }
});
