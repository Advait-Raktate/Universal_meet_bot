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
from app.services.bot_service import _schedule_bot_for_event , schedule_bot_by_meet_url

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


# ─── STEP 1: Redirect user to Google consent screen ──────────────────────────
@router.get("/connect")
async def connect_google_calendar(user_id: str = Query(...)):
    params = {
        "client_id":              GOOGLE_CLIENT_ID,
        "redirect_uri":           REDIRECT_URI,
        "response_type":          "code",
        "scope":                  SCOPES,
        "access_type":            "offline",
        "prompt":                 "consent",
        "include_granted_scopes": "true",
        "state":                  user_id,
    }
    query_string    = "&".join(f"{k}={v}" for k, v in params.items())
    google_auth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"
    return RedirectResponse(url=google_auth_url)


# ─── STEP 2: Google redirects back here ──────────────────────────────────────
@router.get("/google_callback")
async def google_oauth_callback(code: str = Query(...), state: str = Query(...)):
    user_id = state

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

    refresh_token = token_res.json().get("refresh_token")
    if not refresh_token:
        raise HTTPException(status_code=400, detail="No refresh_token returned. Make sure prompt=consent is set.")

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



@router.delete("/disconnect")
async def disconnect_calendar(user_id: str = Query(...)):
    async with httpx.AsyncClient() as client:
        # Step 1 — find calendar_id for this user
        res = await client.get(
            f"{RECALL_BASE_V2}/calendars/",
            headers=RECALL_HEADERS,
            params={"external_id": user_id},
        )

    calendars = res.json().get("results", [])
    if not calendars:
        return {"message": f"No calendar found for user: {user_id}"}

    calendar_id = calendars[0]["id"]

    async with httpx.AsyncClient() as client:
        # Step 2 — delete it from Recall
        res = await client.delete(
            f"{RECALL_BASE_V2}/calendars/{calendar_id}/",
            headers=RECALL_HEADERS,
        )

    if res.status_code == 204:
        return {"message": f"✅ Disconnected calendar for user: {user_id}", "calendar_id": calendar_id}
    else:
        return {"message": f"❌ Failed to disconnect", "detail": res.text}