"""
app/routers/calendar.py
-----------------------
Google OAuth + Recall Calendar Integration (V2)

Endpoints:
  GET  /calendar/connect           — redirect user to Google OAuth
  GET  /calendar/google_callback   — handle Google redirect, save token to Recall
  GET  /calendar/status            — check if calendar is connected
  GET  /calendar/events            — list upcoming calendar events
  POST /calendar/schedule          — manually schedule bot for a meet URL
"""

import os
import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from app.routers.webhook import _schedule_bot_for_event

load_dotenv()

router = APIRouter()

# ─── CONFIG ───────────────────────────────────────────────────────────────────
GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
RECALL_API_KEY       = os.getenv("RECALL_API_KEY")
RECALL_REGION        = os.getenv("RECALL_REGION", "us-west-2")
PUBLIC_URL           = os.getenv("PUBLIC_URL")

RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"
REDIRECT_URI   = f"{PUBLIC_URL}/calendar/google_callback"

RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Content-Type":  "application/json",
}

SCOPES = " ".join([
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/userinfo.email",
])


@router.get("/connect")
async def connect_google_calendar():
    # No user_id needed — we'll extract email from Google after login
    params = {
        "client_id":              GOOGLE_CLIENT_ID,
        "redirect_uri":           REDIRECT_URI,
        "response_type":          "code",
        "scope":                  SCOPES,
        "access_type":            "offline",
        "prompt":                 "consent",
        "include_granted_scopes": "true",
    }
    query_string    = "&".join(f"{k}={v}" for k, v in params.items())
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"
    return RedirectResponse(url=google_auth_url)


@router.get("/google_callback")
async def google_oauth_callback(code: str = Query(...)):
    # Step 1 — exchange code for tokens
    async with httpx.AsyncClient() as client:
        token_res = await client.post(
            "https://oauth2.googleapis.com/token",
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
        )

    if token_res.status_code != 200:
        raise HTTPException(status_code=400, detail=f"Failed to exchange code: {token_res.text}")

    tokens        = token_res.json()
    refresh_token = tokens.get("refresh_token")
    access_token  = tokens.get("access_token")

    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token returned. Make sure prompt=consent is set.")

    # Step 2 — fetch user email from Google using the access token
    async with httpx.AsyncClient() as client:
        userinfo_res = await client.get(
            "https://www.googleapis.com/oauth2/v2/userinfo",
            headers={"Authorization": f"Bearer {access_token}"},
        )

    if userinfo_res.status_code != 200:
        raise HTTPException(status_code=400, detail="Failed to fetch user info from Google")

    user_id = userinfo_res.json().get("email")  # e.g. "your@email.com"
    print(f"[CALENDAR] Google user identified: {user_id}")

    # Step 3 — register calendar in Recall
    async with httpx.AsyncClient() as client:
        recall_res = await client.post(
            f"{RECALL_BASE_V2}/calendars/",
            headers=RECALL_HEADERS,
            json={
                "oauth_client_id":     GOOGLE_CLIENT_ID,
                "oauth_client_secret": GOOGLE_CLIENT_SECRET,
                "oauth_refresh_token": refresh_token,
                "platform":            "google_calendar",
            }
        )

    if recall_res.status_code not in (200, 201):
        raise HTTPException(status_code=400, detail=f"Failed to create Recall calendar: {recall_res.text}")

    calendar_id = recall_res.json()["id"]
    print(f"[CALENDAR] Connected for user {user_id} → calendar_id: {calendar_id}")

    return {
        "message":     "Google Calendar connected successfully",
        "user_id":     user_id,
        "calendar_id": calendar_id,
    }

# ─── Check connection status ──────────────────────────────────────────────────
@router.get("/status")
async def calendar_status(user_id: str = Query(...)):
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{RECALL_BASE_V2}/calendars/",
            headers=RECALL_HEADERS,
            params={"external_id": user_id},
        )

    calendars = res.json().get("results", [])
    if not calendars:
        return {"connected": False, "user_id": user_id}

    cal = calendars[0]
    return {
        "connected":      True,
        "user_id":        user_id,
        "calendar_id":    cal["id"],
        "platform_email": cal.get("platform_email"),
        "status":         cal.get("status"),
    }


# ─── List upcoming calendar events ───────────────────────────────────────────
@router.get("/events")
async def list_calendar_events():
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{RECALL_BASE_V2}/calendar-events/",
            headers=RECALL_HEADERS,
        )

    events = res.json().get("results", [])
    return [
        {
            "id":        e["id"],
            "title":     e.get("raw", {}).get("summary", "No title"),
            "start":     e.get("start_time"),
            "meet_url":  e.get("meeting_url"),
            "attendees": [a.get("email") for a in e.get("raw", {}).get("attendees", [])],
        }
        for e in events if e.get("meeting_url")
    ]


# ─── Manual schedule by Meet URL (kept for ad-hoc use) ───────────────────────
@router.post("/schedule")
async def schedule_bot_by_meet_url(meet_url: str = Query(...)):
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