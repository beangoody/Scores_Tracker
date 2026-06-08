// sw.js — Trackr service worker
const CACHE_NAME = 'trackr-v2';

const PRECACHE_URLS = [
  '/',
  '/static/style.css',
  '/static/app.js',
  '/static/manifest.json',
  '/auth/login',
];

// ── Install ───────────────────────────────────────────────────────────────────
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(PRECACHE_URLS))
      .then(() => self.skipWaiting())
  );
});

// ── Activate ──────────────────────────────────────────────────────────────────
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys()
      .then(keys => Promise.all(
        keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k))
      ))
      .then(() => self.clients.claim())
  );
});

// ── Fetch — network first, cache fallback ─────────────────────────────────────
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;

  const url = new URL(event.request.url);
  if (url.pathname.startsWith('/stats/api') ||
      url.pathname.startsWith('/sports/api') ||
      url.pathname.startsWith('/push/')) return;

  event.respondWith(
    fetch(event.request)
      .then(response => {
        if (response && response.status === 200) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request).then(c => c || caches.match('/')))
  );
});

// ── Push — show notification ──────────────────────────────────────────────────
self.addEventListener('push', event => {
  let data = { title: 'Trackr', body: 'You have a new notification.', url: '/' };

  if (event.data) {
    try { data = JSON.parse(event.data.text()); } catch (_) {}
  }

  event.waitUntil(
    self.registration.showNotification(data.title, {
      body:    data.body,
      icon:    data.icon  || '/static/icons/icon-192.png',
      badge:   data.badge || '/static/icons/icon-192.png',
      data:    { url: data.url || '/' },
      vibrate: [200, 100, 200],
      // Show even if app is in foreground
      requireInteraction: false,
    })
  );
});

// ── Notification click — open the relevant page ───────────────────────────────
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true })
      .then(windowClients => {
        // If app is already open, focus it and navigate
        for (const client of windowClients) {
          if ('focus' in client) {
            client.focus();
            client.navigate(url);
            return;
          }
        }
        // Otherwise open a new window
        if (clients.openWindow) return clients.openWindow(url);
      })
  );
});