"""
FastAPI router for Dify LLM chat proxy.
Prefix: /api/chat
"""

import os
import re
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import gtfs_static, gtfs_realtime

router = APIRouter()
JST = timezone(timedelta(hours=9))
_FULLWIDTH_TO_HALFWIDTH = str.maketrans(
    "０１２３４５６７８９ＡＢＣＤＥＦＧＨＩＪＫＬＭＮＯＰＱＲＳＴＵＶＷＸＹＺａｂｃｄｅｆｇｈｉｊｋｌｍｎｏｐｑｒｓｔｕｖｗｘｙｚ－",
    "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-",
)

_DEMO_RESPONSE = (
    "現在はDify未接続のデモモードです。\n\n"
    "このPoCでは、都バスの停留所・車両位置・公式FAQをAI案内につなぐ体験を想定しています。\n\n"
    "**試せること:**\n"
    "- 「都庁前付近を表示して」\n"
    "- 「都01を見せて」\n"
    "- 「バリアフリー停留所を表示して」\n"
    "- 地図上の停留所や車両をクリック"
)


class ChatRequest(BaseModel):
    message: str
    conversation_id: Optional[str] = None
    inputs: Optional[dict[str, Any]] = None
    map_context: Optional[dict[str, Any]] = None


def _dify_url() -> Optional[str]:
    return os.getenv("DIFY_API_URL", "").strip() or None


def _dify_key() -> Optional[str]:
    return os.getenv("DIFY_API_KEY", "").strip() or None


def _dify_app_mode() -> str:
    return os.getenv("DIFY_APP_MODE", "auto").strip().lower()


def _dify_ssl_verify() -> bool:
    return os.getenv("DIFY_SSL_VERIFY", "true").strip().lower() not in {"0", "false", "no"}


def _api_key() -> Optional[str]:
    return os.getenv("ODPT_API_KEY") or None


def _format_epoch_jst(value: Any) -> str:
    try:
        return datetime.fromtimestamp(int(value), JST).strftime("%Y-%m-%d %H:%M:%S JST")
    except Exception:
        return "未取得"


def _route_candidates(text: str) -> list[str]:
    candidates = re.findall(r"[一-龠ぁ-んァ-ヶA-Za-z]{1,4}\d{1,3}(?:-\d)?|\d{2,3}", text)
    seen: set[str] = set()
    result: list[str] = []
    for candidate in candidates:
        if candidate not in seen:
            seen.add(candidate)
            result.append(candidate)
    return result


def _destination_candidates(text: str) -> list[str]:
    patterns = [
        r"([一-龠ぁ-んァ-ヶA-Za-z0-9・ー]+?(?:駅前|駅|西口|東口|南口|北口|車庫|操車所|庁舎|病院|学校|公園|センター|ターミナル))\s*行(?:き)?",
        r"([一-龠ぁ-んァ-ヶA-Za-z0-9・ー]{2,20})\s*行(?:き)?(?:の)?(?:バス|車両)",
    ]
    seen: set[str] = set()
    result: list[str] = []
    for pattern in patterns:
        for candidate in re.findall(pattern, text):
            candidate = candidate.strip()
            if candidate and candidate not in seen:
                seen.add(candidate)
                result.append(candidate)
    return result


def _normalize_user_text(text: str) -> str:
    normalized = (text or "").translate(_FULLWIDTH_TO_HALFWIDTH)
    return re.sub(r"(?<=\d)ー(?=\d)", "-", normalized)


def _destination_label(destination: Any) -> str:
    text = str(destination or "").strip()
    if not text:
        return ""
    return text if text.endswith(" 行") else f"{text} 行"


