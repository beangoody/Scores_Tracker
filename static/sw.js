// sw.js — Trackr service worker
// Caches the app shell for offline use and faster loads

const CACHE_NAME = 'trackr-v1';

// Core pages and assets to cache on install
const PRECACHE_URLS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
  '/auth/login',
];

// Install — cache the app shell
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

// Activate — clean up old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys
          .filter(key => key !== CACHE_NAME)
          .map(key => caches.delete(key))
      )
    ).then(() => self.clients.claim())
  );
});

// Fetch — network first, fall back to cache
// This means users always get fresh data when online,
// but the app still loads offline for cached pages
self.addEventListener('fetch', event => {
  // Only handle GET requests
  if (event.request.method !== 'GET') return;

  // Don't cache API calls or admin routes
  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/stats/api') ||
      url.pathname.startsWith('/sports/api')) {
    return;
  }

  event.respondWith(
    fetch(event.request)
      .then(response => {
        // Cache successful responses
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => {
            cache.put(event.request, clone);
          });
        }
        return response;
      })
      .catch(() => {
        // Network failed — try the cache
        return caches.match(event.request).then(cached => {
          return cached || caches.match('/');
        });
      })
  );
});