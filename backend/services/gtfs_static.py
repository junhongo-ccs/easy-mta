"""
GTFS static data service.
Provides an in-memory Toei Bus sample dataset for the PoC page.
"""

from typing import Optional

# Toei Bus PoC stops: representative central Tokyo stops with route assignments.
_STOPS: list[dict] = [
    {"stop_id": "toeibus-stop-001", "stop_name": "都庁第一本庁舎", "stop_lat": 35.689634, "stop_lon": 139.692101, "routes": ["都01", "宿75"], "wheelchair_accessible": True, "area": "新宿", "aliases": ["都庁前", "都庁", "東京都庁"]},
    {"stop_id": "toeibus-stop-002", "stop_name": "新宿駅西口", "stop_lat": 35.690921, "stop_lon": 139.699347, "routes": ["都01", "宿74", "宿75"], "wheelchair_accessible": True, "area": "新宿"},
    {"stop_id": "toeibus-stop-003", "stop_name": "渋谷駅前", "stop_lat": 35.658034, "stop_lon": 139.701636, "routes": ["都01", "渋66"], "wheelchair_accessible": True, "area": "渋谷"},
    {"stop_id": "toeibus-stop-004", "stop_name": "六本木駅前", "stop_lat": 35.662836, "stop_lon": 139.731443, "routes": ["都01", "反96"], "wheelchair_accessible": True, "area": "港"},
    {"stop_id": "toeibus-stop-005", "stop_name": "新橋駅前", "stop_lat": 35.666195, "stop_lon": 139.758590, "routes": ["都01", "業10"], "wheelchair_accessible": True, "area": "港"},
    {"stop_id": "toeibus-stop-006", "stop_name": "東京駅丸の内南口", "stop_lat": 35.679807, "stop_lon": 139.764964, "routes": ["東98", "都04"], "wheelchair_accessible": True, "area": "千代田"},
    {"stop_id": "toeibus-stop-007", "stop_name": "銀座四丁目", "stop_lat": 35.671991, "stop_lon": 139.765913, "routes": ["業10", "都04", "都05-1"], "wheelchair_accessible": True, "area": "中央"},
    {"stop_id": "toeibus-stop-008", "stop_name": "築地", "stop_lat": 35.668002, "stop_lon": 139.772091, "routes": ["業10", "都04", "都05-1"], "wheelchair_accessible": False, "area": "中央"},
    {"stop_id": "toeibus-stop-009", "stop_name": "豊洲駅前", "stop_lat": 35.654925, "stop_lon": 139.796569, "routes": ["業10", "都05-1", "海01"], "wheelchair_accessible": True, "area": "江東"},
    {"stop_id": "toeibus-stop-010", "stop_name": "東京ビッグサイト", "stop_lat": 35.630233, "stop_lon": 139.791593, "routes": ["都05-2", "海01"], "wheelchair_accessible": True, "area": "江東"},
    {"stop_id": "toeibus-stop-011", "stop_name": "上野公園山下", "stop_lat": 35.711693, "stop_lon": 139.773174, "routes": ["上23", "上46"], "wheelchair_accessible": True, "area": "台東"},
    {"stop_id": "toeibus-stop-012", "stop_name": "浅草雷門", "stop_lat": 35.710063, "stop_lon": 139.797505, "routes": ["草24", "上23"], "wheelchair_accessible": True, "area": "台東"},
    {"stop_id": "toeibus-stop-013", "stop_name": "錦糸町駅前", "stop_lat": 35.696825, "stop_lon": 139.814833, "routes": ["都02", "錦13", "上23"], "wheelchair_accessible": True, "area": "墨田"},
    {"stop_id": "toeibus-stop-014", "stop_name": "門前仲町", "stop_lat": 35.671904, "stop_lon": 139.796357, "routes": ["都07", "海01", "東22"], "wheelchair_accessible": False, "area": "江東"},
]

_ROUTES: list[dict] = [
    {"route_id": "都01", "route_name": "都01 渋谷駅前 - 新橋駅前", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "宿75", "route_name": "宿75 新宿駅西口 - 三宅坂", "route_color": "0068B7", "route_text_color": "FFFFFF"},
    {"route_id": "宿74", "route_name": "宿74 新宿駅西口 - 東京女子医大", "route_color": "0068B7", "route_text_color": "FFFFFF"},
    {"route_id": "渋66", "route_name": "渋66 渋谷駅前 - 阿佐ヶ谷駅前", "route_color": "00A3E0", "route_text_color": "FFFFFF"},
    {"route_id": "反96", "route_name": "反96 六本木 - 品川駅高輪口", "route_color": "8A4FFF", "route_text_color": "FFFFFF"},
    {"route_id": "業10", "route_name": "業10 新橋 - とうきょうスカイツリー駅", "route_color": "F58220", "route_text_color": "000000"},
    {"route_id": "東98", "route_name": "東98 東京駅 - 等々力操車所", "route_color": "D71920", "route_text_color": "FFFFFF"},
    {"route_id": "都04", "route_name": "都04 東京駅 - 豊海水産埠頭", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "都05-1", "route_name": "都05-1 東京駅 - 晴海埠頭", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "都05-2", "route_name": "都05-2 東京駅 - 東京ビッグサイト", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "海01", "route_name": "海01 門前仲町 - 東京テレポート駅", "route_color": "00A3E0", "route_text_color": "FFFFFF"},
    {"route_id": "上23", "route_name": "上23 上野松坂屋 - 平井駅前", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "上46", "route_name": "上46 上野松坂屋 - 南千住駅東口", "route_color": "FCCC0A", "route_text_color": "000000"},
    {"route_id": "草24", "route_name": "草24 浅草寿町 - 東大島駅前", "route_color": "8A4FFF", "route_text_color": "FFFFFF"},
    {"route_id": "都02", "route_name": "都02 大塚駅前 - 錦糸町駅前", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "錦13", "route_name": "錦13 錦糸町駅前 - 晴海埠頭", "route_color": "D71920", "route_text_color": "FFFFFF"},
    {"route_id": "都07", "route_name": "都07 錦糸町駅前 - 門前仲町", "route_color": "00843D", "route_text_color": "FFFFFF"},
    {"route_id": "東22", "route_name": "東22 東京駅 - 錦糸町駅前", "route_color": "D71920", "route_text_color": "FFFFFF"},
]

_stops_by_id: dict[str, dict] = {s["stop_id"]: s for s in _STOPS}


def get_stops() -> list[dict]:
    """Return all static bus stops."""
    return list(_STOPS)


def get_routes() -> list[dict]:
    """Return all bus routes."""
    return list(_ROUTES)


def get_stop_by_id(stop_id: str) -> Optional[dict]:
    """Return a single stop by its stop_id, or None if not found."""
    return _stops_by_id.get(stop_id)


def search_stops(query: str, limit: int = 10) -> list[dict]:
    """Return stops whose name, area, or route labels match the query."""
    needle = query.strip()
    if not needle:
        return []

    matches: list[dict] = []
    for stop in _STOPS:
        haystack = " ".join([
            stop.get("stop_name", ""),
            stop.get("area", ""),
            " ".join(stop.get("routes", [])),
            " ".join(stop.get("aliases", [])),
        ])
        aliases = [
            haystack,
            haystack.replace("駅前", ""),
            haystack.replace("第一本庁舎", ""),
            haystack.replace("丸の内南口", ""),
        ]
        if any(needle in alias for alias in aliases):
            matches.append(stop)
            if len(matches) >= limit:
                break
    return matches
