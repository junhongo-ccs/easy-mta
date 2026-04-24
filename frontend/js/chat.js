/* global CONFIG, MapManager */
'use strict';

const ChatManager = (() => {
  let _conversationId = null;
  let _isTyping = false;

  const WELCOME_MESSAGE =
    'こんにちは！🗽 **Easy MTA** へようこそ！\n\n' +
    '私はニューヨーク地下鉄のAIアシスタントです。\n\n' +
    '**できること:**\n' +
    '- 駅情報や路線の案内\n' +
    '- リアルタイム運行状況の説明\n' +
    '- 地図の操作（「タイムズスクエア駅を表示して」等）\n' +
    '- バリアフリー情報のご案内\n\n' +
    '地図上の駅や列車をクリックすると、その情報を日本語でお伝えします！\n\n' +
    '何でもお気軽にどうぞ 😊';

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _el(id) { return document.getElementById(id); }

  function _formatTime(date) {
    return `${date.getHours().toString().padStart(2, '0')}:${date.getMinutes().toString().padStart(2, '0')}`;
  }

  function _scrollToBottom() {
    const area = _el('chat-messages');
    if (area) area.scrollTop = area.scrollHeight;
  }

  function _extractMapCommand(text) {
    // Try ```json ... ``` blocks first
    const jsonBlock = text.match(/```json\s*([\s\S]*?)```/i);
    if (jsonBlock) {
      try {
        const cmd = JSON.parse(jsonBlock[1].trim());
        if (cmd && cmd.type) return cmd;
      } catch (_) { /* ignore */ }
    }
    // Try raw JSON object with a "type" field
    const rawJson = text.match(/\{[^{}]*"type"\s*:[^{}]*\}/);
    if (rawJson) {
      try {
        const cmd = JSON.parse(rawJson[0]);
        if (cmd && cmd.type) return cmd;
      } catch (_) { /* ignore */ }
    }
    return null;
  }

  function _stripMapCommandBlock(text) {
    return text.replace(/```json\s*[\s\S]*?```/gi, '').trim();
  }

  // Basic markdown-like → HTML
  function formatMessage(text) {
    // Escape HTML
    let safe = text
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');

    // Bold **text**
    safe = safe.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
    // Italic *text*
    safe = safe.replace(/\*(.+?)\*/g, '<em>$1</em>');
    // Bullet list lines starting with - or •
    const lines = safe.split('\n');
    const out = [];
    let inList = false;
    for (const line of lines) {
      const bullet = line.match(/^[-•]\s+(.*)/);
      if (bullet) {
        if (!inList) { out.push('<ul>'); inList = true; }
        out.push(`<li>${bullet[1]}</li>`);
      } else {
        if (inList) { out.push('</ul>'); inList = false; }
        out.push(line === '' ? '<br>' : `<span>${line}</span><br>`);
      }
    }
    if (inList) out.push('</ul>');
    return out.join('');
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  function init() {
    addMessage('assistant', WELCOME_MESSAGE);
  }

  function addMessage(role, text) {
    const area = _el('chat-messages');
    if (!area) return;

    // Remove typing indicator if present
    const typing = area.querySelector('.typing-indicator');
    if (typing) typing.remove();

    const wrapper = document.createElement('div');
    wrapper.className = `message ${role === 'user' ? 'message-user' : 'message-bot'}`;

    const bubble = document.createElement('div');
    bubble.className = 'message-bubble';
    bubble.innerHTML = formatMessage(text);

    const time = document.createElement('div');
    time.className = 'message-time';
    time.textContent = _formatTime(new Date());

    wrapper.appendChild(bubble);
    wrapper.appendChild(time);
    area.appendChild(wrapper);
    _scrollToBottom();
  }

  function showTyping() {
    if (_isTyping) return;
    _isTyping = true;
    const area = _el('chat-messages');
    if (!area) return;
    const el = document.createElement('div');
    el.className = 'message message-bot typing-indicator';
    el.innerHTML = `<div class="message-bubble typing-bubble"><span></span><span></span><span></span></div>`;
    area.appendChild(el);
    _scrollToBottom();
  }

  function hideTyping() {
    _isTyping = false;
    const el = document.querySelector('.typing-indicator');
    if (el) el.remove();
  }

  async function sendMessage(text) {
    const trimmed = (text || '').trim();
    if (!trimmed) return;

    addMessage('user', trimmed);
    showTyping();

    const body = {
      message: trimmed,
      conversation_id: _conversationId || undefined,
      inputs: {},
    };

    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/chat/message`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const data = await res.json();
      hideTyping();
      handleResponse(data);
    } catch (e) {
      hideTyping();
      addMessage('assistant', `⚠️ エラーが発生しました: ${e.message}\n\nもう一度お試しください。`);
    }
  }

  function sendMapContext(context) {
    const typeLabel = context.type === 'stop' ? '駅' : '列車';
    const name = context.stop_name || context.name || context.id || JSON.stringify(context);
    const prompt = `この${typeLabel}について日本語で教えてください: **${name}**`;

    // Add user-visible message
    addMessage('user', prompt);
    showTyping();

    const body = {
      message: prompt,
      conversation_id: _conversationId || undefined,
      inputs: {},
      map_context: context,
    };

    fetch(`${CONFIG.API_BASE}/api/chat/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(res => {
        if (!res.ok) return res.json().then(e => { throw new Error(e.detail || `HTTP ${res.status}`); });
        return res.json();
      })
      .then(data => {
        hideTyping();
        handleResponse(data);
      })
      .catch(e => {
        hideTyping();
        addMessage('assistant', `⚠️ エラーが発生しました: ${e.message}`);
      });
  }

  function handleResponse(response) {
    if (response.conversation_id) {
      _conversationId = response.conversation_id;
    }

    let answer = response.answer || '';

    // Try map_command from dedicated field first, then parse from answer text
    const mapCmd = response.map_command || _extractMapCommand(answer);
    if (mapCmd) {
      executeMapCommand(mapCmd);
      answer = _stripMapCommandBlock(answer);
    }

    if (answer) addMessage('assistant', answer);
  }

  function executeMapCommand(cmd) {
    if (!cmd || !cmd.type) return;
    if (!window.MapManager) return;

    switch (cmd.type) {
      case 'focusOn':
        MapManager.focusOn(cmd.lat, cmd.lng, cmd.zoom);
        break;
      case 'filterAccessible':
        MapManager.filterStops(stop => stop.wheelchair_accessible === true);
        _showCommandNotice('♿ バリアフリー駅のみ表示中');
        break;
      case 'highlightStop':
        MapManager.highlightStop(cmd.stop_id);
        break;
      case 'showRoute':
        MapManager.filterStops(stop =>
          (stop.routes || []).includes(cmd.route_id)
        );
        _showCommandNotice(`🚇 ${cmd.route_id} 路線の駅を表示中`);
        break;
      case 'resetFilters':
        MapManager.filterStops(null);
        _showCommandNotice('🗺️ すべての駅を表示中');
        break;
      default:
        console.warn('[ChatManager] 不明なマップコマンド:', cmd);
    }
  }

  let _commandNoticeTimer = null;

  function _showCommandNotice(text) {
    const badge = document.getElementById('map-command-notice');
    if (!badge) return;
    badge.textContent = text;
    badge.classList.add('visible');
    clearTimeout(_commandNoticeTimer);
    _commandNoticeTimer = setTimeout(() => badge.classList.remove('visible'), 4000);
  }

  return {
    init,
    sendMessage,
    sendMapContext,
    handleResponse,
    executeMapCommand,
    addMessage,
    showTyping,
    hideTyping,
    formatMessage,
  };
})();

window.ChatManager = ChatManager;
