import os
import json
from datetime import datetime
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from google_auth_oauthlib.flow import Flow
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
GOOGLE_REDIRECT_URI  = "https://us-west-2.recall.ai/api/v1/calendar/google_oauth_callback/"

SCOPES = [
    "https://www.googleapis.com/auth/calendar.events.readonly",
    "https://www.googleapis.com/auth/userinfo.email"
]

STATE_FILE = "state_store.json"


def save_state(state: str, flow_data: dict):
    store = {}
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            store = json.load(f)
    store[state] = flow_data
    with open(STATE_FILE, "w") as f:
        json.dump(store, f)


def pop_state(state: str):
    if not os.path.exists(STATE_FILE):
        return None
    with open(STATE_FILE, "r") as f:
        store = json.load(f)
    flow_data = store.pop(state, None)
    with open(STATE_FILE, "w") as f:
        json.dump(store, f)
    return flow_data


def get_flow():
    return Flow.from_client_config(
        {
            "web": {
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "auth_uri":      "https://accounts.google.com/o/oauth2/auth",
                "token_uri":     "https://oauth2.googleapis.com/token",
            }
        },
        scopes=SCOPES,
        redirect_uri=GOOGLE_REDIRECT_URI,
    )


@router.get("/auth/google")
async def google_auth():
    flow = get_flow()

    auth_url, state = flow.authorization_url(
        access_type="offline",
        prompt="consent",
        include_granted_scopes="true",
        code_verifier=None        # ← disable PKCE
    )

    # Manually rebuild URL without code_challenge
    from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
    parsed   = urlparse(auth_url)
    params   = parse_qs(parsed.query, keep_blank_values=True)

    # ← Remove PKCE params
    params.pop("code_challenge",        None)
    params.pop("code_challenge_method", None)

    clean_query = urlencode({k: v[0] for k, v in params.items()})
    clean_url   = urlunparse(parsed._replace(query=clean_query))

    print(f"[AUTH] Clean URL: {clean_url}")
    save_state(state, {"state": state})
    return RedirectResponse(clean_url)


@router.get("/auth/google/callback")
async def google_callback(code: str, state: str = ""):
    flow_data = pop_state(state)

    if not flow_data:
        return {"error": "Invalid state — please try /auth/google again"}

    os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

    flow = get_flow()
    flow.fetch_token(code=code)

    refresh_token = flow.credentials.refresh_token
    print(f"[AUTH] Refresh token: {refresh_token}")

    from app.services.calendar_service import create_recall_calendar
    calendar = await create_recall_calendar(refresh_token)

    return {
        "message":     "Calendar connected successfully!",
        "calendar_id": calendar["id"]
    }