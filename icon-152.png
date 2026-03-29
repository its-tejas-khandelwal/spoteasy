// SpotEasy Service Worker — PWA offline support
const CACHE = 'spoteasy-v1';
const OFFLINE_URL = '/offline';

// Files to cache for offline use
const PRECACHE = [
  '/',
  '/lots',
  '/login',
  '/register',
  '/static/keep-alive.js',
  '/static/notifications.js',
  '/static/manifest.json',
  'https://cdn.tailwindcss.com',
  'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap',
  'https://unpkg.com/lucide@latest/dist/umd/lucide.js',
];

self.addEventListener('install', e => {
  e.waitUntil(
    caches.open(CACHE).then(cache => cache.addAll(PRECACHE).catch(() => {}))
  );
  self.skipWaiting();
});

self.addEventListener('activate', e => {
  e.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  if (e.request.url.includes('/api/') || e.request.url.includes('/health')) return;

  e.respondWith(
    fetch(e.request)
      .then(resp => {
        if (resp.status === 200) {
          const clone = resp.clone();
          caches.open(CACHE).then(c => c.put(e.request, clone));
        }
        return resp;
      })
      .catch(() => caches.match(e.request).then(cached => {
        if (cached) return cached;
        // Return offline page for navigation requests
        if (e.request.mode === 'navigate') {
          return new Response(
            `<!DOCTYPE html><html><head><title>SpotEasy — Offline</title>
            <meta name="viewport" content="width=device-width,initial-scale=1"/>
            <style>body{font-family:Inter,sans-serif;display:flex;align-items:center;justify-content:center;min-height:100vh;margin:0;background:#f9fafb;text-align:center;padding:20px;}
            .card{background:white;border-radius:24px;padding:40px;max-width:360px;box-shadow:0 8px 32px rgba(0,0,0,0.1);}
            h1{color:#16a34a;font-size:24px;font-weight:900;margin:16px 0 8px;}
            p{color:#6b7280;font-size:14px;line-height:1.6;}
            button{background:#16a34a;color:white;border:none;border-radius:12px;padding:12px 24px;font-size:15px;font-weight:700;cursor:pointer;margin-top:20px;width:100%;}
            </style></head><body>
            <div class="card">
              <div style="font-size:48px;">🅿️</div>
              <h1>You're Offline</h1>
              <p>No internet connection. Please check your network and try again.</p>
              <button onclick="location.reload()">Try Again</button>
            </div></body></html>`,
            { headers: { 'Content-Type': 'text/html' } }
          );
        }
      }))
  );
});
