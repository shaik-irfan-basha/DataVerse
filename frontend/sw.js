/**
 * frontend/sw.js - DataVerse PWA Service Worker
 *
 * SECURITY INVARIANT:
 * Authenticated API endpoints, user datasets, and SQL results are NEVER cached.
 * Caches ONLY safe static application shell assets (HTML, CSS, JS, icons).
 */

const CACHE_NAME = 'dataverse-shell-v12';

const STATIC_ASSETS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/css/style.css?v=12.0.0',
  '/css/components.css?v=12.0.0',
  '/css/style.css',
  '/css/components.css',
  '/js/api.js',
  '/js/state.js',
  '/js/ui.js',
  '/js/app.js',
  '/icons/favicon.svg',
  '/icons/icon-192.png',
  '/icons/icon-512.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => {
      return cache.addAll(STATIC_ASSETS);
    })
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) => {
      return Promise.all(
        keys.filter((key) => key !== CACHE_NAME).map((key) => {
          console.log('[SW] Evicting stale cache:', key);
          return caches.delete(key);
        })
      );
    }).then(() => self.clients.claim())
  );
});

self.addEventListener('message', (event) => {
  if (event.data && event.data.type === 'SKIP_WAITING') {
    self.skipWaiting();
  }
});

self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // 1. BYPASS CACHE FOR ALL API CALLS & UPLOADS (Zero private data caching)
  if (url.pathname.startsWith('/api/') || url.pathname.startsWith('/docs') || url.pathname.startsWith('/openapi.json')) {
    event.respondWith(
      fetch(event.request).catch(() => {
        return new Response(
          JSON.stringify({
            status: "ERROR",
            error: "Network unavailable. DataVerse AI engine requires active network connectivity."
          }),
          {
            status: 503,
            headers: { 'Content-Type': 'application/json' }
          }
        );
      })
    );
    return;
  }

  // 2. Network-First for static assets with Cache fallback
  event.respondWith(
    fetch(event.request)
      .then((networkResponse) => {
        // If fetch succeeds, update cache in background
        if (event.request.method === 'GET' && networkResponse && networkResponse.status === 200) {
          const responseClone = networkResponse.clone();
          caches.open(CACHE_NAME).then((cache) => {
            cache.put(event.request, responseClone);
          });
        }
        return networkResponse;
      })
      .catch(() => {
        // Fallback to cache when offline or network fails
        return caches.match(event.request).then((cachedResponse) => {
          if (cachedResponse) {
            return cachedResponse;
          }
          if (event.request.mode === 'navigate') {
            return caches.match('/index.html');
          }
          return new Response('Network unavailable and asset not cached', {
            status: 503,
            statusText: 'Service Unavailable'
          });
        });
      })
  );
});