def _normalize_destination_notation(text: str) -> str:
    if not text:
        return text

    def replace_label(match: re.Match[str]) -> str:
        destination = match.group(1).strip()
        destination = re.sub(r"(?:\s*行|行き)$", "", destination)
        return _destination_label(destination)

    normalized = re.sub(r"行先\s*[:：]\s*([^\n、。/]+)", replace_label, text)
    normalized = re.sub(r"(?:目的地|行き先)は\s*([^\n、。/]+)", replace_label, normalized)
    normalized = re.sub(
        r"([一-龠ぁ-んァ-ヶA-Za-z0-9・ー]+?(?:駅前|駅|西口|東口|南口|北口|車庫|操車所|庁舎|病院|学校|公園|センター|ターミナル))行き",
        lambda match: _destination_label(match.group(1)),
        normalized,
    )
    normalized = re.sub(
        r"([一-龠ぁ-んァ-ヶA-Za-z0-9・ー]+?(?:駅前|駅|西口|東口|南口|北口|車庫|操車所|庁舎|病院|学校|公園|センター|ターミナル))行(?![一-龠ぁ-んァ-ヶA-Za-z0-9])",
        lambda match: _destination_label(match.group(1)),
        normalized,
    )
    return normalized


def _wants_nearby_vehicles(text: str) -> bool:
    if any(word in text for word in ["接近", "走行", "車両", "バス"]):
        return True
    return any(word in text for word in ["近く", "付近", "周辺"]) and any(word in text for word in ["来る", "いる", "探", "教えて"])


def _wants_same_route_vehicles(text: str) -> bool:
    if "同系統" in text or "同一系統" in text:
        return True
    return "同じ" in text and any(word in text for word in ["系統", "路線", "バス", "車両"])


def _wants_same_destination_vehicles(text: str) -> bool:
    return "同じ" in text and any(word in text for word in ["行先", "行き先", "行", "方面"])


def _is_vehicle_context_prompt(text: str) -> bool:
    return text.startswith("この車両について教えてください")


def _vehicle_status_label(status: Any) -> str:
    # Fallback used when the GTFS-RT stop_id cannot be resolved to a stop name.
    labels = {
        "INCOMING_AT": "停留所に接近しています",
        "STOPPED_AT": "停留所に停車中です",
        "IN_TRANSIT_TO": "次の停留所へ向かっています",
    }
    return labels.get(str(status or ""), "運行中です")


def _vehicle_stop_status_sentence(status: Any, next_stop_name: Any, current_stop_name: Any) -> str:
    status_text = str(status or "")
    next_name = str(next_stop_name or "").strip()
    current_name = str(current_stop_name or "").strip()
    if status_text == "STOPPED_AT" and current_name:
        return f"現在は **{current_name}** に停車中です。"
    if status_text == "INCOMING_AT" and next_name:
        return f"現在は **{next_name}** に接近しています。"
    if status_text == "IN_TRANSIT_TO" and next_name:
        return f"現在は **{next_name}** へ向かっています。"
    return f"現在は{_vehicle_status_label(status)}。"


def _vehicle_line(vehicle: dict, include_distance: bool = False) -> str:
    route = vehicle.get("route_short_name") or vehicle.get("route_display_name") or f"{vehicle.get('route_id')}系統"
    destination = f" / {_destination_label(vehicle.get('destination'))}" if vehicle.get("destination") else ""
    distance = f" / 約{vehicle.get('distance_m')}m" if include_distance and vehicle.get("distance_m") is not None else ""
    return f"- **{route}**{destination}{distance}"


async def _search_destination_vehicles(candidate: str, limit: int = 8) -> tuple[list[dict], str]:
    vehicles = await gtfs_realtime.search_vehicles_by_route(_api_key(), candidate, limit=20)
    exact_matches = [v for v in vehicles if str(v.get("destination") or "").strip() == candidate]
    if exact_matches:
        return exact_matches[:limit], candidate
    if vehicles:
        return vehicles[:limit], str(vehicles[0].get("destination") or candidate)
    return [], candidate


