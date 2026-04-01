"""
app/routers/webhook.py
-----------------------
Receives webhook events from Recall.ai.
When bot.done fires, runs the full pipeline automatically:
  fetch transcript → fix Hindi/tech terms → format → LLM summarize → save notes
"""
import json
import asyncio
from fastapi import APIRouter, Request
from app.services.recall_service import fetch_and_format_transcript, fetch_speaker_transcript
from app.services.llm_service import summarize_meeting, summarize_per_speaker
from datetime import datetime
from pathlib import Path

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

    event_type = body.get("event")
    print(f"[WEBHOOK] Received: {event_type}")

    if event_type == "bot.done":
        bot_id = body["data"]["bot"]["id"]
        # Run pipeline in background — return 200 to Recall immediately
        asyncio.create_task(run_pipeline(bot_id))

    return {"status": "ok"}


async def run_pipeline(bot_id: str):
    """
    Full pipeline:
      1. Fetch raw transcript from Recall (grouped by speaker)
      2. Format into readable text
      3. Fix Devanagari Hindi → Hinglish + mangled tech terms (Claude)
      4. Send clean transcript to GPT-4o for summary + action items
      5. Save notes to JSON file (swap for DB as needed)
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id}")

    try:
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
        print(f"[PIPELINE] Error for {bot_id}: {e}")
        raise  # re-raise so the full traceback is visible in logs