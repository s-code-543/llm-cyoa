// Service Worker for CYOA PWA
// Required for Chromium/Samsung Internet PWA installability

const CACHE_NAME = 'cyoa-v2';
const OFFLINE_URL = '/offline.html';

// Install: pre-cache the offline fallback page and key assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll([
        OFFLINE_URL,
        '/static/icons/icon-192.png',
        '/static/icons/icon-512.png',
        '/static/icons/favicon-96x96.png',
      ])
    )
  );
  self.skipWaiting();
});

// Activate: clean old caches and claim clients immediately
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) =>
      Promise.all(
        names.filter((n) => n !== CACHE_NAME).map((n) => caches.delete(n))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch: network-first for navigations, cache-first for static assets
self.addEventListener('fetch', (event) => {
  // Only intercept GET requests
  if (event.request.method !== 'GET') return;

  // Navigation requests: network-first with offline fallback
  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  // Static assets: network-first, cache fallback
  if (event.request.url.includes('/static/')) {
    event.respondWith(
      fetch(event.request)
        .then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return response;
        })
        .catch(() => caches.match(event.request))
    );
    return;
  }

  // Everything else: just fetch from network
  event.respondWith(fetch(event.request));
});
