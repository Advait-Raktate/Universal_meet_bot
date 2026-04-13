
"""
app/routers/webhook.py
-----------------------
Receives all webhook events from Recall.ai.
  POST /webhook/recall — bot lifecycle events + calendar events
"""
import json
#import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

from app.services.calendar_service import get_attendees_by_meet_url
from app.services.helper import _schedule_bot_for_event,_fetch_bot_title
from app.services.recall_service import format_transcript , fetch_speaker_transcript
from app.services.transcription_pipeline import run_pipeline
from app.core.config import settings

router = APIRouter()

@router.post("/recall")
async def recall_webhook(request: Request):
    body       = await request.json()
    event_type = body.get("event")
    data       = body.get("data", {})

    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = data["bot"]["id"]
        meet_url = data.get("bot", {}).get("meeting_url", "")

        meeting_title = (
            data.get("bot", {}).get("meeting_metadata", {}).get("title")
            or data.get("bot", {}).get("metadata", {}).get("meeting_title")
            or ""
        )
        if not meeting_title:
            meeting_title = await _fetch_bot_title(bot_id)

        # extract attendee_emails stored at schedule time
        attendee_emails_str = data.get("bot", {}).get("metadata", {}).get("attendee_emails", "")
        attendee_emails     = attendee_emails_str.split(",") if attendee_emails_str else []

        print(f"[WEBHOOK] Meeting title: '{meeting_title}'  | attendees: {attendee_emails}")
        asyncio.create_task(run_pipeline(bot_id, meeting_title, meet_url ,attendee_emails))
        return {"status": "ok"}
        
    if event_type == "calendar.sync_events":
        # run in background so webhook returns 200 immediately
        asyncio.create_task(handle_calendar_sync(data))
        return {"ok": True}

    if event_type == "calendar.update":
        print(f"[CALENDAR WEBHOOK] Calendar updated: {data.get('calendar_id')}")
        return {"ok": True}

    return {"ok": True}
# ─── Calendar sync handler (background) ──────────────────────────────────────
async def handle_calendar_sync(data: dict):
    calendar_id = data.get("calendar_id")

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{settings.recall_base_v2}/calendar-events/",
                headers=settings.recall_headers_accept,
                params={"calendar_id": calendar_id},  # no updated_at filter
            )

        events = res.json().get("results", [])
        now    = datetime.now(timezone.utc)

        for event in events:
            event_id   = event["id"]
            meet_url   = event.get("meeting_url")
            start_time = event.get("start_time")
            is_deleted = event.get("is_deleted", False)
            title      = event.get("raw", {}).get("summary", "No title")

            print(f"[DEBUG] event: title={title} | meet_url={meet_url} | start={start_time}")

            if not meet_url:
                print(f"[CALENDAR WEBHOOK] Skipping '{title}' — no meeting URL")
                continue

            if is_deleted:
                print(f"[CALENDAR WEBHOOK] Deleted: '{title}'")
                continue

            if start_time:
                event_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
                if event_start <= now:
                    print(f"[CALENDAR WEBHOOK] Skipping past event: '{title}'")
                    continue

            await _schedule_bot_for_event(event_id, meet_url, title)

    except Exception as e:
        print(f"[CALENDAR SYNC] Error: {e}")
