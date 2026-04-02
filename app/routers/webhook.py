"""
app/routers/webhook.py
-----------------------
Receives all webhook events from Recall.ai.

  POST /webhook/recall    — bot lifecycle events (bot.done, etc.)
  POST /webhook/calendar  — calendar events (sync_events, calendar update)
"""

import os
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from app.services.helper import _schedule_bot_for_event,_send_to_downstream,_fetch_bot_title
from app.services.transcription_pipeline import run_pipeline
router = APIRouter()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
PUBLIC_URL     = os.getenv("PUBLIC_URL")
DOWNSTREAM_API = os.getenv("DOWNSTREAM_API")

RECALL_BASE_V1  = f"https://{RECALL_REGION}.recall.ai/api/v1"
RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"
RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}


# ─── Single Webhook — handles all Recall events ───────────────────────────────
@router.post("/recall")
async def recall_webhook(request: Request):
    """
    Single endpoint for all Recall events.
    Register this one URL in the Recall Dashboard for everything.

    bot.done              — meeting ended → extract transcript + summarize
    calendar.sync_events  — event created / updated / deleted → schedule bot
    calendar.update       — calendar connected / disconnected
    """
    body       = await request.json()
    event_type = body.get("event")
    data       = body.get("data", {})

    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = data["bot"]["id"]

        meeting_title = (
            data.get("bot", {}).get("meeting_metadata", {}).get("title")
            or data.get("bot", {}).get("metadata", {}).get("meeting_title")
            or ""
        )

        # 2. If not in payload, fetch from bot metadata API (FALLBACK BASICALLY)
        if not meeting_title:
            meeting_title = await _fetch_bot_title(bot_id)
        print(f"[WEBHOOK] Meeting title resolved: '{meeting_title}'")
        
        asyncio.create_task(run_pipeline(bot_id, meeting_title))
        return {"status": "ok"}

    if event_type == "calendar.update":
        calendar_id = data.get("calendar_id")
        print(f"[CALENDAR WEBHOOK] Calendar updated: {calendar_id}")
        return {"ok": True}

    if event_type == "calendar.sync_events":
        calendar_id     = data.get("calendar_id")
        last_updated_ts = data.get("last_updated_ts")

        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{RECALL_BASE_V2}/calendar-events/",
                headers=RECALL_HEADERS,
                params={
                    "calendar_id":     calendar_id,
                    "updated_at__gte": last_updated_ts,
                },
            )

        events = res.json().get("results", [])
        now    = datetime.now(timezone.utc)

        for event in events:
            event_id   = event["id"]
            meet_url   = event.get("meeting_url")
            start_time = event.get("start_time")
            is_deleted = event.get("is_deleted", False)
            title      = event.get("raw", {}).get("summary", "No title")

            if not meet_url:
                print(f"[CALENDAR WEBHOOK] Skipping '{title}' — no meeting URL")
                continue

            if is_deleted:
                print(f"[CALENDAR WEBHOOK] Event deleted: '{title}' — bot auto-unscheduled by Recall")
                continue

            if start_time:
                event_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                if event_start <= now:
                    print(f"[CALENDAR WEBHOOK] Skipping past event: '{title}'")
                    continue

            await _schedule_bot_for_event(event_id, meet_url, title)

    return {"ok": True}


        