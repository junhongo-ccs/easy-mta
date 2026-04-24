/* global L, CONFIG, ChatManager */
'use strict';

const MapManager = (() => {
  let _map = null;
  let _stopMarkers = {};      // stop_id → L.CircleMarker
  let _vehicleMarkers = {};   // vehicle_id → L.Marker
  let _alertLayer = null;
  let _allStops = [];
  let _activeFilter = null;
  let _vehicleCounter = 0;
  let _realtimeTimer = null;

  // -------------------------------------------------------------------------
  // Internal helpers
  // -------------------------------------------------------------------------

  function _routeColor(routeId) {
    return (CONFIG.ROUTE_COLORS[routeId]) || '#808183';
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
    const textColor = (routeId === 'N' || routeId === 'Q' || routeId === 'R' || routeId === 'W') ? '#000' : '#fff';
    return L.divIcon({
      className: '',
      html: `<div class="vehicle-icon" style="background:${color};color:${textColor};" title="${routeId}">${routeId}</div>`,
      iconSize: [24, 24],
      iconAnchor: [12, 12],
    });
  }

  function _stopPopupHTML(stop) {
    const routes = (stop.routes || []);
    const badges = routes.map(r =>
      `<span class="route-badge" style="background:${_routeColor(r)};color:${r === 'N' || r === 'Q' || r === 'R' || r === 'W' ? '#000' : '#fff'}">${r}</span>`
    ).join(' ');
    const accessible = stop.wheelchair_boarding === 1
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
    const color = _routeColor(v.route_id);
    const textColor = (v.route_id === 'N' || v.route_id === 'Q' || v.route_id === 'R' || v.route_id === 'W') ? '#000' : '#fff';
    return `
      <div class="map-popup">
        <div class="popup-name">
          <span class="route-badge" style="background:${color};color:${textColor}">${v.route_id}</span>
          ${v.trip_id ? `列車 ${v.trip_id.slice(0, 12)}…` : '車両'}
        </div>
        <div class="popup-meta">方向: ${_directionLabel(v.direction_id)}</div>
        <div class="popup-meta">状態: ${_statusLabel(v.current_status)}</div>
        <button class="popup-btn" onclick="ChatManager.sendMapContext(${JSON.stringify(v).replace(/"/g, '&quot;')})">AIに質問</button>
      </div>`;
  }

  function _directionLabel(d) {
    if (d === 0) return '下り (South/West)';
    if (d === 1) return '上り (North/East)';
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

  function loadVehicles(vehicles) {
    // Remove old vehicle markers
    Object.values(_vehicleMarkers).forEach(m => _map.removeLayer(m));
    _vehicleMarkers = {};

    vehicles.forEach(v => {
      // Normalise nested protobuf-style structure
      const entity = v.vehicle || v;
      const pos = entity.position || v.position || v;
      const trip = entity.trip || v.trip || {};
      const lat = parseFloat(pos.latitude ?? pos.lat);
      const lng = parseFloat(pos.longitude ?? pos.lon ?? pos.lng);
      const routeId = trip.route_id || entity.route_id || v.route_id || '?';
      const vehicleId = (entity.vehicle || {}).id || entity.id || v.id || v.vehicle_id || `vehicle-${++_vehicleCounter}`;

      if (isNaN(lat) || isNaN(lng)) return;

      const normalized = {
        id: vehicleId,
        route_id: routeId,
        trip_id: trip.trip_id || entity.trip_id || v.trip_id,
        direction_id: trip.direction_id ?? entity.direction_id ?? v.direction_id,
        current_status: entity.current_status || v.current_status,
        lat, lng,
      };

      const marker = L.marker([lat, lng], { icon: _makeVehicleIcon(routeId) });
      marker.bindPopup(_vehiclePopupHTML(normalized), { maxWidth: 260 });
      marker.on('click', () => {
        if (window.ChatManager) ChatManager.sendMapContext({ type: 'vehicle', ...normalized });
      });
      marker.addTo(_map);
      _vehicleMarkers[vehicleId] = marker;
    });
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
    getMap,
  };
})();

window.MapManager = MapManager;
