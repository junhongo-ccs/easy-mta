'use strict';

require([
  'esri/Map',
  'esri/views/MapView',
  'esri/Graphic',
  'esri/layers/GraphicsLayer',
], function (Map, MapView, Graphic, GraphicsLayer) {
  const API_URL = '/api/gtfs/realtime/vehicles';
  const POLLING_MS = 30000;
  const DEFAULT_CENTER = [139.7619, 35.6842];
  const DEFAULT_ZOOM = 14;

  const vehicleLayer = new GraphicsLayer();
  const map = new Map({
    basemap: 'streets-navigation-vector',
    layers: [vehicleLayer],
  });

  const view = new MapView({
    container: 'viewDiv',
    map,
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
  });

  const statusEl = document.getElementById('status-indicator');
  const countEl = document.getElementById('count');
  const updatedAtEl = document.getElementById('updated-at');

  function setStatus(connected) {
    if (!statusEl) return;
    statusEl.className = connected ? 'status-dot connected' : 'status-dot error';
    statusEl.title = connected ? '接続中' : '接続エラー';
  }

  function setUpdatedAt(unixSeconds) {
    if (!updatedAtEl) return;
    if (!unixSeconds || !Number.isFinite(Number(unixSeconds))) {
      updatedAtEl.textContent = '更新: --';
      return;
    }
    const date = new Date(Number(unixSeconds) * 1000);
    updatedAtEl.textContent = `更新: ${date.toLocaleTimeString('ja-JP', { hour12: false })}`;
  }

  function toVehicleArray(payload) {
    if (Array.isArray(payload)) return payload;
    if (Array.isArray(payload?.vehicles)) return payload.vehicles;
    return [];
  }

  function toGraphic(vehicle) {
    const lat = Number(vehicle.latitude);
    const lng = Number(vehicle.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return null;
    if (Math.abs(lat) > 90 || Math.abs(lng) > 180) return null;

    const routeLabel = String(vehicle.route_short_name || vehicle.route_id || '-');
    const vehicleId = String(vehicle.vehicle_id || vehicle.id || '-');
    const updated = vehicle.timestamp ? new Date(Number(vehicle.timestamp) * 1000).toLocaleString('ja-JP', { hour12: false }) : '-';
    const destination = String(vehicle.destination || '-');

    return new Graphic({
      geometry: {
        type: 'point',
        longitude: lng,
        latitude: lat,
      },
      attributes: {
        routeLabel,
        vehicleId,
        destination,
        updated,
      },
      symbol: {
        type: 'simple-marker',
        size: 8,
        color: '#1A753F',
        outline: {
          color: '#FFFFFF',
          width: 1,
        },
      },
      popupTemplate: {
        title: '都バス車両',
        content: [
          { type: 'text', text: '系統: {routeLabel}' },
          { type: 'text', text: '行先: {destination}' },
          { type: 'text', text: '車両ID: {vehicleId}' },
          { type: 'text', text: '更新時刻: {updated}' },
        ],
      },
    });
  }

  async function refreshVehicles() {
    try {
      const response = await fetch(API_URL, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const vehicles = toVehicleArray(payload);
      const graphics = vehicles.map(toGraphic).filter(Boolean);

      vehicleLayer.removeAll();
      vehicleLayer.addMany(graphics);

      if (countEl) countEl.textContent = String(graphics.length);
      const latestTs = vehicles.reduce((max, v) => Math.max(max, Number(v.timestamp || v.feed_timestamp || 0)), 0);
      setUpdatedAt(latestTs);
      setStatus(true);
    } catch (error) {
      // Keep current graphics on screen; only report fetch failure.
      console.warn('[arcgis] 車両データ取得失敗:', error);
      setStatus(false);
    }
  }

  view.when(function () {
    refreshVehicles();
    setInterval(refreshVehicles, POLLING_MS);
  });
});
