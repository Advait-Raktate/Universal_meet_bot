import os
import httpx
from dotenv import load_dotenv
from app.services.recall_service import RECALL_HEADERS, RECALL_BASE_V2


load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"

RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}


async def get_attendees_by_meet_url(meet_url: str) -> list[dict]:
    all_events = []
    url = f"{RECALL_BASE_V2}/calendar-events/"

    async with httpx.AsyncClient() as client:
        while url:
            res = await client.get(url, headers=RECALL_HEADERS)
            data = res.json()
            all_events.extend(data.get("results", []))
            url = data.get("next")  # ← follow next page if exists

    matched = next((e for e in all_events if e.get("meeting_url") == meet_url), None)

    print(f"[CALENDAR] Looking for meet_url: {meet_url}")
    print(f"[CALENDAR] Total events searched: {len(all_events)}")
    print(f"[CALENDAR] Matched event: {matched}")

    if not matched:
        return []

    organizer_email = matched.get("raw", {}).get("organizer", {}).get("email", "")
    raw_attendees   = matched.get("raw", {}).get("attendees", [])

    if not raw_attendees and organizer_email:
        raw_attendees = [{"email": organizer_email}]

    print(f"[CALENDAR DEBUG] raw attendees: {raw_attendees}")

    return [
        {
            "email":       a.get("email", ""),
            "displayName": a.get("displayName", a.get("email", ""))
        }
        for a in raw_attendees if a.get("email")
    ]