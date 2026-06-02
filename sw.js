// Service Worker – Mein Sparplan PWA
// Bug 4 Fix: Network-First für /data/* (frische ETF-Daten), Cache-First für statische Assets.
// B1 Fix: Offline-Lookup ignoriert den ?t=-Cache-Buster und liefert die NEUESTE gecachte
//         Kopie. Pro Daten-Datei werden rollend max. DATA_CACHE_KEEP Kopien behalten,
//         ältere werden automatisch gelöscht (kein unbegrenzter Stapel mehr).

const CACHE_NAME = 'sparplan-v32-20260602-data-cache-rolling3';
const FORCE_RELOAD = true;

// Pro Daten-Datei (z. B. performance.json) maximal so viele Kopien behalten.
// Sobald eine neuere dazukommt und mehr als KEEP existieren, fliegt die älteste raus.
const DATA_CACHE_KEEP = 3;

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

// Hilfsfunktion: ist das eine HTML-/Navigationsanfrage (index.html)?
// Network-First, damit neue Builds ohne Cache-Bump sofort ankommen.
function isHtmlRequest(request) {
  if (request.mode === 'navigate') return true;
  const accept = request.headers.get('accept') || '';
  return accept.includes('text/html');
}

// --- B1: Daten-Cache mit rollender Begrenzung -------------------------------
// Alle Cache-Einträge für DENSELBEN Daten-Pfad finden (die ?t=-Uhrzeit wird
// ignoriert), sortiert nach Zeitstempel – neueste zuerst.
async function dataEntriesFor(cache, requestUrl) {
  const targetPath = new URL(requestUrl).pathname;
  const keys = await cache.keys();
  return keys
    .map(req => ({ req, url: new URL(req.url) }))
    .filter(e => e.url.pathname === targetPath)
    .map(e => ({ req: e.req, t: Number(e.url.searchParams.get('t')) || 0 }))
    .sort((a, b) => b.t - a.t); // neueste zuerst
}

// Nach dem Schreiben aufräumen: nur die neuesten DATA_CACHE_KEEP Kopien behalten.
async function pruneDataCache(cache, requestUrl) {
  const entries = await dataEntriesFor(cache, requestUrl);
  for (const stale of entries.slice(DATA_CACHE_KEEP)) {
    await cache.delete(stale.req);
  }
}

// Offline: die NEUESTE gecachte Kopie für diesen Pfad zurückgeben (Uhrzeit egal).
async function newestDataMatch(cache, requestUrl) {
  const entries = await dataEntriesFor(cache, requestUrl);
  return entries.length ? cache.match(entries[0].req) : undefined;
}

// Network-First für ETF-Daten: frisch vom Server; offline die neueste Kopie.
async function networkFirstData(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200 && response.type !== 'opaque') {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
      await pruneDataCache(cache, request.url); // rollend auf max. 3 begrenzen
    }
    return response;
  } catch (e) {
    const cache = await caches.open(CACHE_NAME);
    const cached = await newestDataMatch(cache, request.url);
    return cached || Response.error();
  }
}

// Network-First für HTML/index.html: neue Builds sofort, offline der Cache.
async function networkFirstHtml(request) {
  try {
    const response = await fetch(request);
    if (response && response.status === 200 && response.type !== 'opaque') {
      const cache = await caches.open(CACHE_NAME);
      await cache.put(request, response.clone());
    }
    return response;
  } catch (e) {
    const cached = await caches.match(request);
    return cached || caches.match('./index.html');
  }
}

// Cache-First für statische Assets (Icons, manifest …).
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  const response = await fetch(request);
  if (response && response.status === 200 && response.type !== 'opaque') {
    const cache = await caches.open(CACHE_NAME);
    await cache.put(request, response.clone());
  }
  return response;
}

// Fetch-Handler:
//   /data/*  → Network-First + rollender Cache (max. 3 Kopien/Datei)
//   HTML     → Network-First (Offline-Fallback auf index.html)
//   Restliche Assets → Cache-First
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  if (isDataRequest(event.request.url)) {
    event.respondWith(networkFirstData(event.request));
  } else if (isHtmlRequest(event.request)) {
    event.respondWith(networkFirstHtml(event.request));
  } else {
    event.respondWith(cacheFirst(event.request));
  }
});
