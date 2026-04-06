import os
import httpx
from dotenv import load_dotenv

load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"

RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}


async def get_attendees_by_meet_url(meet_url: str) -> list[dict]:
    """
    Returns list of attendees with email + displayName for a given Meet URL.
    Example return:
    [
        { "email": "sanika@arcitech.ai",   "displayName": "Sanika Patane" },
        { "email": "vaibhavi@arcitech.ai", "displayName": "Vaibhavi Patil" }
    ]
    Returns [] if no event found or no attendees invited.
    """
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{RECALL_BASE_V2}/calendar-events/",
            headers=RECALL_HEADERS,
        )

    events  = res.json().get("results", [])
    matched = next((e for e in events if e.get("meeting_url") == meet_url), None)

    print(f"[CALENDAR] Looking for meet_url: {meet_url}")
    print(f"[CALENDAR] Matched event: {matched}")

    if not matched:
        return []

    # in calendar_service.py — add organizer to attendees list
    organizer_email = matched.get("raw", {}).get("organizer", {}).get("email", "")

    raw_attendees = matched.get("raw", {}).get("attendees", [])

    if not raw_attendees and organizer_email:
        raw_attendees = [{"email": organizer_email}]

    print(f"[CALENDAR DEBUG] raw attendees: {raw_attendees}")

    return [
        {
            "email":       a.get("email", ""),
            "displayName": a.get("displayName", a.get("email", ""))  # fallback to email if no name
        }
        for a in raw_attendees if a.get("email")
    ]