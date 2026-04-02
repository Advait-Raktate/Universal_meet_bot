import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Request
from app.core.config import settings
from app.services.recall_service import fetch_speaker_transcript, format_transcript


async def _schedule_bot_for_event(event_id: str, meet_url: str, title: str):
    """
    Schedules a bot for a calendar event.
    deduplication_key = event_id ensures re-scheduling on event updates
    doesn't create duplicate bots.
    """
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{settings.recall_base_v2}/calendar-events/{event_id}/bot/",
            headers=settings.recall_headers,
            json={
                "deduplication_key": event_id,
                "bot_config": {
                    "bot_name":    "Notes Bot",
                    "webhook_url": settings.webhook_recall_url,
                    "metadata": {"meeting_title": title},
                    "recording_config": {
                        "transcript": {
                            "provider": {
                                "recallai_streaming": {
                                    "language":         "en",
                                    "identify_speaker": True,
                                }
                            }
                        }
                    }
                }
            }
        )

    if res.status_code in (200, 201):
        bot_id = res.json().get("bot", {}).get("id")
        print(f"[CALENDAR WEBHOOK] ✅ Bot scheduled for '{title}' | event={event_id} bot={bot_id}")
    else:
        print(f"[CALENDAR WEBHOOK] ❌ Failed to schedule bot for '{title}': {res.text}")


        
async def _send_to_downstream(payload: dict):
    """
    POSTs { project_name, transcription } to your downstream API.
    Swap the URL / auth headers to match your API's requirements.
    """
    if not settings.downstream_api:
        print("[DOWNSTREAM] DOWNSTREAM_API_URL not set — skipping")
        return

    async with httpx.AsyncClient() as client:
        res = await client.post(
            settings.downstream_api,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    if res.status_code in (200, 201):
        print(f"[DOWNSTREAM] ✅ Sent successfully: {res.status_code}")
    else:
        print(f"[DOWNSTREAM] ❌ Failed: {res.status_code} — {res.text}")        
        

async def _fetch_bot_title(bot_id: str) -> str:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{settings.recall_base_v1}/bot/{bot_id}/",
            headers=settings.recall_headers_accept,
        )
    if res.status_code == 200:
        bot_data = res.json()

        # 1. Custom title we stored when scheduling
        title = bot_data.get("metadata", {}).get("meeting_title")
        if title:
            return title

        # 2. Actual meeting title from recording (often None for Google Meet)
        recordings = bot_data.get("recordings", [])
        if recordings:
            title = recordings[0].get("meeting_metadata", {}).get("data", {}).get("title")
            if title:
                return title
    return "Untitled Meeting"