def _context_as_prompt(message: str, map_context: Optional[dict[str, Any]]) -> str:
    if not map_context:
        return message

    if map_context.get("type") == "vehicle":
        fields = {
            "車両ID": map_context.get("id") or map_context.get("vehicle_id"),
            "系統": map_context.get("route_display_name") or map_context.get("route_short_name"),
            "GTFS route_id": map_context.get("route_id"),
            "行先": map_context.get("destination"),
            "状態": map_context.get("current_status"),
            "緯度": map_context.get("lat") or map_context.get("latitude"),
            "経度": map_context.get("lng") or map_context.get("longitude"),
            "位置情報時刻": _format_epoch_jst(map_context.get("timestamp")),
            "データソース": "ODPT実データ" if map_context.get("source") == "odpt" else map_context.get("source"),
        }
        details = "\n".join(f"- {key}: {value}" for key, value in fields.items() if value)
        return (
            f"{message}\n\n"
            "地図上でクリックされた車両の情報は以下です。この情報を根拠に回答してください。\n"
            f"{details}"
        )

    if map_context.get("type") == "stop":
        routes = "、".join(map_context.get("routes") or [])
        fields = {
            "停留所名": map_context.get("stop_name") or map_context.get("name"),
            "停留所ID": map_context.get("stop_id"),
            "エリア": map_context.get("area"),
            "主な系統": routes,
            "緯度": map_context.get("stop_lat") or map_context.get("lat"),
            "経度": map_context.get("stop_lon") or map_context.get("lng"),
            "バリアフリー": map_context.get("wheelchair_accessible"),
        }
        details = "\n".join(f"- {key}: {value}" for key, value in fields.items() if value is not None and value != "")
        return (
            f"{message}\n\n"
            "地図上でクリックされた停留所の情報は以下です。この情報を根拠に回答してください。\n"
            f"{details}"
        )

    return message


