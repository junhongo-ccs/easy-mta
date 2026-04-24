/* global MapManager, ChatManager, CONFIG */
'use strict';

document.addEventListener('DOMContentLoaded', () => {
  // ── Initialize core modules ──────────────────────────────────────────────
  MapManager.init();
  ChatManager.init();

  // ── Chat input wiring ────────────────────────────────────────────────────
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');

  function submitChat() {
    const text = input.value.trim();
    if (!text) return;
    input.value = '';
    input.style.height = 'auto';
    ChatManager.sendMessage(text);
  }

  sendBtn.addEventListener('click', submitChat);

  input.addEventListener('keydown', e => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      submitChat();
    }
  });

  // Auto-grow textarea
  input.addEventListener('input', () => {
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 120) + 'px';
  });

  // ── Accessibility filter button ──────────────────────────────────────────
  const accessBtn = document.getElementById('accessibility-btn');
  let accessActive = false;

  if (accessBtn) {
    accessBtn.addEventListener('click', () => {
      accessActive = !accessActive;
      if (accessActive) {
        MapManager.filterStops(stop =>
          stop.wheelchair_boarding === 1 || stop.wheelchair_accessible === true
        );
        accessBtn.classList.add('active');
        accessBtn.title = 'バリアフリーフィルター解除';
      } else {
        MapManager.filterStops(null);
        accessBtn.classList.remove('active');
        accessBtn.title = 'バリアフリー駅のみ表示';
      }
    });
  }

  // ── Refresh real-time data button ────────────────────────────────────────
  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.classList.add('spinning');
      refreshBtn.disabled = true;
      await MapManager.refreshRealtime();
      refreshBtn.classList.remove('spinning');
      refreshBtn.disabled = false;
    });
  }

  // ── Periodic real-time refresh ───────────────────────────────────────────
  // MapManager handles its own polling, but we keep the status indicator
  // in sync with a lightweight heartbeat here.
  setInterval(() => {
    MapManager.refreshRealtime();
  }, CONFIG.REALTIME_INTERVAL);

  // ── Legend toggle ────────────────────────────────────────────────────────
  const legendToggle = document.getElementById('legend-toggle');
  const legend = document.getElementById('route-legend');
  if (legendToggle && legend) {
    legendToggle.addEventListener('click', () => {
      legend.classList.toggle('hidden');
      legendToggle.textContent = legend.classList.contains('hidden') ? '凡例 ▲' : '凡例 ▼';
    });
  }

  // ── New conversation button ───────────────────────────────────────────────
  const newChatBtn = document.getElementById('new-chat-btn');
  if (newChatBtn) {
    newChatBtn.addEventListener('click', () => {
      const area = document.getElementById('chat-messages');
      if (area) area.innerHTML = '';
      ChatManager.init();
    });
  }
});
