import os
import asyncio
import httpx
from fastapi import HTTPException
from dotenv import load_dotenv

load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"
PUBLIC_URL     = os.getenv("PUBLIC_URL")

RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}

# ─── Dedup guard ───────────────────────────────────────────────────────────────
in_flight = set()
_lock     = asyncio.Lock()


async def schedule_bot_by_meet_url(meet_url: str):
    """
    Manual fallback — useful for testing or scheduling a specific meeting.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{RECALL_BASE_V2}/calendar-events/", headers=RECALL_HEADERS)

    events  = res.json().get("results", [])
    matched = next((e for e in events if e.get("meeting_url") == meet_url), None)

    if not matched:
        raise HTTPException(
            status_code=404,
            detail="No calendar event found for this Meet URL."
        )

    event_id = matched["id"]
    title    = matched.get("raw", {}).get("summary", "No title")

    await _schedule_bot_for_event(event_id, meet_url, title)

    return {
        "message":   "Bot scheduled ✅ — will auto-join at meeting start time",
        "meet_url":  meet_url,
        "event_id":  event_id,
        "attendees": [a.get("email") for a in matched.get("raw", {}).get("attendees", [])],
    }


async def _schedule_bot_for_event(event_id: str, meet_url: str, title: str):
    """
    Schedules a bot for a calendar event.
    - asyncio.Lock ensures atomic check+add even across 11 simultaneous calendars
    - in_flight set blocks duplicate meet_url requests
    - 409 treated as non-fatal
    """

    # ── Atomic dedup check ────────────────────────────────────────────────────
    async with _lock:
        if meet_url in in_flight:
            print(f"[BOT SERVICE] ⚠️ Skipping duplicate for '{title}' — already in flight")
            return
        in_flight.add(meet_url)

    try:
        async with httpx.AsyncClient() as client:
            res = await client.post(
                f"{RECALL_BASE_V2}/calendar-events/{event_id}/bot/",
                headers=RECALL_HEADERS,
                json={
                    "deduplication_key": meet_url,
                    "bot_config": {
                        "bot_name":    "AG Brain Bot",
                        "webhook_url": f"{PUBLIC_URL}/webhook/recall",
                        "recording_config": {
                            "transcript": {
                                "provider": {
                                    "assembly_ai_async_chunked": {
                                        "speaker_labels":     True,
                                        "language_detection": True,
                                        "format_text":        True,
                                        "punctuate":          True,
                                        "keyterms_prompt":    [],
                                        "disfluencies":       False,
                                    }
                                }
                            }
                        }
                    }
                }
            )

        # ── Success ───────────────────────────────────────────────────────────
        if res.status_code in (200, 201):
            data   = res.json()
            print(f"[BOT SERVICE] Raw response: {data}")

            bot_id = data.get("bots", [{}])[0].get("bot_id")

            if bot_id:
                from app.routers.bot import save_bot_store
                save_bot_store(bot_id, meet_url, title)
                print(f"[BOT SERVICE] ✅ Saved bot_id={bot_id} → meet_url={meet_url} title={title}")
            else:
                print(f"[BOT SERVICE] ❌ Could not extract bot_id from response: {data}")

            print(f"[CALENDAR WEBHOOK] ✅ Bot scheduled for '{title}' | event={event_id} bot={bot_id}")

        # ── 409 — already scheduled, not an error ─────────────────────────────
        elif res.status_code == 409:
            print(f"[CALENDAR WEBHOOK] ⚠️ Bot already scheduled for '{title}' — ignoring")

        # ── Real failure ──────────────────────────────────────────────────────
        else:
            print(f"[CALENDAR WEBHOOK] ❌ Failed for '{title}': {res.text}")

    finally:
        in_flight.discard(meet_url)  # always clean up