async def _demo_response(message: str, map_context: Optional[dict[str, Any]]) -> dict[str, Any]:
    text = _normalize_user_text(message).strip()

    if map_context:
        if map_context.get("type") == "stop":
            routes = "、".join(map_context.get("routes") or [])
            accessible = "バリアフリー対応あり" if map_context.get("wheelchair_accessible") else "バリアフリー情報は要確認"
            stop_name = map_context.get("stop_name") or map_context.get("name")
            wants_nearby = _wants_nearby_vehicles(text)
            if wants_nearby:
                lat = map_context.get("stop_lat") or map_context.get("lat")
                lng = map_context.get("stop_lon") or map_context.get("lng")
                vehicles = []
                if lat is not None and lng is not None:
                    vehicles = await gtfs_realtime.search_nearby_vehicles(
                        _api_key(),
                        float(lat),
                        float(lng),
                        radius_m=900,
                        limit=8,
                    )
                if vehicles:
                    lines = "\n".join(_vehicle_line(v, include_distance=True) for v in vehicles[:5])
                    nearest = vehicles[0]
                    return {
                        "answer": (
                            f"**{stop_name}** 周辺で接近中・走行中の車両を見つけました。\n\n"
                            f"{lines}\n\n"
                            "地図は最も近い車両付近へ移動します。"
                        ),
                        "map_command": {
                            "type": "focusOn",
                            "lat": nearest["latitude"],
                            "lng": nearest["longitude"],
                            "zoom": 15,
                        },
                    }
                return {
                    "answer": f"**{stop_name}** 周辺では、現在の検索半径内に接近中・走行中の車両が見つかりませんでした。",
                    "map_command": {
                        "type": "highlightStop",
                        "stop_id": map_context.get("stop_id"),
                    },
                }
            return {
                "answer": (
                    f"**{stop_name}** の停留所案内です。\n\n"
                    f"- 主な系統: {routes or '不明'}\n"
                    f"- エリア: {map_context.get('area', '未設定')}\n"
                    f"- {accessible}\n"
                    f"- 停留所ID: {map_context.get('stop_id')}\n\n"
                    "地図上の停留所データをもとに表示しています。この停留所について「接近中のバスを教えて」と聞くと、周辺の車両を確認できます。"
                ),
                "map_command": {"type": "highlightStop", "stop_id": map_context.get("stop_id")},
            }
        if map_context.get("type") == "vehicle":
            route_label = map_context.get("route_short_name") or map_context.get("route_display_name") or f"{map_context.get('route_id')}系統"
            destination = _destination_label(map_context.get("destination"))
            if not _is_vehicle_context_prompt(text):
                for candidate in _destination_candidates(text):
                    vehicles, found_destination = await _search_destination_vehicles(candidate)
                    if vehicles:
                        lines = "\n".join(_vehicle_line(v) for v in vehicles[:5])
                        return {
                            "answer": (
                                f"**{_destination_label(found_destination)}** の走行中車両を見つけました。\n\n"
                                f"{lines}\n\n"
                                "地図上ではこの行先の車両だけを表示します。"
                            ),
                            "map_command": {
                                "type": "filterVehiclesByRoute",
                                "destination": found_destination,
                            },
                        }
            if _wants_same_route_vehicles(text):
                return {
                    "answer": f"**{route_label}** と同じ系統のバスを表示します。",
                    "map_command": {
                        "type": "filterVehiclesByRoute",
                        "route_short_name": map_context.get("route_short_name"),
                        "route_id": map_context.get("route_id"),
                    },
                }
            if _wants_same_destination_vehicles(text) and map_context.get("destination"):
                return {
                    "answer": f"**{destination}** のバスを表示します。",
                    "map_command": {
                        "type": "filterVehiclesByRoute",
                        "destination": map_context.get("destination"),
                    },
                }
            destination_sentence = (
                f"このバスは **{route_label}** の **{destination}** です。"
                if destination
                else f"このバスは **{route_label}** です。行先情報は現在確認中です。"
            )
            status_sentence = _vehicle_stop_status_sentence(
                map_context.get("current_status"),
                map_context.get("next_stop_name") or map_context.get("stop_name"),
                map_context.get("current_stop_name") or map_context.get("stop_name"),
            )
            map_command = {
                "type": "filterVehiclesByRoute",
                "destination": map_context.get("destination"),
                "route_short_name": map_context.get("route_short_name"),
                "route_id": map_context.get("route_id"),
            }
            return {
                "answer": (
                    "選択したバスの案内です。\n\n"
                    f"{destination_sentence}\n"
                    f"{status_sentence}\n\n"
                    "「全バスを表示」と入力してもバス表示を初期化できます。"
                ),
                "map_command": map_command,
            }

    if "全バス" in text or "すべてのバス" in text or "全車両" in text or "すべての車両" in text:
        return {
            "answer": "すべてのバスを表示します。",
            "map_command": {"type": "resetVehicleFilters"},
        }

    for candidate in _destination_candidates(text):
        vehicles, destination = await _search_destination_vehicles(candidate)
        if vehicles:
            lines = "\n".join(_vehicle_line(v) for v in vehicles[:5])
            return {
                "answer": (
                    f"**{_destination_label(destination)}** の走行中車両を見つけました。\n\n"
                    f"{lines}\n\n"
                    "地図上ではこの行先の車両だけを表示します。"
                ),
                "map_command": {
                    "type": "filterVehiclesByRoute",
                    "destination": destination,
                },
            }

    for stop in gtfs_static.get_stops():
        aliases = [
            stop["stop_name"],
            stop["stop_name"].replace("駅前", ""),
            stop["stop_name"].replace("第一本庁舎", ""),
            stop["stop_name"].replace("丸の内南口", ""),
            stop.get("area", ""),
            *(stop.get("aliases") or []),
        ]
        if any(alias and alias in text for alias in aliases):
            wants_nearby = _wants_nearby_vehicles(text)
            if wants_nearby:
                vehicles = await gtfs_realtime.search_nearby_vehicles(
                    _api_key(),
                    float(stop["stop_lat"]),
                    float(stop["stop_lon"]),
                    radius_m=900,
                    limit=8,
                )
                if vehicles:
                    lines = "\n".join(_vehicle_line(v, include_distance=True) for v in vehicles[:5])
                    nearest = vehicles[0]
                    return {
                        "answer": (
                            f"**{stop['stop_name']}** から約900m以内を走行中の車両を見つけました。\n\n"
                            f"{lines}\n\n"
                            "地図は最も近い車両付近へ移動します。"
                        ),
                        "map_command": {
                            "type": "focusOn",
                            "lat": nearest["latitude"],
                            "lng": nearest["longitude"],
                            "zoom": 15,
                        },
                    }
                return {
                    "answer": f"**{stop['stop_name']}** 周辺では、現在の検索半径内に車両が見つかりませんでした。",
                    "map_command": {
                        "type": "focusOn",
                        "lat": stop["stop_lat"],
                        "lng": stop["stop_lon"],
                        "zoom": 15,
                    },
                }
            return {
                "answer": (
                    f"**{stop['stop_name']}** 付近を表示します。\n\n"
                    "現在の拡大率はそのまま、地図の中心だけを移動します。"
                ),
                "map_command": {
                    "type": "focusOn",
                    "lat": stop["stop_lat"],
                    "lng": stop["stop_lon"],
                    "preserve_zoom": True,
                },
            }

    for candidate in _route_candidates(text):
        vehicles = await gtfs_realtime.search_vehicles_by_route(_api_key(), candidate, limit=8)
        if vehicles:
            lines = "\n".join(_vehicle_line(v) for v in vehicles[:5])
            first = vehicles[0]
            route_label = first.get("route_short_name") or candidate
            return {
                "answer": (
                    f"**{route_label}** に該当する走行中の車両を見つけました。\n\n"
                    f"{lines}\n\n"
                    "地図上では該当系統の車両だけを表示します。"
                ),
                "map_command": {
                    "type": "filterVehiclesByRoute",
                    "route_short_name": first.get("route_short_name"),
                    "route_id": first.get("route_id"),
                },
            }

    for route in gtfs_static.get_routes():
        if route["route_id"] in text:
            return {
                "answer": f"**{route['route_name']}** の停留所を地図上に絞り込みます。",
                "map_command": {"type": "showRoute", "route_id": route["route_id"]},
            }

    if "バリアフリー" in text or "車いす" in text or "車椅子" in text:
        return {
            "answer": "バリアフリー対応のある停留所を表示します。本番では停留所設備、乗り場位置、車両情報まで案内対象にします。",
            "map_command": {"type": "filterAccessible"},
        }

    if "リセット" in text or "全て" in text or "すべて" in text or "絞り込みを解除" in text:
        return {
            "answer": "地図の絞り込みを解除します。",
            "map_command": {"type": "resetFilters"},
        }

    return {"answer": _DEMO_RESPONSE}


