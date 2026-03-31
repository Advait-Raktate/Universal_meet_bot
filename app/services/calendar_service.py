"""
app/services/calendar_service.py
----------------------------------
Handles Recall Calendar V2 API interactions
"""
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

RECALL_API_KEY       = os.getenv("RECALL_API_KEY")
RECALL_REGION        = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE          = f"https://{RECALL_REGION}.recall.ai/api/v1"
RECALL_CALENDAR_BASE = f"https://{RECALL_REGION}.recall.ai/api/v2"   # ← Calendar V2 uses v2

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Accept":        "application/json",
    "Content-Type":  "application/json",
}


async def create_recall_calendar(refresh_token: str) -> dict:
    """
    Registers user's Google Calendar with Recall.
    Recall will start syncing events and firing webhooks.
    """

    url = f"{RECALL_CALENDAR_BASE}/calendar/"
    print(f"[CALENDAR] Calling URL: {url}")  
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{RECALL_CALENDAR_BASE}/calendar/",
            
            headers=HEADERS,
            json={
                "platform":            "google_calendar",
                "oauth_client_id":     GOOGLE_CLIENT_ID,
                "oauth_client_secret": GOOGLE_CLIENT_SECRET,
                "oauth_refresh_token": refresh_token,
            },
            timeout=30
        )
        if r.status_code >= 400:
            print(f"[CALENDAR ERROR] {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()


async def list_calendar_events(calendar_id: str, last_updated_ts: int) -> list:
    """
    Fetches all upcoming events for a calendar from Recall.
    """
    params = {"calendar_id": calendar_id}

    if last_updated_ts:
        params["updated_at__gte"] = last_updated_ts
         
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{RECALL_CALENDAR_BASE}/calendar-events/",
            headers=HEADERS,
            params=params,
            timeout=30
        )
         if r.status_code >= 400:
            print(f"[CALENDAR ERROR] {r.status_code}: {r.text}")
        r.raise_for_status()
        events = r.json().get("results", [])

        # ← Debug
        print(f"[CALENDAR] Total events found: {len(events)}")
        for e in events:
            print(f"[CALENDAR] Event: {e.get('title')} | URL: {e.get('meeting_url')} | Start: {e.get('start_time')}")

        return events


async def schedule_bot_for_event(calendar_event_id: str, meeting_name: str) -> dict:
    """
    Schedules a bot for a specific calendar event.
    Bot will auto-join at the event's start time.
    """
    try:
        async with httpx.AsyncClient() as client:
            # Step 1: Force record
            patch = await client.patch(
                f"{RECALL_CALENDAR_BASE}/calendar-events/{calendar_event_id}/",
                headers=HEADERS,
                json={"override_should_record": True},
                timeout=30
            )
            print(f"[SCHEDULE] Patch status: {patch.status_code} | {patch.text}")

            # Step 2: Schedule bot
            r = await client.post(
                f"{RECALL_CALENDAR_BASE}/calendar-events/{calendar_event_id}/bot/",
                headers=HEADERS,
                json={
                    "bot_name": "Notes Bot",
                    "metadata": {
                        "meeting_name": meeting_name
                    },
                    "recording_config": {
                        "transcript": {
                            "provider": {
                                "assembly_ai_async_chunked": {
                                    "speaker_labels":     True,
                                    "language_detection": True,
                                    "format_text":        True,
                                    "punctuate":          True,
                                    "disfluencies":       False,
                                    "keyterms_prompt":    []
                                }
                            }
                        }
                    }
                },
                timeout=30
            )
            print(f"[SCHEDULE] Status: {r.status_code} | Response: {r.text}")
            r.raise_for_status()
            return r.json()

    except httpx.HTTPStatusError as e:
        print(f"[ERROR] HTTP error: {e.response.status_code} | {e.response.text}")
    except Exception as e:
        print(f"[ERROR] An error occurred: {str(e)}")

async def delete_bot_from_event(calendar_event_id: str) -> None:
    """Removes scheduled bot from a calendar event."""
    async with httpx.AsyncClient() as client:
        r = await client.delete(
            f"{RECALL_CALENDAR_BASE}/calendar-event/{calendar_event_id}/bot/",
            headers=HEADERS,
            timeout=30
        )
        r.raise_for_status()
