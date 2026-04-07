import os
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


async def schedule_bot_by_meet_url(meet_url: str):
    """
    Manual fallback — useful for testing or scheduling a specific meeting.
    For normal usage, bots are auto-scheduled via the webhook.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{RECALL_BASE_V2}/calendar-events/", headers=RECALL_HEADERS)

    events  = res.json().get("results", [])
    matched = next((e for e in events if e.get("meeting_url") == meet_url), None)

    if not matched:
        raise HTTPException(
            status_code=404,
            detail="No calendar event found for this Meet URL. Make sure the event exists on your connected Google Calendar."
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
    deduplication_key = event_id ensures re-scheduling on event updates
    doesn't create duplicate bots.
    """
    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{RECALL_BASE_V2}/calendar-events/{event_id}/bot/",
            headers=RECALL_HEADERS,
            json={
                "deduplication_key": meet_url,  # ← use meet_url so same meeting never gets 2 bots
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
                                    #"speech_model":       "universal-3-pro",  # ← highest accuracy
                                    "keyterms_prompt":    [],
                                    "disfluencies":       False,
                                }
                            }
                        }
                    }
                }
            }
        )

    if res.status_code in (200, 201):
        data   = res.json()
        print(f"[BOT SERVICE] Raw response: {data}")  # ← debug: see actual structure

        # try both possible response structures
        """
        bot_id = (
            data.get("id") or                          # direct id
            data.get("bot", {}).get("id") or           # nested bot.id
            data.get("bot_id")                         # bot_id field
        )
        """
        bot_id = data.get("bots", [{}])[0].get("bot_id")  # correct bot_id from bots array

        if bot_id:
            from app.routers.bot import save_bot_store
            save_bot_store(bot_id, meet_url, title)  # ← pass title
            print(f"[BOT SERVICE] ✅ Saved bot_id={bot_id} → meet_url={meet_url} title={title}")
        else:
            print(f"[BOT SERVICE] ❌ Could not extract bot_id from response: {data}")

        print(f"[CALENDAR WEBHOOK] ✅ Bot scheduled for '{title}' | event={event_id} bot={bot_id}")
    else:
        print(f"[CALENDAR WEBHOOK] ❌ Failed to schedule bot for '{title}': {res.text}")