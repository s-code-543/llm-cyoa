// Offline fallback for the installed app. Game/API responses stay on the network.
const CACHE_NAME = 'cyoa-v3-signpost';
const OFFLINE_URL = '/offline.html';

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll([
      OFFLINE_URL,
      '/static/icons/icon-192.png',
      '/static/icons/icon-512.png',
      '/static/icons/icon-maskable-192.png',
      '/static/icons/icon-maskable-512.png',
      '/static/icons/favicon-96x96.png',
    ])).then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((names) => Promise.all(
      names.filter((name) => name.startsWith('cyoa-') && name !== CACHE_NAME)
        .map((name) => caches.delete(name))
    )).then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  if (event.request.mode === 'navigate') {
    event.respondWith(
      fetch(event.request).catch(() => caches.match(OFFLINE_URL))
    );
    return;
  }

  if (url.pathname.startsWith('/static/')) {
    // Network-first keeps deployments fresh; cached assets remain available offline.
    const response = fetch(event.request);
    event.waitUntil(response.then(async (result) => {
      if (result.ok) {
        const copy = result.clone();
        const cache = await caches.open(CACHE_NAME);
        await cache.put(event.request, copy);
      }
    }).catch(() => {}));
    event.respondWith(response.catch(async () =>
      (await caches.match(event.request)) || Response.error()
    ));
  }
});
