"""
GTFS static shapes service.
Builds exact route polylines from GTFS files (routes/trips/shapes).
"""

from __future__ import annotations

import csv
import os
from pathlib import Path
from typing import Optional

_CACHE: dict[str, object] = {"key": "", "value": None}


def _gtfs_dir() -> Path:
    configured = os.getenv("GTFS_STATIC_DIR", "").strip()
    if configured:
        return Path(configured)
    return Path(__file__).parent.parent / "data" / "gtfs"


def _read_csv_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def _load_exact_shapes_data() -> dict:
    base = _gtfs_dir()
    routes_path = base / "routes.txt"
    trips_path = base / "trips.txt"
    shapes_path = base / "shapes.txt"
    if not routes_path.is_file() or not trips_path.is_file() or not shapes_path.is_file():
        raise FileNotFoundError(
            f"GTFS files not found in '{base}'. Required: routes.txt, trips.txt, shapes.txt"
        )

    cache_key = str(base.resolve())
    if _CACHE["key"] == cache_key and _CACHE["value"] is not None:
        return _CACHE["value"]  # type: ignore[return-value]

    routes = _read_csv_rows(routes_path)
    trips = _read_csv_rows(trips_path)
    shapes = _read_csv_rows(shapes_path)

    route_meta: dict[str, dict] = {}
    for row in routes:
        route_id = str(row.get("route_id") or "").strip()
        if not route_id:
            continue
        route_meta[route_id] = {
            "route_id": route_id,
            "route_short_name": str(row.get("route_short_name") or "").strip(),
            "route_long_name": str(row.get("route_long_name") or "").strip(),
            "route_color": str(row.get("route_color") or "").strip(),
        }

    route_to_shapes: dict[str, set[str]] = {}
    for row in trips:
        route_id = str(row.get("route_id") or "").strip()
        shape_id = str(row.get("shape_id") or "").strip()
        if not route_id or not shape_id:
            continue
        route_to_shapes.setdefault(route_id, set()).add(shape_id)

    shape_points: dict[str, list[tuple[int, float, float]]] = {}
    for row in shapes:
        shape_id = str(row.get("shape_id") or "").strip()
        if not shape_id:
            continue
        try:
            lat = float(row["shape_pt_lat"])
            lon = float(row["shape_pt_lon"])
            seq = int(float(row["shape_pt_sequence"]))
        except (KeyError, TypeError, ValueError):
            continue
        if abs(lat) > 90 or abs(lon) > 180:
            continue
        shape_points.setdefault(shape_id, []).append((seq, lon, lat))

    for shape_id, points in shape_points.items():
        points.sort(key=lambda x: x[0])
        shape_points[shape_id] = points

    data = {
        "route_meta": route_meta,
        "route_to_shapes": route_to_shapes,
        "shape_points": shape_points,
    }
    _CACHE["key"] = cache_key
    _CACHE["value"] = data
    return data


def get_exact_route_shapes_geojson(route_filters: Optional[list[str]] = None) -> dict:
    data = _load_exact_shapes_data()
    route_meta: dict[str, dict] = data["route_meta"]  # type: ignore[assignment]
    route_to_shapes: dict[str, set[str]] = data["route_to_shapes"]  # type: ignore[assignment]
    shape_points: dict[str, list[tuple[int, float, float]]] = data["shape_points"]  # type: ignore[assignment]

    filters = {f.strip() for f in (route_filters or []) if f.strip()}
    features: list[dict] = []
    for route_id, shape_ids in route_to_shapes.items():
        meta = route_meta.get(route_id, {"route_id": route_id})
        short_name = str(meta.get("route_short_name") or "")
        if filters and route_id not in filters and short_name not in filters:
            continue
        for shape_id in sorted(shape_ids):
            points = shape_points.get(shape_id, [])
            if len(points) < 2:
                continue
            coords = [[lon, lat] for _, lon, lat in points]
            features.append({
                "type": "Feature",
                "id": f"exact-{route_id}-{shape_id}",
                "geometry": {"type": "LineString", "coordinates": coords},
                "properties": {
                    "route_id": route_id,
                    "route_short_name": short_name,
                    "route_long_name": meta.get("route_long_name"),
                    "route_color": meta.get("route_color"),
                    "shape_id": shape_id,
                    "point_count": len(coords),
                    "path_type": "gtfs-shapes-exact",
                },
            })
    return {"type": "FeatureCollection", "features": features}
