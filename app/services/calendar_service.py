import os
import httpx
from dotenv import load_dotenv
from app.services.recall_service import RECALL_HEADERS, RECALL_BASE_V2


bot_map = {}

load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"

RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}


async def get_attendees_by_meet_url(meet_url: str) -> list[dict]:
    matched = None
    url     = f"{RECALL_BASE_V2}/calendar-events/"
    total   = 0
    async with httpx.AsyncClient() as client:
        while url:
            res     = await client.get(url, headers=RECALL_HEADERS, timeout=30)
            data    = res.json()
            results = data.get("results", [])
            total  += len(results)

            # ✅ search each page for correct event
            matched = next(
                (e for e in results if e.get("meeting_url") == meet_url), None
            )
            if matched:
                break  # ← stop when found

            url = data.get("next")  # ← go to next page

    print(f"[CALENDAR] Looking for meet_url: {meet_url}")
    print(f"[CALENDAR] Total events searched: {total}")
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