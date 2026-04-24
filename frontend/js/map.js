/* global L, CONFIG, ChatManager */
'use strict';

const MapManager = (() => {
  let _map = null;
  let _stopMarkers = {};      // stop_id → L.CircleMarker
  let _vehicleMarkers = {};   // vehicle_id → L.Marker
  let _alertLayer = null;
  let _allStops = [];
  let _allVehicles = [];
  let _activeFilter = null;
  let _activeVehicleFilter = null;
  let _realtimeTimer = null;

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _routeColor(routeId) {
    if (CONFIG.ROUTE_COLORS[routeId]) return CONFIG.ROUTE_COLORS[routeId];
    const text = String(routeId || '?');
    let hash = 0;
    for (let i = 0; i < text.length; i += 1) {
      hash = ((hash << 5) - hash) + text.charCodeAt(i);
      hash |= 0;
    }
    const hue = Math.abs(hash) % 360;
    return `hsl(${hue} 72% 46%)`;
  }

  function _routeTextColor(routeId) {
    return (routeId === '上23' || routeId === '上46' || routeId === '業10') ? '#000' : '#fff';
  }

  function _stopRouteColor(stop) {
    const routes = stop.routes || [];
    if (routes.length === 0) return '#808183';
    return _routeColor(routes[0]);
  }

  function _makePulseIcon(color) {
    return L.divIcon({
      className: '',
      html: `<span class="alert-pulse" style="background:${color};"></span>`,
      iconSize: [20, 20],
      iconAnchor: [10, 10],
    });
  }

  function _makeVehicleIcon(routeId) {
    const color = _routeColor(routeId);
    const textColor = _routeTextColor(routeId);
    const label = String(routeId || '?');
    const width = Math.max(38, Math.min(72, (label.length * 12) + 18));
    return L.divIcon({
      className: '',
      html: `<div class="vehicle-icon" style="background:${color};color:${textColor};" title="${label}">${label}</div>`,
      iconSize: [width, 26],
      iconAnchor: [width / 2, 13],
    });
  }

  function _makeVehicleIconForVehicle(v, highlighted = false) {
    const label = v.route_label || v.route_short_name || v.route_display_name || v.route_id || '?';
    return _makeVehicleIcon(label, highlighted);
  }

  function _stopPopupHTML(stop) {
    const routes = (stop.routes || []);
    const badges = routes.map(r =>
      `<span class="route-badge" style="background:${_routeColor(r)};color:${_routeTextColor(r)}">${r}</span>`
    ).join(' ');
    const accessible = stop.wheelchair_accessible === true
      ? '<span class="accessible-icon" title="バリアフリー">♿</span>'
      : '';
    return `
      <div class="map-popup">
        <div class="popup-name">${stop.stop_name || stop.name || stop.stop_id}</div>
        <div class="popup-routes">${badges}</div>
        ${accessible}
        <div class="popup-id">ID: ${stop.stop_id}</div>
        <button class="popup-btn" onclick="MapManager.getStopInfo('${stop.stop_id}')">詳細を見る</button>
      </div>`;
  }

  function _vehiclePopupHTML(v) {
    const label = v.route_label || v.route_short_name || v.route_id;
    const color = _routeColor(label);
    const textColor = _routeTextColor(label);
    const updated = _formatEpochJst(v.timestamp);
    return `
      <div class="map-popup">
        <div class="popup-name">
          <span class="route-badge" style="background:${color};color:${textColor}">${label}</span>
          ${v.route_display_name || '都バス車両'}
        </div>
        ${v.destination ? `<div class="popup-meta">行先: ${v.destination}</div>` : ''}
        <div class="popup-meta">車両ID: ${v.id}</div>
        <div class="popup-meta">更新: ${updated}</div>
      </div>`;
  }

  function _directionLabel(d) {
    if (d === 0) return '往路';
    if (d === 1) return '復路';
    return '不明';
  }

  function _statusLabel(s) {
    const map = {
      INCOMING_AT: '到着中',
      STOPPED_AT: '停車中',
      IN_TRANSIT_TO: '移動中',
    };
    return map[s] || s || '不明';
  }

  // -------------------------------------------------------------------------
  // Public API
  // -------------------------------------------------------------------------

  function init() {
    _map = L.map('map', {
      center: CONFIG.MAP_CENTER,
      zoom: CONFIG.MAP_ZOOM,
      zoomControl: true,
    });

    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
      attribution: '© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(_map);

    _alertLayer = L.layerGroup().addTo(_map);

    // Load static data then start realtime polling
    _fetchStops();
    _fetchAlerts();
    _startRealtimePolling();
  }

  async function _fetchStops() {
    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/gtfs/stops`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      _allStops = Array.isArray(data) ? data : (data.stops || []);
      loadStops(_allStops);
      _updateStatus(true);
    } catch (e) {
      console.warn('[MapManager] 停留所データ取得失敗:', e);
      _updateStatus(false);
    }
  }

  async function _fetchVehicles() {
    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/gtfs/realtime/vehicles`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const vehicles = Array.isArray(data) ? data : (data.vehicles || data.entity || []);
      _allVehicles = vehicles;
      loadVehicles(vehicles);
      _updateStatus(true);
    } catch (e) {
      console.warn('[MapManager] 車両データ取得失敗:', e);
      _updateStatus(false);
    }
  }

  async function _fetchAlerts() {
    try {
      const res = await fetch(`${CONFIG.API_BASE}/api/gtfs/realtime/alerts`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const alerts = Array.isArray(data) ? data : (data.alerts || data.entity || []);
      loadAlerts(alerts);
    } catch (e) {
      console.warn('[MapManager] アラートデータ取得失敗:', e);
    }
  }

  function _updateStatus(ok) {
    const el = document.getElementById('status-indicator');
    if (!el) return;
    el.className = ok ? 'status-dot connected' : 'status-dot error';
    el.title = ok ? '接続中' : '接続エラー';
  }

  function _formatEpochJst(epoch) {
    if (!epoch) return '--';
    const date = new Date(Number(epoch) * 1000);
    if (Number.isNaN(date.getTime())) return '--';
    return date.toLocaleTimeString('ja-JP', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
      hour12: false,
    });
  }

  function _updateVehicleSummary(vehicles) {
    const countEl = document.getElementById('vehicle-count');
    const feedTimeEl = document.getElementById('feed-time');
    if (countEl) countEl.textContent = String(vehicles.length);
    if (feedTimeEl) {
      const latest = vehicles.reduce((max, v) => Math.max(max, Number(v.timestamp || v.feed_timestamp || 0)), 0);
      feedTimeEl.textContent = `取得時刻: ${_formatEpochJst(latest)}`;
    }
  }

  function loadStops(stops) {
    // Clear existing
    Object.values(_stopMarkers).forEach(m => _map.removeLayer(m));
    _stopMarkers = {};

    stops.forEach(stop => {
      const lat = parseFloat(stop.stop_lat ?? stop.lat);
      const lng = parseFloat(stop.stop_lon ?? stop.lon ?? stop.lng);
      if (isNaN(lat) || isNaN(lng)) return;

      const color = _stopRouteColor(stop);
      const marker = L.circleMarker([lat, lng], {
        radius: 6,
        fillColor: color,
        color: '#fff',
        weight: 1.5,
        opacity: 1,
        fillOpacity: 0.9,
      });

      marker.bindPopup(_stopPopupHTML(stop), { maxWidth: 260 });
      marker.on('click', () => {
        if (window.ChatManager) {
          ChatManager.sendMapContext({ type: 'stop', ...stop });
        }
      });

      marker._stopData = stop;
      marker.addTo(_map);
      _stopMarkers[stop.stop_id] = marker;
    });

    // Re-apply active filter if any
    if (_activeFilter) filterStops(_activeFilter);
  }

  function _normalizeVehicle(v) {
    const entity = v.vehicle || v;
    const pos = entity.position || v.position || v;
    const trip = entity.trip || v.trip || {};
    const lat = parseFloat(pos.latitude ?? pos.lat);
    const lng = parseFloat(pos.longitude ?? pos.lon ?? pos.lng);
    const routeId = trip.route_id || entity.route_id || v.route_id || '?';
    const routeLabel = v.route_short_name || v.route_display_name || routeId;
    const vehicleId = (entity.vehicle || {}).id || entity.id || v.id || v.vehicle_id
      || `${routeId}-${(trip.trip_id || entity.trip_id || v.trip_id || 'unknown').slice(0, 16)}-${lat.toFixed(4)}-${lng.toFixed(4)}`;

    if (isNaN(lat) || isNaN(lng)) return null;

    return {
      id: vehicleId,
      route_id: routeId,
      route_short_name: v.route_short_name,
      route_long_name: v.route_long_name,
      route_display_name: v.route_display_name,
      route_label: routeLabel,
      destination: v.destination,
      pattern_id: v.pattern_id,
      trip_id: trip.trip_id || entity.trip_id || v.trip_id,
      direction_id: trip.direction_id ?? entity.direction_id ?? v.direction_id,
      current_status: entity.current_status || v.current_status,
      timestamp: entity.timestamp || v.timestamp,
      source: v.source,
      lat, lng,
    };
  }

  function _vehicleMatchesFilter(vehicle, filter) {
    if (!filter) return true;
    if (filter.route_short_name && vehicle.route_short_name !== filter.route_short_name) return false;
    if (filter.route_id && vehicle.route_id !== filter.route_id) return false;
    if (filter.destination && vehicle.destination !== filter.destination) return false;
    if (filter.vehicle_ids && !filter.vehicle_ids.includes(vehicle.id)) return false;
    return true;
  }

  function loadVehicles(vehicles) {
    // Remove old vehicle markers
    Object.values(_vehicleMarkers).forEach(m => _map.removeLayer(m));
    _vehicleMarkers = {};

    vehicles.forEach(v => {
      // Normalise nested protobuf-style structure
      const normalized = _normalizeVehicle(v);
      if (!normalized) return;
      if (!_vehicleMatchesFilter(normalized, _activeVehicleFilter)) return;

      const marker = L.marker([normalized.lat, normalized.lng], { icon: _makeVehicleIconForVehicle(normalized) });
      marker._vehicleData = normalized;
      marker.bindPopup(_vehiclePopupHTML(normalized), { maxWidth: 260 });
      marker.on('click', () => {
        if (window.ChatManager) ChatManager.sendMapContext({ type: 'vehicle', ...normalized });
      });
      marker.addTo(_map);
      _vehicleMarkers[normalized.id] = marker;
    });
    const visibleVehicles = Object.values(_vehicleMarkers)
      .map(marker => marker._vehicleData)
      .filter(Boolean);
    _updateVehicleSummary(visibleVehicles);
  }

  function filterVehicles(filter) {
    _activeVehicleFilter = filter;
    loadVehicles(_allVehicles);
  }

  function clearVehicleFilter() {
    _activeVehicleFilter = null;
    loadVehicles(_allVehicles);
  }

  function loadAlerts(alerts) {
    _alertLayer.clearLayers();

    alerts.forEach(alert => {
      const entity = alert.alert || alert;
      const informed = entity.informed_entity || alert.informed_entity || [];
      // Try to find a stop to pin the alert to
      informed.forEach(ie => {
        if (!ie.stop_id) return;
        const stopMarker = _stopMarkers[ie.stop_id];
        if (!stopMarker) return;
        const latlng = stopMarker.getLatLng();
        const pulseMarker = L.marker(latlng, { icon: _makePulseIcon('#FF6319'), zIndexOffset: 500 });
        const headerText = ((entity.header_text || {}).translation || [{}])[0]?.text || 'サービスアラート';
        pulseMarker.bindTooltip(headerText, { permanent: false, direction: 'top' });
        _alertLayer.addLayer(pulseMarker);
      });
    });
  }

  function focusOn(lat, lng, zoom) {
    if (!_map) return;
    _map.flyTo([lat, lng], zoom || 15, { duration: 1.2 });
  }

  function filterStops(filterFn) {
    _activeFilter = filterFn;
    Object.values(_stopMarkers).forEach(marker => {
      const stop = marker._stopData;
      if (!filterFn || filterFn(stop)) {
        if (!_map.hasLayer(marker)) marker.addTo(_map);
      } else {
        if (_map.hasLayer(marker)) _map.removeLayer(marker);
      }
    });
  }

  function highlightStop(stopId) {
    const marker = _stopMarkers[stopId];
    if (!marker) return;
    _map.flyTo(marker.getLatLng(), 16, { duration: 1 });
    marker.openPopup();
    // Briefly flash the marker
    const orig = marker.options.radius;
    marker.setStyle({ radius: 14, weight: 3, color: '#FCCC0A' });
    setTimeout(() => marker.setStyle({ radius: orig, weight: 1.5, color: '#fff' }), 2000);
  }

  function getStopInfo(stopId) {
    const marker = _stopMarkers[stopId];
    if (marker) {
      const stop = marker._stopData;
      if (window.ChatManager) {
        ChatManager.sendMapContext({ type: 'stop', ...stop });
      }
      return stop;
    }
    return null;
  }

  async function refreshRealtime() {
    await Promise.allSettled([_fetchVehicles(), _fetchAlerts()]);
  }

  function _startRealtimePolling() {
    // Initial load
    _fetchVehicles();
    _realtimeTimer = setInterval(() => {
      _fetchVehicles();
      _fetchAlerts();
    }, CONFIG.REALTIME_INTERVAL);
  }

  function getMap() { return _map; }

  return {
    init,
    loadStops,
    loadVehicles,
    loadAlerts,
    focusOn,
    filterStops,
    highlightStop,
    getStopInfo,
    refreshRealtime,
    filterVehicles,
    clearVehicleFilter,
    getMap,
  };
})();

window.MapManager = MapManager;
