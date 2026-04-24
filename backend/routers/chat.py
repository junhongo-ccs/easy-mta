"""
FastAPI router for Dify LLM chat proxy.
Prefix: /api/chat
"""

import os
from typing import Any, Optional

import httpx
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

_DEMO_RESPONSE = (
    "こんにちは！私はNYC地下鉄アシスタントです。\n\n"
    "現在、Dify APIキーが設定されていないためデモモードで動作しています。\n\n"
    "実際の環境では、地図上の駅をクリックするとその駅の情報を日本語で説明し、"
    "「タイムズスクエア駅を表示して」のようなメッセージで地図を操作することができます。\n\n"
    "**主な機能:**\n"
    "- 駅情報の日本語解説\n"
    "- リアルタイム運行情報\n"
    "- 路線案内\n"
    "- 地図の操作（ズーム・移動・フィルタリング）"
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


@router.post("/message")
async def send_message(body: ChatRequest):
    """Proxy a chat message to Dify and return the response."""
    dify_url = _dify_url()
    dify_key = _dify_key()

    if not dify_url or not dify_key:
        # Demo mode — return canned Japanese response
        return {
            "answer": _DEMO_RESPONSE,
            "conversation_id": body.conversation_id or "demo-conversation",
            "message_id": "demo-message",
            "tool_calls": [],
            "demo_mode": True,
        }

    # Build the Dify blocking chat-messages payload
    inputs = dict(body.inputs or {})
    if body.map_context:
        inputs["map_context"] = body.map_context

    payload: dict[str, Any] = {
        "query": body.message,
        "inputs": inputs,
        "response_mode": "blocking",
        "user": "easy-mta-user",
    }
    if body.conversation_id:
        payload["conversation_id"] = body.conversation_id

    headers = {
        "Authorization": f"Bearer {dify_key}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{dify_url.rstrip('/')}/v1/chat-messages",
                json=payload,
                headers=headers,
            )
            resp.raise_for_status()
            data = resp.json()
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
    for msg in data.get("messages", []):
        if msg.get("type") == "tool":
            tool_calls.append(msg)

    return {
        "answer": data.get("answer", ""),
        "conversation_id": data.get("conversation_id"),
        "message_id": data.get("id"),
        "tool_calls": tool_calls,
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
