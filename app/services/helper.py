import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Request
from app.core.config import settings
from app.services.recall_service import fetch_speaker_transcript, format_transcript

async def schedule_bot_by_meet_url(meet_url: str):
    """
    Manual fallback — useful for testing or scheduling a specific meeting.
    For normal usage, bots are auto-scheduled via the webhook.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(f"{settings.recall_base_v2}/calendar-events/", headers=settings.recall_headers)

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
     # fetch attendees now while event still exists
    from app.services.calendar_service import get_attendees_by_meet_url
    attendees = await get_attendees_by_meet_url(meet_url)
    attendee_emails = [a["email"] for a in attendees]
    print(f"[BOT] Attendees at schedule time: {attendee_emails}")

    async with httpx.AsyncClient() as client:
        res = await client.post(
            f"{settings.recall_base_v2}/calendar-events/{event_id}/bot/",
            headers=settings.recall_headers,
            json={
                "deduplication_key": meet_url,  # ← same across all calendars, prevents duplicates
                "bot_config": {
                    "bot_name":    "AG BRAIN Bot",
                    "webhook_url": settings.webhook_recall_url,
                    "metadata": {
                        "meeting_title": title,
                        "meet_url":      meet_url,
                        "attendee_emails":",".join(attendee_emails),  # ← store here

                    },
                    "recording_config": {
                        "transcript": {
                            "provider": {
                                "assembly_ai_async_chunked": {
                                "speaker_labels":     True,
                                "language_detection": True,
                                "format_text":        True,
                                "punctuate":          True,
                                #"speech_model":       "universal-3-pro",  # ← uncomment this
                                "keyterms_prompt":    [],
                                "disfluencies":       False,
                                }
                            }
                        }
                    }
                }
            }
        )

    print(f"[BOT] Response status: {res.status_code}")
    print(f"[BOT] Response body: {res.json()}")  # ← add this


    if res.status_code in (200, 201):
        data   = res.json()
        #print(f"[BOT] Raw response: {data}")  # keep this to verify

        bot_id = (
        data.get("bots", [{}])[0].get("bot_id")  # V2 calendar endpoint
        or data.get("bot", {}).get("id")          # V1 direct bot endpoint
        or data.get("id")                          # fallback
        )
        print(f"[CALENDAR WEBHOOK] ✅ Bot scheduled for '{title}' | event={event_id} bot={bot_id}")
    else:
        print(f"[CALENDAR WEBHOOK] ❌ Failed: {res.status_code} — {res.text}")  

        
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
