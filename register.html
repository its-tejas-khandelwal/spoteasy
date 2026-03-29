// Firebase Service Worker — SpotEasy India
// Handles background push notifications

importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/9.0.0/firebase-messaging-compat.js');

// Initialize Firebase
firebase.initializeApp({
  apiKey: self.FIREBASE_API_KEY || '',
  authDomain: self.FIREBASE_AUTH_DOMAIN || '',
  projectId: self.FIREBASE_PROJECT_ID || '',
  storageBucket: self.FIREBASE_STORAGE_BUCKET || '',
  messagingSenderId: self.FIREBASE_SENDER_ID || '',
  appId: self.FIREBASE_APP_ID || ''
});

const messaging = firebase.messaging();

// Handle background messages
messaging.onBackgroundMessage(function(payload) {
  console.log('[SpotEasy] Background message:', payload);
  const title = payload.notification.title || 'SpotEasy India';
  const body  = payload.notification.body  || 'You have a new notification';
  const icon  = '/static/icons/icon-192.png';
  self.registration.showNotification(title, { body, icon });
});
