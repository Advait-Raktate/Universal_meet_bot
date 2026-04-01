"""
app/routers/webhook.py
-----------------------
<<<<<<< HEAD
Receives webhook events from Recall.ai.
When bot.done fires, runs the full pipeline automatically:
  fetch transcript → fix Hindi/tech terms → format → LLM summarize → save notes
"""
import json
=======
Receives all webhook events from Recall.ai.

  POST /webhook/recall    — bot lifecycle events (bot.done, etc.)
  POST /webhook/calendar  — calendar events (sync_events, calendar update)
"""

import os
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d
import asyncio
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Request
from app.services.recall_service import fetch_and_format_transcript, fetch_speaker_transcript
from app.services.llm_service import summarize_meeting, summarize_per_speaker
from datetime import datetime
from pathlib import Path

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
    """
    Single endpoint for all Recall events.
    Register this one URL in the Recall Dashboard for everything.

    bot.done              — meeting ended → extract transcript + summarize
    calendar.sync_events  — event created / updated / deleted → schedule bot
    calendar.update       — calendar connected / disconnected
    """
<<<<<<< HEAD
    print("function called")
=======
    body       = await request.json()
    event_type = body.get("event")
    data       = body.get("data", {})
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d

    body = await request.json()
    print(f"[WEBHOOK] Full body: {body}")

    event_type = body.get("event")
    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = body["data"]["bot"]["id"]
<<<<<<< HEAD
        # Run pipeline in background — return 200 to Recall immediately
=======
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d
        asyncio.create_task(run_pipeline(bot_id))
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


# ─── Helper ───────────────────────────────────────────────────────────────────
async def _schedule_bot_for_event(event_id: str, meet_url: str, title: str):
    """
    Schedules a bot for a calendar event.
    deduplication_key = event_id ensures re-scheduling on event updates
    doesn't create duplicate bots.
    """
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{RECALL_BASE_V2}/calendar-events/{event_id}/bot/",
            headers=RECALL_HEADERS,
            json={
                "deduplication_key": event_id,
                "bot_config": {
                    "bot_name":    "Notes Bot",
                    "webhook_url": f"{PUBLIC_URL}/webhook/recall",
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


# ─── Pipeline ─────────────────────────────────────────────────────────────────
async def run_pipeline(bot_id: str):
    """
<<<<<<< HEAD
    Full pipeline:
      1. Fetch raw transcript from Recall (grouped by speaker)
      2. Format into readable text
      3. Fix Devanagari Hindi → Hinglish + mangled tech terms (Claude)
      4. Send clean transcript to GPT-4o for summary + action items
      5. Save notes to JSON file (swap for DB as needed)
=======
    Full post-meeting pipeline:
      1. Fetch transcript from Recall (grouped by speaker)
      2. Format into readable text
      3. Summarize with LLM
      4. Save notes to file
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id}")

    try:
<<<<<<< HEAD
        # Step 1+2+3 — fetch, format, and clean in one call
        clean_transcript = await fetch_and_format_transcript(bot_id)

        if not clean_transcript.strip():
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return

        print(f"\n── Cleaned Transcript ───────────────────────────\n{clean_transcript}")

        # Step 4 — fetch raw speaker_map separately for per-speaker summary
        speaker_map = await fetch_speaker_transcript(bot_id)

        # Step 5 — run meeting summary + per-speaker summary simultaneously
        print("\n[PIPELINE] Generating summaries...")
        meeting_notes, per_speaker = await asyncio.gather(
            summarize_meeting(clean_transcript),    # full meeting notes (clean)
            summarize_per_speaker(speaker_map)      # per person summary
        )
=======
        speaker_map = await fetch_speaker_transcript(bot_id)
        if not speaker_map:
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return

        formatted = format_transcript(speaker_map)
        print(f"\n── Transcript ───────────────────────────\n{formatted}")

        notes = await summarize_meeting(formatted)
        print(f"\n── Meeting Notes ────────────────────────\n{notes}\n")

        with open(f"notes_{bot_id}.txt", "w") as f:
            f.write("── TRANSCRIPT ──────────────────────────────────\n\n")
            f.write(formatted)
            f.write("\n\n── MEETING NOTES ───────────────────────────────\n\n")
            f.write(notes)
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d

        print(f"\n── Meeting Notes ──\n{meeting_notes}")
        print(f"\n── Per Speaker ──\n{per_speaker}")

        # Step 6 — save as JSON file
        Path("transcripts").mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"transcripts/{bot_id}_{timestamp}.json"

        result = {
            "bot_id":              bot_id,
            "timestamp":           datetime.now().isoformat(),
            "transcript":          clean_transcript,
            "meeting_notes":       meeting_notes,
            "per_speaker_summary": per_speaker,
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ [PIPELINE] Saved: {filename}")

    except Exception as e:
<<<<<<< HEAD
        print(f"[PIPELINE] Error for {bot_id}: {e}")
        raise  # re-raise so the full traceback is visible in logs
=======
        print(f"[PIPELINE] Error for {bot_id}: {e}")
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d
