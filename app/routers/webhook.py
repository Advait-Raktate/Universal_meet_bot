"""
app/routers/webhook.py
-----------------------
Receives webhook events from Recall.ai.
When bot.done fires, runs the full pipeline automatically:
  fetch transcript → format → LLM summarize → save notes
"""
#import json
import asyncio
from fastapi import APIRouter, Request
from app.services.recall_service import fetch_speaker_transcript, format_transcript
from app.services.llm_service import summarize_meeting, summarize_per_speaker
from datetime import datetime
from pathlib  import Path
router = APIRouter()


@router.post("/recall")
async def recall_webhook(request: Request):
    """
    Recall calls this endpoint with a bot.done event when:
      - The meeting has ended
      - The transcript is fully processed and ready to fetch
    """
    print("function called")

    body = await request.json()
    print(f"[WEBHOOK] Full body: {body}")

    event      = await request.json()
    event_type = event.get("event")

    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = event["data"]["bot"]["id"]
        # Run pipeline in background — return 200 to Recall immediately
        asyncio.create_task(run_pipeline(bot_id))

 # ── Calendar events updated ──
    elif event_type == "calendar.sync_events":
        #calendar_id = event["data"]["calendar"]["id"]
        calendar_id      = event["data"]["calendar_id"]        # ← correct field name
        last_updated_ts  = event["data"]["last_updated_ts"]    # ← get timestamp
        asyncio.create_task(sync_calendar_events(calendar_id, last_updated_ts))
        #asyncio.create_task(sync_calendar_events(calendar_id))

    # ── Calendar disconnected ──
    elif event_type == "calendar.update":
        status = event["data"]["calendar"].get("status")
        print(f"[CALENDAR] Status changed: {status}")

    return {"status": "ok"}


async def sync_calendar_events(calendar_id: str):
    """
    Fetches all calendar events and schedules
    bot for each one that has a Google Meet link.
    """
    from app.services.calendar_service import (
        list_calendar_events,
        schedule_bot_for_event
    )

    print(f"[CALENDAR] Syncing events for calendar: {calendar_id}")

    events = await list_calendar_events(calendar_id , last_updated_ts)  # ← pass timestamp if needed

    for event in events:
        meeting_name = event.get("title", "Untitled Meeting")
        meet_invite  = event.get("meet_invite")        # ← from Recall response
        event_id     = event["id"]
        will_record  = event.get("will_record", False)

        if not meet_invite:
            print(f"[CALENDAR] No Meet link in: {meeting_name} — skipping")
            continue

        if will_record:
            print(f"[CALENDAR] Already scheduled: {meeting_name}")
            continue

        print(f"[CALENDAR] Scheduling bot for: {meeting_name}")
        await schedule_bot_for_event(event_id, meeting_name)
        print(f"[CALENDAR] ✅ Bot scheduled for: {meeting_name}")


async def run_pipeline(bot_id: str):

    import json
    """
    Full pipeline:
      1. Fetch transcript from Recall (grouped by speaker name)
      2. Format into clean readable text
      3. Send to Claude for summary + action items
      4. Save notes to file (swap for DB as needed)
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id}")

    try:
        # Step 1 — fetch
        speaker_map = await fetch_speaker_transcript(bot_id)
        if not speaker_map:
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return

        # Step 2 — format
        formatted = format_transcript(speaker_map)
        print(f"\n── Transcript ───────────────────────────\n{formatted}")

        # Step 3: Run meeting summary + per speaker simultaneously
        print("\n[PIPELINE] Generating summaries...")
        meeting_notes, per_speaker = await asyncio.gather(
            summarize_meeting(formatted),           # ← full meeting notes
            summarize_per_speaker(speaker_map)      # ← per person summary
        )

        print(f"\n── Meeting Notes ──\n{meeting_notes}")
        print(f"\n── Per Speaker ──\n{per_speaker}")

        # Step 4: Save as JSON file automatically
        Path("transcripts").mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename  = f"transcripts/{bot_id}_{timestamp}.json"

        result = {
            "bot_id":              bot_id,
            "timestamp":           datetime.now().isoformat(),
            "transcript":          formatted,
            "meeting_notes":       meeting_notes,
            "per_speaker_summary": per_speaker
            
        }

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        print(f"\n✅ [PIPELINE] Saved: {filename}")

    except Exception as e:
        print(f"[PIPELINE] Error for {bot_id}: {e}")

