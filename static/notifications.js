// SpotEasy Notification Manager — FCM V1
'use strict';

const SpotEasyNotif = {
  config: null,
  messaging: null,
  swReg: null,

  async init(config) {
    this.config = config;
    if (!('Notification' in window) || !('serviceWorker' in navigator)) return;
    if (!config.apiKey) return; // Firebase not configured
    try {
      // Register SW
      this.swReg = await navigator.serviceWorker.register('/static/firebase-sw.js', { scope: '/' });
      // Send config to SW
      await navigator.serviceWorker.ready;
      this.swReg.active?.postMessage({ type: 'FIREBASE_CONFIG', config });

      // Init Firebase in main thread too
      if (!firebase.apps.length) firebase.initializeApp(config);
      this.messaging = firebase.messaging();

      // Foreground message handler
      this.messaging.onMessage(payload => this._toast(payload));

      // Auto-get token if already permitted
      if (Notification.permission === 'granted') await this._saveToken();

    } catch(e) { console.error('[SpotEasy Notif]', e); }
  },

  async requestPermission() {
    try {
      const p = await Notification.requestPermission();
      if (p === 'granted') { await this._saveToken(); return true; }
      return false;
    } catch(e) { return false; }
  },

  async _saveToken() {
    try {
      const token = await this.messaging.getToken({ vapidKey: this.config.vapidKey, serviceWorkerRegistration: this.swReg });
      if (token) {
        await fetch('/save_fcm_token', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ token })
        });
      }
    } catch(e) { console.error('[SpotEasy] Token save failed:', e); }
  },

  _toast({ notification: n = {} }) {
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:fixed;top:76px;right:16px;z-index:99999;max-width:320px;animation:seToast 0.35s cubic-bezier(.4,0,.2,1)';
    wrap.innerHTML = `
      <div style="background:white;border:1px solid #e5e7eb;border-radius:18px;padding:14px 16px;box-shadow:0 16px 40px rgba(0,0,0,0.14);display:flex;gap:12px;align-items:flex-start;">
        <div style="width:40px;height:40px;border-radius:12px;background:linear-gradient(135deg,#16a34a,#059669);display:flex;align-items:center;justify-content:center;flex-shrink:0;font-size:20px;">🅿️</div>
        <div style="flex:1;min-width:0;">
          <p style="font-weight:800;font-size:14px;color:#111827;margin:0 0 2px;">${n.title || 'SpotEasy'}</p>
          <p style="font-size:13px;color:#6b7280;margin:0;line-height:1.4;">${n.body || ''}</p>
        </div>
        <button onclick="this.closest('[style]').remove()" style="background:none;border:none;cursor:pointer;color:#d1d5db;font-size:18px;padding:0;line-height:1;flex-shrink:0;">✕</button>
      </div>`;
    document.body.appendChild(wrap);
    setTimeout(() => wrap.style.opacity = '0', 4500);
    setTimeout(() => wrap.remove(), 5000);
  }
};

// Add toast animation
if (!document.getElementById('se-notif-style')) {
  const s = document.createElement('style');
  s.id = 'se-notif-style';
  s.textContent = '@keyframes seToast{from{transform:translateX(110%);opacity:0}to{transform:translateX(0);opacity:1}}';
  document.head.appendChild(s);
}
