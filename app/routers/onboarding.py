"""
app/routers/onboarding.py
--------------------------
Simple onboarding flow:
  GET /onboarding         — shows connect calendar page
  GET /onboarding/success — shown after calendar connected
"""
import os
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

load_dotenv()

router    = APIRouter()
PUBLIC_URL = os.getenv("PUBLIC_URL")


# ─── Step 1 — Connect Calendar Page ──────────────────────────────────────────
@router.get("/", response_class=HTMLResponse)
async def onboarding_page():
    """
    Simple page with Connect Google Calendar button.
    No name/email input needed — Google provides email automatically.
    """
    html = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>MeetBot — Connect Calendar</title>
        <style>
            body {
                font-family: Arial, sans-serif;
                max-width: 500px;
                margin: 100px auto;
                text-align: center;
                padding: 20px;
            }
            h1 { color: #333; }
            p  { color: #666; margin-bottom: 30px; }
            a.btn {
                display: inline-block;
                background: #4285f4;
                color: white;
                text-decoration: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-size: 16px;
                width: 100%;
                box-sizing: border-box;
            }
            a.btn:hover { background: #3367d6; }
            .logo { font-size: 48px; margin-bottom: 20px; }
        </style>
    </head>
    <body>
        <div class="logo">🤖</div>
        <h1>Welcome to MeetBot</h1>
        <p>Connect your Google Calendar and MeetBot will automatically
           join your meetings and generate transcripts.</p>

        <a class="btn" href="/calendar/connect">
            Connect Google Calendar
        </a>
    </body>
    </html>
    """
    return HTMLResponse(content=html)


# ─── Step 2 — Success Page ────────────────────────────────────────────────────
@router.get("/success", response_class=HTMLResponse)
async def onboarding_success(email: str = ""):
    """
    Shown after calendar is successfully connected.
    Shows connected email and button to schedule meeting.
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>MeetBot — Connected!</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                max-width: 500px;
                margin: 100px auto;
                text-align: center;
                padding: 20px;
            }}
            h1 {{ color: #2e7d32; }}
            p  {{ color: #666; margin-bottom: 30px; }}
            .email {{
                background: #f0f4f8;
                padding: 10px 20px;
                border-radius: 8px;
                margin-bottom: 24px;
                font-weight: bold;
                color: #333;
            }}
            a.btn {{
                display: inline-block;
                background: #2e7d32;
                color: white;
                text-decoration: none;
                padding: 14px 28px;
                border-radius: 8px;
                font-size: 16px;
                width: 100%;
                box-sizing: border-box;
            }}
            a.btn:hover {{ background: #1b5e20; }}
            .logo {{ font-size: 48px; margin-bottom: 20px; }}
        </style>
    </head>
    <body>
        <div class="logo">✅</div>
        <h1>Calendar Connected!</h1>
        {"<div class='email'>📧 " + email + "</div>" if email else ""}
        <p>MeetBot will now automatically join all your Google Meet meetings
           and generate transcripts after each meeting ends.</p>

        <a class="btn" href="https://calendar.google.com/calendar/r/eventedit">
            Schedule a Meeting on Google Calendar
        </a>
    </body>
    </html>
    """
    return HTMLResponse(content=html)