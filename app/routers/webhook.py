"""
app/routers/webhook.py
-----------------------
Receives all webhook events from Recall.ai.
  POST /webhook/recall — bot lifecycle events + calendar events
"""
import json
import os
import asyncio
from datetime import datetime, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Request

from app.services.recall_service import (
    fetch_and_format_transcript,
    fetch_speaker_transcript,
    format_transcript,
    format_transcript_with_timestamps,
    map_names_to_emails,
)
from app.services.llm_service import fix_technical_terms
from app.services.calendar_service import get_attendees_by_meet_url
from app.services.bot_service import _schedule_bot_for_event
from app.routers.bot import get_meet_url, get_meeting_title
from app.services.helper import _send_to_downstream

router = APIRouter()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
PUBLIC_URL     = os.getenv("PUBLIC_URL")

RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"
RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}


# ─── Single Webhook — handles all Recall events ───────────────────────────────
@router.post("/recall")
async def recall_webhook(request: Request):
    body       = await request.json()
    event_type = body.get("event")
    data       = body.get("data", {})

    print(f"[WEBHOOK] Full body: {body}")
    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = data["bot"]["id"]
        asyncio.create_task(run_pipeline(bot_id))
        return {"status": "ok"}

    if event_type == "calendar.update":
        calendar_id = data.get("calendar_id")
        print(f"[CALENDAR WEBHOOK] Calendar updated: {calendar_id}")
        return {"ok": True}

    if event_type == "calendar.sync_events":
        asyncio.create_task(handle_calendar_sync(data))
        return {"ok": True}

    return {"ok": True}


# ─── Calendar sync handler (background) ──────────────────────────────────────
async def handle_calendar_sync(data: dict):
    """
    Handles calendar.sync_events in background.
    Schedules bot for upcoming meetings found in the sync.
    """
    calendar_id     = data.get("calendar_id")
    last_updated_ts = data.get("last_updated_ts")

    try:
        async with httpx.AsyncClient() as client:
            res = await client.get(
                f"{RECALL_BASE_V2}/calendar-events/",
                headers=RECALL_HEADERS,
                params={
                    "calendar_id":     calendar_id,
                    "updated_at__gte": last_updated_ts,
                },
                timeout=30,
            )

        events = res.json().get("results", [])
        now    = datetime.now(timezone.utc)

        for event in events:
            event_id        = event["id"]
            meet_url        = event.get("meeting_url")
            start_time      = event.get("start_time")
            is_deleted      = event.get("is_deleted", False)
            title           = event.get("raw", {}).get("summary", "No title")
            organizer_email = event.get("raw", {}).get("organizer", {}).get("email", "")

            # Filter 1 — only Google Meet
            if not meet_url or not meet_url.startswith("https://meet.google.com/"):
                print(f"[CALENDAR WEBHOOK] Skipping '{title}' — not Google Meet")
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

    except Exception as e:
        print(f"[CALENDAR SYNC] Error: {e}")


# ─── Pipeline ─────────────────────────────────────────────────────────────────
async def run_pipeline(bot_id: str):
    """
    Full post-meeting pipeline:
      1. Fetch + format + clean transcript (Hindi fix + tech terms)
      2. Fetch attendees from Google Calendar
      3. Map speaker names → emails using first name fallback
      4. Send to downstream API
      5. Save everything to JSON
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id}")

    try:
        # Step 1 — fetch, format, clean transcript
        clean_transcript = await fetch_and_format_transcript(bot_id)

        if not clean_transcript.strip():
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return

        print(f"\n── Cleaned Transcript ───────────────────────────\n{clean_transcript}")

        # Step 2 — fetch ordered segments with timestamps
        segments = await fetch_speaker_transcript(bot_id)
        print(f"[DEBUG] segments count: {len(segments)}")

        # Step 3 — fetch attendees + meeting title
        meet_url      = get_meet_url(bot_id)
        meeting_title = get_meeting_title(bot_id)
        attendees     = await get_attendees_by_meet_url(meet_url) if meet_url else []
        print(f"[PIPELINE] meet_url={meet_url} | title={meeting_title} | attendees={attendees}")

        # Step 4 — map speaker names → emails
        email_segments = map_names_to_emails(segments, attendees)

        # for downstream API — simple format + Hindi fix
        simple_transcript = format_transcript(email_segments)
        simple_transcript = await fix_technical_terms(simple_transcript)

        # for JSON file — timestamped format + Hindi fix
        email_transcript = format_transcript_with_timestamps(email_segments)
        email_transcript = await fix_technical_terms(email_transcript)
        print(f"\n── Email Transcript ─────────────────────────────\n{email_transcript}")

        # Step 4b — send to downstream API
        await _send_to_downstream({
            "project_name":  meeting_title,
            "transcription": simple_transcript,
        })

        # Step 5 — save to JSON
        Path("transcripts").mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"transcripts/{bot_id}_{timestamp}.json"

        result = {
            "bot_id":              bot_id,
            "timestamp":           datetime.now().isoformat(),
            "meeting_title":       meeting_title,
            "meet_url":            meet_url,
            "attendees":           attendees,
            "transcript_by_email": email_transcript,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ [PIPELINE] Saved: {filename}")

    except Exception as e:
        print(f"[PIPELINE] Error for {bot_id}: {e}")
        raise