
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

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import RedirectResponse

from app.core.config import settings
from app.services.helper import _schedule_bot_for_event

router = APIRouter()

@router.get("/connect")
async def connect_google_calendar():
    # No user_id needed — we'll extract email from Google after login
    params = {
        "client_id":              settings.google_client_id,
        "redirect_uri":           settings.redirect_uri,
        "response_type":          "code",
        "scope":                  settings.google_scopes,
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
                "client_id":     settings.google_client_id,
                "client_secret": settings.google_client_secret,
                "redirect_uri":  settings.redirect_uri,
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
            f"{settings.recall_base_v2}/calendars/",
            headers=settings.recall_headers,
            json={
                "oauth_client_id":     settings.google_client_id,
                "oauth_client_secret": settings.google_client_secret,
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
            f"{settings.recall_base_v2}/calendars/",
            headers=settings.recall_headers_accept,
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
            f"{settings.recall_base_v2}/calendar-events/",
            headers=settings.recall_headers_accept,
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

