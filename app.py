{% extends "base.html" %}
{% block title %}Login — SpotEasy{% endblock %}
{% block content %}
<div class="min-h-[70vh] flex items-center justify-center py-8">
  <div class="w-full max-w-md animate-scale-in">
    <div class="text-center mb-8">
      <div class="w-16 h-16 rounded-2xl bg-gradient-to-br from-green-500 to-emerald-600 flex items-center justify-center mx-auto mb-4 shadow-xl hover:scale-110 transition-transform">
        <i data-lucide="parking-circle" class="w-8 h-8 text-white"></i>
      </div>
      <h1 class="text-3xl font-black text-gray-900 dark:text-white">Welcome back</h1>
      <p class="text-gray-500 dark:text-gray-400 mt-1">Sign in to SpotEasy India</p>
    </div>
    <div class="card shadow-2xl">
      <form method="POST" id="loginForm" novalidate class="space-y-4">

        <div>
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">Email Address</label>
          <input type="email" name="email" id="loginEmail" required
                 placeholder="you@example.com" class="inp" autocomplete="email"/>
          <p id="loginEmailErr" class="text-red-500 text-xs mt-1 hidden">Enter a valid email address.</p>
        </div>

        <div>
          <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">Password</label>
          <div class="relative">
            <input type="password" name="password" id="loginPw" required
                   placeholder="Your password" class="inp pr-10" autocomplete="current-password"/>
            <button type="button" onclick="togglePw()"
              class="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 dark:hover:text-gray-200">
              <i data-lucide="eye" class="w-4 h-4" id="eyeLogin"></i>
            </button>
          </div>
          <p id="loginPwErr" class="text-red-500 text-xs mt-1 hidden">Password cannot be empty.</p>
        </div>

        <!-- Rate limiting notice -->
        <div id="rateLimitNotice" class="hidden bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl px-4 py-3 text-sm text-red-700 dark:text-red-300">
          ⚠️ Too many failed attempts. Please wait <span id="countdown">30</span>s before trying again.
        </div>

        <button type="submit" id="loginBtn"
          class="btn-primary w-full py-3.5 text-base rounded-2xl mt-2">
          Sign In →
        </button>
      </form>

      <div class="mt-6 pt-5 border-t border-gray-100 dark:border-dark-700 text-center text-sm text-gray-500">
        Don't have an account?
        <a href="{{ url_for('register') }}" class="text-green-600 dark:text-green-400 font-bold hover:underline ml-1">Register free</a>
      </div>
      <div class="mt-3 bg-gray-50 dark:bg-dark-800 rounded-xl p-3 text-xs text-gray-400 dark:text-gray-500">
        <strong class="text-gray-500 dark:text-gray-400">Demo Admin:</strong>
        admin@spoteasy.in · Set password in Render environment
      </div>
    </div>
  </div>
</div>
{% endblock %}

{% block scripts %}
<script>
// Show/hide password
function togglePw() {
  const f = document.getElementById('loginPw');
  const i = document.getElementById('eyeLogin');
  f.type = f.type === 'password' ? 'text' : 'password';
  i.setAttribute('data-lucide', f.type === 'password' ? 'eye' : 'eye-off');
  lucide.createIcons();
}

// Client-side rate limiting (3 failed attempts = 30s lockout)
let attempts = parseInt(sessionStorage.getItem('loginAttempts') || '0');
let lockUntil = parseInt(sessionStorage.getItem('lockUntil') || '0');

function checkLock() {
  if (Date.now() < lockUntil) {
    const btn = document.getElementById('loginBtn');
    const notice = document.getElementById('rateLimitNotice');
    btn.disabled = true;
    btn.classList.add('opacity-50','cursor-not-allowed');
    notice.classList.remove('hidden');
    const timer = setInterval(() => {
      const left = Math.ceil((lockUntil - Date.now()) / 1000);
      if (left <= 0) {
        clearInterval(timer);
        btn.disabled = false;
        btn.classList.remove('opacity-50','cursor-not-allowed');
        notice.classList.add('hidden');
        attempts = 0;
        sessionStorage.removeItem('loginAttempts');
        sessionStorage.removeItem('lockUntil');
      } else {
        document.getElementById('countdown').textContent = left;
      }
    }, 1000);
    return true;
  }
  return false;
}
checkLock();

document.getElementById('loginForm').addEventListener('submit', function(e) {
  if (checkLock()) { e.preventDefault(); return; }

  const email = document.getElementById('loginEmail').value.trim();
  const pw    = document.getElementById('loginPw').value;
  let ok = true;

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    document.getElementById('loginEmailErr').classList.remove('hidden'); ok = false;
  } else document.getElementById('loginEmailErr').classList.add('hidden');

  if (!pw) {
    document.getElementById('loginPwErr').classList.remove('hidden'); ok = false;
  } else document.getElementById('loginPwErr').classList.add('hidden');

  if (!ok) { e.preventDefault(); return; }

  // Track attempts for rate limiting (incremented on page reload after 401)
  attempts++;
  sessionStorage.setItem('loginAttempts', attempts);
  if (attempts >= 3) {
    lockUntil = Date.now() + 30000;
    sessionStorage.setItem('lockUntil', lockUntil);
  }
});

// Reset attempts on successful load with no flash error
{% if not get_flashed_messages() %}
sessionStorage.removeItem('loginAttempts');
{% endif %}
</script>
{% endblock %}
