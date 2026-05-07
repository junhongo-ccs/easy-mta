'use strict';

require([
  'esri/Map',
  'esri/views/MapView',
  'esri/layers/GeoJSONLayer',
], function (Map, MapView, GeoJSONLayer) {
  const DEFAULT_CENTER = [139.7619, 35.6842];
  const DEFAULT_ZOOM = 13;
  const REFRESH_MINUTES = 0.5; // 30 seconds

  const params = new URLSearchParams(window.location.search);
  const routes = params.get('routes');
  const routeSuffix = routes ? `?routes=${encodeURIComponent(routes)}` : '';
  const layerUrl = `/api/gtfs/realtime/vehicles.geojson${routeSuffix}`;

  const routeFilterEl = document.getElementById('route-filter');
  const layerUrlEl = document.getElementById('layer-url');
  if (routeFilterEl) routeFilterEl.textContent = `系統: ${routes || '全件'}`;
  if (layerUrlEl) layerUrlEl.textContent = `Layer URL: ${layerUrl}`;

  const layer = new GeoJSONLayer({
    url: layerUrl,
    refreshInterval: REFRESH_MINUTES,
    title: '都バス車両（リアルタイム）',
    renderer: {
      type: 'simple',
      symbol: {
        type: 'simple-marker',
        size: 8,
        color: '#0a7a33',
        outline: {
          color: '#ffffff',
          width: 1,
        },
      },
    },
    popupTemplate: {
      title: '{route_label} {vehicle_id}',
      content: [
        { type: 'text', text: '系統: {route_label}' },
        { type: 'text', text: '行先: {destination}' },
        { type: 'text', text: '車両ID: {vehicle_id}' },
        { type: 'text', text: '更新時刻(UNIX): {timestamp}' },
      ],
    },
  });

  const map = new Map({
    basemap: 'gray-vector',
    layers: [layer],
  });

  new MapView({
    container: 'viewDiv',
    map,
    center: DEFAULT_CENTER,
    zoom: DEFAULT_ZOOM,
  });
});
