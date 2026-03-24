"""
app/routers/webhook.py
-----------------------
Receives webhook events from Recall.ai.
When bot.done fires, runs the full pipeline automatically:
  fetch transcript → format → LLM summarize → save notes
"""

import asyncio
from fastapi import APIRouter, Request
from app.services.recall_service import fetch_speaker_transcript, format_transcript
from app.services.llm_service import summarize_meeting

router = APIRouter()


@router.post("/recall")
async def recall_webhook(request: Request):
    """
    Recall calls this endpoint with a bot.done event when:
      - The meeting has ended
      - The transcript is fully processed and ready to fetch
    """
    event      = await request.json()
    event_type = event.get("event")

    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = event["data"]["bot"]["id"]
        # Run pipeline in background — return 200 to Recall immediately
        asyncio.create_task(run_pipeline(bot_id))

    return {"status": "ok"}


async def run_pipeline(bot_id: str):
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

        # Step 3 — summarize
        notes = await summarize_meeting(formatted)
        print(f"\n── Meeting Notes ────────────────────────\n{notes}\n")

        # Step 4 — save (replace with DB insert as needed)
        with open(f"notes_{bot_id}.txt", "w") as f:
            f.write("── TRANSCRIPT ──────────────────────────────────\n\n")
            f.write(formatted)
            f.write("\n\n── MEETING NOTES ───────────────────────────────\n\n")
            f.write(notes)

        print(f"[PIPELINE] Notes saved: notes_{bot_id}.txt")

    except Exception as e:
        print(f"[PIPELINE] Error for {bot_id}: {e}")
