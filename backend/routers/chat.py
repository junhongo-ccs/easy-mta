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


def _vehicle_line(vehicle: dict, include_distance: bool = False) -> str:
    route = vehicle.get("route_display_name") or vehicle.get("route_short_name") or f"{vehicle.get('route_id')}系統"
    destination = f" / 行先: {vehicle.get('destination')}" if vehicle.get("destination") else ""
    distance = f" / 約{vehicle.get('distance_m')}m" if include_distance and vehicle.get("distance_m") is not None else ""
    return f"- **{route}** 車両ID: {vehicle.get('vehicle_id')}{destination}{distance}"


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
    text = message.strip()

    if map_context:
        if map_context.get("type") == "stop":
            routes = "、".join(map_context.get("routes") or [])
            accessible = "バリアフリー対応あり" if map_context.get("wheelchair_accessible") else "バリアフリー情報は要確認"
            stop_name = map_context.get("stop_name") or map_context.get("name")
            return {
                "answer": (
                    f"**{stop_name}** の停留所案内です。\n\n"
                    f"- 主な系統: {routes or '不明'}\n"
                    f"- エリア: {map_context.get('area', '未設定')}\n"
                    f"- {accessible}\n"
                    f"- 停留所ID: {map_context.get('stop_id')}\n\n"
                    "地図上の停留所データをもとに表示しています。周辺を走行中の車両や利用できる系統も、この停留所を起点に案内できます。"
                ),
                "map_command": {"type": "highlightStop", "stop_id": map_context.get("stop_id")},
            }
        if map_context.get("type") == "vehicle":
            source = "ODPT実データ" if map_context.get("source") == "odpt" else "モックデータ"
            timestamp = _format_epoch_jst(map_context.get("timestamp"))
            route_label = (
                map_context.get("route_display_name")
                or map_context.get("route_short_name")
                or f"{map_context.get('route_id')}系統"
            )
            route_note = ""
            if map_context.get("route_short_name") and map_context.get("route_id"):
                route_note = f"- GTFS route_id: {map_context.get('route_id')}\n"
            destination = f"- 行先: {map_context.get('destination')}\n" if map_context.get("destination") else ""
            return {
                "answer": (
                    f"**{route_label}** の車両案内です。\n\n"
                    f"- 車両ID: {map_context.get('id')}\n"
                    f"{route_note}"
                    f"{destination}"
                    f"- 状態: {map_context.get('current_status', '不明')}\n\n"
                    f"- データ: {source}\n"
                    f"- 位置情報タイムスタンプ: {timestamp}\n\n"
                    "リアルタイム車両位置データに、系統名・行先情報を組み合わせて表示しています。"
                )
            }

    for stop in gtfs_static.get_stops():
        aliases = [
            stop["stop_name"],
            stop["stop_name"].replace("駅前", ""),
            stop["stop_name"].replace("第一本庁舎", ""),
            stop["stop_name"].replace("丸の内南口", ""),
            stop.get("area", ""),
        ]
        if any(alias and alias in text for alias in aliases):
            wants_nearby = any(word in text for word in ["近く", "付近", "周辺", "走", "車両", "バス"])
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
                    "この停留所を起点に、周辺を走行中の車両や利用できる系統を案内する想定です。"
                ),
                "map_command": {
                    "type": "focusOn",
                    "lat": stop["stop_lat"],
                    "lng": stop["stop_lon"],
                    "zoom": 15,
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

    if "リセット" in text or "全て" in text or "すべて" in text:
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

    if not dify_url or not dify_key:
        # Demo mode — return canned Japanese response
        demo = await _demo_response(body.message, body.map_context)
        return {
            "answer": demo.get("answer", _DEMO_RESPONSE),
            "conversation_id": body.conversation_id or "demo-conversation",
            "message_id": "demo-message",
            "tool_calls": [],
            "map_command": demo.get("map_command"),
            "demo_mode": True,
        }

    if body.map_context:
        context_answer = await _demo_response(body.message, body.map_context)
        return {
            "answer": context_answer.get("answer", ""),
            "conversation_id": body.conversation_id,
            "message_id": "local-map-context",
            "tool_calls": [],
            "map_command": context_answer.get("map_command"),
            "dify_mode": "local_map_context",
            "demo_mode": False,
        }

    # Build the Dify blocking chat-messages payload
    inputs = dict(body.inputs or {})
    if body.map_context:
        inputs["map_context"] = body.map_context

    enriched_query = _context_as_prompt(body.message, body.map_context)

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
        async with httpx.AsyncClient(timeout=60.0) as client:
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
        "answer": answer,
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
