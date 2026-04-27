/* global CONFIG, MapManager */
'use strict';

const ChatManager = (() => {
  let _conversationId = null;
  let _isTyping = false;
  let _lastMapContext = null;

  const WELCOME_MESSAGES = [
    '**都バス運行案内サイト PoC** です。',
    '試せる質問:\n\n' +
    '「東京駅周辺に移動して」\n' +
    '「新宿駅西口 行のバスを表示して」\n' +
    '「都05-1だけ表示して」\n' +
    '「銀座四丁目に接近中のバス」\n' +
    '「絞り込みを解除して」',
    '停留所や車両をクリックすると、その情報をもとに続けて質問できます。',
    'バス表示は、上部の「全バスを表示」ボタンで元に戻ります。',
  ];

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

  function _sanitizeUserFacingAnswer(text) {
    if (!text) return text;
    const withoutInternalStopId = text
      .replace(/(?:^|\n)[-•]?\s*停留所ID\s*[:：]\s*[^\n]*/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim();
    return withoutInternalStopId;
  }

  function _extractVehicleIds(text) {
    const ids = new Set();
    const patterns = [
      /(?:車両ID|バスID)\s*[:：]?\s*([A-Z]\d{2,4})/g,
    ];
    patterns.forEach(pattern => {
      let match;
      while ((match = pattern.exec(text)) !== null) {
        ids.add(match[1]);
      }
    });
    return Array.from(ids);
  }

  function _hasExplicitContextReference(text, contextType) {
    if (contextType === 'vehicle') {
      return /(このバス|この車両|この便|選択したバス|選択中のバス|同じバス|同じ車両|この系統)/.test(text);
    }
    if (contextType === 'stop') {
      return /(この停留所|このバス停|選択した停留所|選択中の停留所|同じ停留所|ここ)/.test(text);
    }
    return false;
  }

  function _isBroadNearbySearch(text) {
    return /(周辺|近く|付近|最寄|周り|周囲|一覧|ほか|他の|別の|探して|教えて|表示して).*(バス|車両|停留所)|((駅|停留所|バス停).*(周辺|近く|付近))/.test(text);
  }

  function _normalizeForLooseMatch(value) {
    return String(value || '')
      .replace(/\s+/g, '')
      .replace(/(停留所|バス停)/g, '')
      .trim();
  }

  function _mentionsVehicleContextPlace(text, context) {
    if (!context || context.type !== 'vehicle') return false;
    const normalizedText = _normalizeForLooseMatch(text);
    const candidates = [
      context.next_stop_name,
      context.current_stop_name,
      context.stop_name,
      context.destination,
    ]
      .map(_normalizeForLooseMatch)
      .filter(name => name && name.length >= 2);

    return candidates.some(name => normalizedText.includes(name));
  }

  function _shouldAttachLastMapContext(text) {
    if (!_lastMapContext) return false;
    if (_hasExplicitContextReference(text, _lastMapContext.type)) return true;
    if (_mentionsVehicleContextPlace(text, _lastMapContext) && /(周辺|近く|付近|最寄|周り|周囲|探して|教えて|表示して)/.test(text)) {
      return true;
    }
    if (_isBroadNearbySearch(text)) return false;

    if (_lastMapContext.type === 'stop') {
      return /接近|到着|何分|次のバス|時刻|同じ停留所|一番近|最も近|最寄|近い/.test(text);
    }
    if (_lastMapContext.type === 'vehicle') {
      return /同じ|系統|行先|行き先|現在地|どこを走|次の停留所|遅延|何分/.test(text);
    }
    return false;
  }

  function _contextKey(context) {
    if (!context || !context.type) return null;
    const id = context.id || context.vehicle_id || context.stop_id || context.name;
    return id ? `${context.type}:${id}` : null;
  }

  function _applyVehicleIdFilter(vehicleIds, options = {}) {
    if (!window.MapManager?.filterVehicles) return;
    const ids = Array.isArray(vehicleIds) ? vehicleIds.filter(Boolean) : [];

    const applyFilter = () => {
      MapManager.filterVehicles({ vehicle_ids: ids });
      const visible = MapManager.getVisibleVehicleCount ? MapManager.getVisibleVehicleCount() : ids.length;
      const notice = visible === ids.length
        ? `${visible}台の車両だけ表示中`
        : `${ids.length}台中${visible}台を表示中`;
      _showCommandNotice(notice);
      if (typeof options.lat === 'number' && typeof options.lng === 'number') {
        MapManager.focusOn(options.lat, options.lng, options.zoom || 15);
      }
    };

    if (MapManager.refreshRealtime) {
      MapManager.refreshRealtime().finally(applyFilter);
      return;
    }
    applyFilter();
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
    WELCOME_MESSAGES.forEach(message => addMessage('assistant', message));
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
    if (_shouldAttachLastMapContext(trimmed)) {
      body.map_context = _lastMapContext;
    }

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
    const currentKey = _contextKey(context);
    if (context.type === 'vehicle' && currentKey && currentKey === _contextKey(_lastMapContext)) {
      if (window.MapManager?.clearVehicleFilter) {
        MapManager.clearVehicleFilter();
      }
      _lastMapContext = null;
      _showCommandNotice('すべての車両を表示中');
      return;
    }

    _lastMapContext = context;

    const typeLabel = context.type === 'stop' ? '停留所' : '車両';
    const name = context.route_display_name || context.stop_name || context.name || context.id || JSON.stringify(context);
    const prompt = `この${typeLabel}について教えてください: **${name}**`;

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

    const vehicleIds = _extractVehicleIds(answer);
    if (vehicleIds.length > 0 && window.MapManager?.filterVehicles) {
      _applyVehicleIdFilter(vehicleIds);
    }

    answer = _sanitizeUserFacingAnswer(answer);
    if (answer) addMessage('assistant', answer);
  }

  function executeMapCommand(cmd) {
    if (!cmd || !cmd.type) return;
    if (!window.MapManager) return;

    switch (cmd.type) {
      case 'focusOn':
        MapManager.focusOn(cmd.lat, cmd.lng, cmd.zoom, { preserveZoom: cmd.preserve_zoom === true });
        break;
      case 'filterAccessible':
        MapManager.filterStops(stop => stop.wheelchair_accessible === true);
        _showCommandNotice('バリアフリー停留所のみ表示中');
        break;
      case 'highlightStop':
        MapManager.highlightStop(cmd.stop_id);
        break;
      case 'showRoute':
        MapManager.filterStops(stop =>
          (stop.routes || []).includes(cmd.route_id)
        );
        _showCommandNotice(`${cmd.route_id} 系統の停留所を表示中`);
        break;
      case 'resetFilters':
        MapManager.filterStops(null);
        if (MapManager.clearVehicleFilter) MapManager.clearVehicleFilter();
        _showCommandNotice('すべての停留所を表示中');
        break;
      case 'filterVehiclesByRoute':
        if (MapManager.filterVehicles) {
          MapManager.filterVehicles({
            route_short_name: cmd.route_short_name,
            route_id: cmd.route_id,
            destination: cmd.destination,
          });
          _showCommandNotice(`${cmd.destination ? `${cmd.destination} 行` : (cmd.route_short_name || cmd.route_id || '指定')} の車両を表示中`);
        }
        break;
      case 'filterVehiclesByIds':
        if (MapManager.closePopups) {
          MapManager.closePopups();
        }
        _applyVehicleIdFilter(cmd.vehicle_ids || [], { lat: cmd.lat, lng: cmd.lng, zoom: cmd.zoom });
        break;
      case 'resetVehicleFilters':
        if (MapManager.clearVehicleFilter) {
          MapManager.clearVehicleFilter();
          _showCommandNotice('すべての車両を表示中');
        }
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
    reset() {
      _conversationId = null;
      _lastMapContext = null;
      _isTyping = false;
      hideTyping();
      init();
    },
    sendMessage,
    sendMapContext,
    handleResponse,
    executeMapCommand,
    addMessage,
    showTyping,
    hideTyping,
    showCommandNotice: _showCommandNotice,
    formatMessage,
  };
})();

window.ChatManager = ChatManager;