@router.post("/message")
async def send_message(body: ChatRequest):
    """Proxy a chat message to Dify and return the response."""
    dify_url = _dify_url()
    dify_key = _dify_key()
    normalized_message = _normalize_user_text(body.message)

    if not dify_url or not dify_key:
        # Demo mode — return canned Japanese response
        demo = await _demo_response(normalized_message, body.map_context)
        return {
            "answer": _normalize_destination_notation(demo.get("answer", _DEMO_RESPONSE)),
            "conversation_id": body.conversation_id or "demo-conversation",
            "message_id": "demo-message",
            "tool_calls": [],
            "map_command": demo.get("map_command"),
            "demo_mode": True,
        }

    if body.map_context:
        context_answer = await _demo_response(normalized_message, body.map_context)
        return {
            "answer": _normalize_destination_notation(context_answer.get("answer", "")),
            "conversation_id": body.conversation_id,
            "message_id": "local-map-context",
            "tool_calls": [],
            "map_command": context_answer.get("map_command"),
            "dify_mode": "local_map_context",
            "demo_mode": False,
        }

    local_answer = await _demo_response(normalized_message, None)
    if local_answer.get("map_command"):
        return {
            "answer": _normalize_destination_notation(local_answer.get("answer", "")),
            "conversation_id": body.conversation_id,
            "message_id": "local-supported-query",
            "tool_calls": [],
            "map_command": local_answer.get("map_command"),
            "dify_mode": "local_supported_query",
            "demo_mode": False,
        }

    # Build the Dify blocking chat-messages payload
    inputs = dict(body.inputs or {})
    if body.map_context:
        inputs["map_context"] = body.map_context

    enriched_query = _context_as_prompt(normalized_message, body.map_context)

    chat_payload: dict[str, Any] = {
        "query": enriched_query,
        "inputs": inputs,
        "response_mode": "blocking",
        "user": "easy-mta-user",
    }
    if body.conversation_id:
        chat_payload["conversation_id"] = body.conversation_id

    headers = {
        "Authorization": f"Bearer {dify_key}",
        "Content-Type": "application/json",
    }

    async def call_chat_messages(client: httpx.AsyncClient) -> dict[str, Any]:
        resp = await client.post(
            f"{dify_url.rstrip('/')}/v1/chat-messages",
            json=chat_payload,
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    async def call_workflow(client: httpx.AsyncClient) -> dict[str, Any]:
        workflow_inputs = {**inputs, "query": enriched_query}
        resp = await client.post(
            f"{dify_url.rstrip('/')}/v1/workflows/run",
            json={
                "inputs": workflow_inputs,
                "response_mode": "blocking",
                "user": "easy-mta-user",
            },
            headers=headers,
        )
        resp.raise_for_status()
        return resp.json()

    try:
        async with httpx.AsyncClient(verify=_dify_ssl_verify(), timeout=60.0) as client:
            if _dify_app_mode() == "workflow":
                data = await call_workflow(client)
                mode = "workflow"
            elif _dify_app_mode() == "chat":
                data = await call_chat_messages(client)
                mode = "chat"
            else:
                try:
                    data = await call_chat_messages(client)
                    mode = "chat"
                except httpx.HTTPStatusError as exc:
                    if exc.response.status_code != 400 or "not_chat_app" not in exc.response.text:
                        raise
                    data = await call_workflow(client)
                    mode = "workflow"
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"DifyAPIエラー ({exc.response.status_code}): {exc.response.text}",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Difyサービスに接続できませんでした: {exc}",
        ) from exc

    # Normalise the Dify response
    tool_calls: list[dict] = []
    answer = ""
    conversation_id = None
    message_id = None

    if mode == "workflow":
        workflow_data = data.get("data") or {}
        outputs = workflow_data.get("outputs") or {}
        answer = outputs.get("answer") or outputs.get("text") or ""
        if not answer and outputs:
            answer = next((str(v) for v in outputs.values() if isinstance(v, str)), "")
        message_id = workflow_data.get("id") or data.get("workflow_run_id")
    else:
        answer = data.get("answer", "")
        conversation_id = data.get("conversation_id")
        message_id = data.get("id")
        for msg in data.get("messages", []):
            if msg.get("type") == "tool":
                tool_calls.append(msg)

    return {
        "answer": _normalize_destination_notation(answer),
        "conversation_id": conversation_id,
        "message_id": message_id,
        "tool_calls": tool_calls,
        "dify_mode": mode,
        "demo_mode": False,
    }


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(conversation_id: str):
    """Delete a Dify conversation."""
    dify_url = _dify_url()
    dify_key = _dify_key()

    if not dify_url or not dify_key:
        return {"deleted": True, "demo_mode": True}

    headers = {"Authorization": f"Bearer {dify_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.delete(
                f"{dify_url.rstrip('/')}/v1/conversations/{conversation_id}",
                headers=headers,
                params={"user": "easy-mta-user"},
            )
            resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"会話の削除に失敗しました ({exc.response.status_code})",
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Difyサービスに接続できませんでした: {exc}",
        ) from exc

    return {"deleted": True, "conversation_id": conversation_id}
