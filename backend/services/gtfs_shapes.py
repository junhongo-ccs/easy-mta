"""
GTFS static shapes service.
Builds exact route polylines from GTFS files (routes/trips/shapes).
"""

from __future__ import annotations

import csv
import math
import os
from pathlib import Path
from typing import Optional

_CACHE: dict[str, object] = {"key": "", "value": None}
_MAX_SEGMENT_METERS = 900.0


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
    route_shape_trip_counts: dict[str, dict[str, int]] = {}
    route_shape_direction_counts: dict[str, dict[str, dict[str, int]]] = {}
    for row in trips:
        route_id = str(row.get("route_id") or "").strip()
        shape_id = str(row.get("shape_id") or "").strip()
        if not route_id or not shape_id:
            continue
        route_to_shapes.setdefault(route_id, set()).add(shape_id)
        route_shape_trip_counts.setdefault(route_id, {})
        route_shape_trip_counts[route_id][shape_id] = route_shape_trip_counts[route_id].get(shape_id, 0) + 1

        direction_id = str(row.get("direction_id") or "").strip()
        route_shape_direction_counts.setdefault(route_id, {})
        route_shape_direction_counts[route_id].setdefault(shape_id, {})
        if direction_id:
            route_shape_direction_counts[route_id][shape_id][direction_id] = (
                route_shape_direction_counts[route_id][shape_id].get(direction_id, 0) + 1
            )

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
        "route_shape_trip_counts": route_shape_trip_counts,
        "route_shape_direction_counts": route_shape_direction_counts,
        "shape_points": shape_points,
    }
    _CACHE["key"] = cache_key
    _CACHE["value"] = data
    return data


def _distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _sanitize_shape_coords(coords: list[list[float]], max_segment_m: float = _MAX_SEGMENT_METERS) -> list[list[float]]:
    if len(coords) < 2:
        return coords

    chunks: list[list[list[float]]] = []
    current: list[list[float]] = [coords[0]]
    for i in range(1, len(coords)):
        prev = coords[i - 1]
        cur = coords[i]
        dist = _distance_m(prev[1], prev[0], cur[1], cur[0])
        if dist > max_segment_m:
            if len(current) >= 2:
                chunks.append(current)
            current = [cur]
            continue
        current.append(cur)
    if len(current) >= 2:
        chunks.append(current)

    if not chunks:
        return []

    # Keep the longest connected chunk to avoid sea-crossing jump artifacts.
    return max(chunks, key=len)


def _choose_representative_shapes(
    route_id: str,
    shape_ids: set[str],
    shape_points: dict[str, list[tuple[int, float, float]]],
    route_shape_trip_counts: dict[str, dict[str, int]],
    route_shape_direction_counts: dict[str, dict[str, dict[str, int]]],
) -> list[str]:
    # Pick at most one shape per direction based on trip frequency, then point count.
    by_direction: dict[str, list[str]] = {}
    for shape_id in shape_ids:
        direction_counts = route_shape_direction_counts.get(route_id, {}).get(shape_id, {})
        if direction_counts:
            direction = max(direction_counts.items(), key=lambda item: item[1])[0]
        else:
            direction = "unknown"
        by_direction.setdefault(direction, []).append(shape_id)

    selected: list[str] = []
    for _, candidates in by_direction.items():
        ranked = sorted(
            candidates,
            key=lambda sid: (
                route_shape_trip_counts.get(route_id, {}).get(sid, 0),
                len(shape_points.get(sid, [])),
            ),
            reverse=True,
        )
        if ranked:
            selected.append(ranked[0])
    return sorted(set(selected))


def get_exact_route_shapes_geojson(route_filters: Optional[list[str]] = None, representative_only: bool = False) -> dict:
    data = _load_exact_shapes_data()
    route_meta: dict[str, dict] = data["route_meta"]  # type: ignore[assignment]
    route_to_shapes: dict[str, set[str]] = data["route_to_shapes"]  # type: ignore[assignment]
    route_shape_trip_counts: dict[str, dict[str, int]] = data["route_shape_trip_counts"]  # type: ignore[assignment]
    route_shape_direction_counts: dict[str, dict[str, dict[str, int]]] = data["route_shape_direction_counts"]  # type: ignore[assignment]
    shape_points: dict[str, list[tuple[int, float, float]]] = data["shape_points"]  # type: ignore[assignment]

    filters = {f.strip() for f in (route_filters or []) if f.strip()}
    features: list[dict] = []
    for route_id, shape_ids in route_to_shapes.items():
        meta = route_meta.get(route_id, {"route_id": route_id})
        short_name = str(meta.get("route_short_name") or "")
        if filters and route_id not in filters and short_name not in filters:
            continue
        target_shape_ids = (
            _choose_representative_shapes(
                route_id,
                shape_ids,
                shape_points,
                route_shape_trip_counts,
                route_shape_direction_counts,
            )
            if representative_only
            else sorted(shape_ids)
        )
        for shape_id in target_shape_ids:
            points = shape_points.get(shape_id, [])
            if len(points) < 2:
                continue
            coords = [[lon, lat] for _, lon, lat in points]
            coords = _sanitize_shape_coords(coords)
            if len(coords) < 2:
                continue
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
                    "shape_trip_count": route_shape_trip_counts.get(route_id, {}).get(shape_id, 0),
                    "representative": representative_only,
                    "path_type": "gtfs-shapes-exact",
                },
            })
    return {"type": "FeatureCollection", "features": features}
