import httpx
from app.core.config import settings


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
            f"{settings.recall_base_v2}/calendar-events/",
            headers=settings.recall_headers_accept,
        )

    events  = res.json().get("results", [])
    matched = next((e for e in events if e.get("meeting_url") == meet_url), None)

    print(f"[CALENDAR] Looking for meet_url: {meet_url}")
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
