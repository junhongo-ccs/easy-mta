/* global MapManager, ChatManager, CONFIG */
'use strict';

document.addEventListener('DOMContentLoaded', () => {
  // ── Initialize core modules ──────────────────────────────────────────────
  try {
    MapManager.init();
  } catch (e) {
    console.error('[都バスPoC] 地図の初期化に失敗しました:', e);
    const status = document.getElementById('status-indicator');
    if (status) {
      status.className = 'status-dot error';
      status.title = '地図の初期化に失敗しました';
    }
  }
  try {
    ChatManager.init();
  } catch (e) {
    console.error('[都バスPoC] チャットの初期化に失敗しました:', e);
  }

  // ── Chat input wiring ────────────────────────────────────────────────────
  const input = document.getElementById('chat-input');
  const sendBtn = document.getElementById('send-btn');
  if (!input || !sendBtn) {
    console.error('[都バスPoC] チャットUI要素が見つかりません: #chat-input または #send-btn');
    return;
  }

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

  // ── Refresh real-time data button ────────────────────────────────────────
  const refreshBtn = document.getElementById('refresh-btn');
  if (refreshBtn) {
    refreshBtn.addEventListener('click', async () => {
      refreshBtn.classList.add('spinning');
      refreshBtn.disabled = true;
      try {
        await MapManager.refreshRealtime();
      } finally {
        refreshBtn.classList.remove('spinning');
        refreshBtn.disabled = false;
      }
    });
  }

  // Note: MapManager already starts its own real-time polling interval
  // internally via _startRealtimePolling(). No duplicate timer needed here.

  // ── Legend toggle ────────────────────────────────────────────────────────
  const legendToggle = document.getElementById('legend-toggle');
  const legend = document.getElementById('route-legend');
  if (legendToggle && legend) {
    legendToggle.addEventListener('click', () => {
      legend.classList.toggle('hidden');
      legendToggle.textContent = legend.classList.contains('hidden') ? '概要 ▲' : '概要 ▼';
    });
  }

  // ── Vehicle display reset button ─────────────────────────────────────────
  const showAllBusesBtn = document.getElementById('show-all-buses-btn');
  if (showAllBusesBtn) {
    showAllBusesBtn.addEventListener('click', () => {
      if (MapManager.clearVehicleFilter) MapManager.clearVehicleFilter();
      if (ChatManager.showCommandNotice) ChatManager.showCommandNotice('すべての車両を表示中');
    });
  }
});
