{% extends "base.html" %}
{% block title %}Send Notifications — SpotEasy{% endblock %}
{% block content %}
<div class="max-w-2xl mx-auto">
  <div class="mb-6">
    <a href="{{ url_for('admin_dashboard') }}" class="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700 dark:hover:text-gray-300 mb-3">
      <i data-lucide="arrow-left" class="w-4 h-4"></i> Back to Admin
    </a>
    <h1 class="text-3xl font-black text-gray-900 dark:text-white">Push Notifications</h1>
    <p class="text-gray-500 dark:text-gray-400 text-sm mt-1">
      {{ users|length }} user(s) have notifications enabled
    </p>
  </div>

  <div class="card shadow-xl animate-scale-in">
    <form method="POST" class="space-y-5">
      <div>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">Send To</label>
        <select name="user_id" class="inp">
          <option value="all">📢 All Users ({{ users|length }} enabled)</option>
          {% for u in all_users %}
          <option value="{{ u.id }}">{{ u.name }} — {{ u.email }} ({{ u.role }})</option>
          {% endfor %}
        </select>
      </div>
      <div>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">Notification Title</label>
        <input type="text" name="title" required maxlength="60" placeholder="e.g. 🅿️ New Parking Lot Added!"
               class="inp"/>
      </div>
      <div>
        <label class="block text-sm font-bold text-gray-700 dark:text-gray-300 mb-1.5">Message</label>
        <textarea name="body" required maxlength="200" rows="3"
                  placeholder="e.g. A new parking lot near Connaught Place is now live. Book your slot!"
                  class="inp resize-none"></textarea>
      </div>

      <!-- Quick Templates -->
      <div>
        <p class="text-xs font-bold text-gray-500 dark:text-gray-400 mb-2">Quick Templates:</p>
        <div class="flex flex-wrap gap-2">
          {% for t in [
            ('New Lot', '🅿️ New Parking Lot Added!', 'A new parking lot is now live near you. Book your slot today!'),
            ('Offer', '🎉 Special Offer!', 'Get 20% off on your next parking. Valid today only!'),
            ('Reminder', '⏰ Parking Reminder', 'You have an active parking booking. Don\'t forget to checkout!'),
          ] %}
          <button type="button"
            onclick="document.querySelector('[name=title]').value='{{ t[1] }}';document.querySelector('[name=body]').value='{{ t[2] }}';"
            class="text-xs bg-gray-100 dark:bg-dark-800 hover:bg-green-100 dark:hover:bg-green-900/30 text-gray-600 dark:text-gray-300 px-3 py-1.5 rounded-xl font-semibold transition-all hover:scale-105">
            {{ t[0] }}
          </button>
          {% endfor %}
        </div>
      </div>

      <button type="submit" class="btn-primary w-full py-3.5 rounded-2xl flex items-center justify-center gap-2">
        <i data-lucide="send" class="w-4 h-4"></i> Send Notification
      </button>
    </form>
  </div>

  <!-- Users with notifications enabled -->
  <div class="card mt-5 animate-on-scroll">
    <h3 class="font-bold text-sm text-gray-500 dark:text-gray-400 uppercase tracking-wider mb-4">
      Users with Notifications Enabled ({{ users|length }})
    </h3>
    {% if users %}
    <div class="space-y-2">
      {% for u in users %}
      <div class="flex items-center justify-between p-3 rounded-xl bg-gray-50 dark:bg-dark-800">
        <div class="flex items-center gap-3">
          <div class="w-8 h-8 rounded-xl bg-gradient-to-br from-green-400 to-emerald-600 flex items-center justify-center text-white text-sm font-bold">
            {{ u.name[0].upper() }}
          </div>
          <div>
            <p class="text-sm font-semibold text-gray-900 dark:text-white">{{ u.name }}</p>
            <p class="text-xs text-gray-400">{{ u.email }}</p>
          </div>
        </div>
        <span class="text-green-500 text-xs font-bold">🔔 ON</span>
      </div>
      {% endfor %}
    </div>
    {% else %}
    <p class="text-gray-400 text-sm text-center py-6">No users have enabled notifications yet.</p>
    {% endif %}
  </div>
</div>
{% endblock %}
