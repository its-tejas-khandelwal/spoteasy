// SpotEasy Keep-Alive + Silent Auto-Refresh
// Pings /health every 13 minutes silently to prevent Render sleep

(function() {
  // Silent background ping - no page reload ever
  async function silentPing() {
    try {
      const r = await fetch('/health', { cache: 'no-store' });
      const d = await r.json();
      console.log(`[SpotEasy] Keep-alive ping ✅ ${d.time_ist || ''}`);
    } catch(e) {
      console.log('[SpotEasy] Ping failed:', e.message);
    }
  }

  // Ping every 13 minutes
  setInterval(silentPing, 13 * 60 * 1000);
  // First ping after 60 seconds
  setTimeout(silentPing, 60 * 1000);

  // Silent data refresh for dashboards - updates numbers without reload
  window.SpotEasyRefresh = {
    handlers: [],
    register(fn) { this.handlers.push(fn); },
    async run() {
      for (const fn of this.handlers) {
        try { await fn(); } catch(e) {}
      }
    }
  };
  // Run refresh every 30 seconds silently
  setInterval(() => window.SpotEasyRefresh.run(), 30 * 1000);
})();
