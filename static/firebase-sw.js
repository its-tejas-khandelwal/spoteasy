// SpotEasy Firebase Service Worker — FCM V1 Compatible
// Place this file at /static/firebase-sw.js

importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.7.0/firebase-messaging-compat.js');

// Config will be injected — service worker reads from query param or cache
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(clients.claim()));

// Firebase init (config injected by main thread via postMessage)
let messaging;
self.addEventListener('message', event => {
  if (event.data && event.data.type === 'FIREBASE_CONFIG') {
    try {
      if (!self.firebaseApp) {
        self.firebaseApp = firebase.initializeApp(event.data.config);
      }
      messaging = firebase.messaging();
      messaging.onBackgroundMessage(payload => {
        const { title, body } = payload.notification || {};
        self.registration.showNotification(title || 'SpotEasy', {
          body:  body || 'You have a new update',
          icon:  '/static/icon-192.png',
          badge: '/static/badge.png',
          data:  payload.data || {},
          vibrate: [200, 100, 200],
          tag: 'spoteasy',
          requireInteraction: false,
          actions: [
            { action: 'open', title: '👁 View' },
            { action: 'dismiss', title: '✕' }
          ]
        });
      });
    } catch(e) { console.error('[SW] Firebase init error:', e); }
  }
});

// Click handler
self.addEventListener('notificationclick', event => {
  event.notification.close();
  const url = event.notification.data?.url || '/';
  if (event.action !== 'dismiss') {
    event.waitUntil(
      clients.matchAll({ type: 'window' }).then(cls => {
        const existing = cls.find(c => c.url.includes(self.location.origin));
        if (existing) { existing.focus(); existing.navigate(url); }
        else clients.openWindow(url);
      })
    );
  }
});
