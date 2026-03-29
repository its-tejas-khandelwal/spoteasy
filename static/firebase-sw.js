self.addEventListener('install', function() {
  self.skipWaiting();
});
self.addEventListener('activate', function(e) {
  e.waitUntil(clients.claim());
});
self.addEventListener('push', function(e) {
  var data = {};
  try { data = e.data.json(); } catch(err) {}
  e.waitUntil(
    self.registration.showNotification(data.title || 'SpotEasy India', {
      body: data.body || 'New notification',
      icon: '/static/icons/icon-192.png'
    })
  );
});
self.addEventListener('notificationclick', function(e) {
  e.notification.close();
  e.waitUntil(clients.openWindow('/'));
});
