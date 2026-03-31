"""
app/services/recall_service.py
-------------------------------
All Recall.ai API interactions:
  - Creating and sending the bot into a meeting
  - Fetching the transcript after the meeting ends (with participant emails)
"""

import os
import httpx
from collections import defaultdict
from dotenv import load_dotenv

load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE    = f"https://{RECALL_REGION}.recall.ai/api/v1"
PUBLIC_URL     = os.getenv("PUBLIC_URL")

HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Accept":        "application/json",
}


# ─────────────────────────────────────────
# Create bot and send into meeting
# ─────────────────────────────────────────

async def create_bot(meet_url: str, bot_name: str) -> dict:
    payload = {
        "meeting_url": meet_url,
        "bot_name":    bot_name,
        "webhook_url": f"{PUBLIC_URL}/webhook/recall",
        "recording_config": {
            "transcript": {
                "provider": {
                    "recallai_streaming": {
                        "language":         "en",
                        "identify_speaker": True
                    }
                }
            }
        }
    }

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{RECALL_BASE}/bot/",
            headers={**HEADERS, "Content-Type": "application/json"},
            json=payload,
            timeout=30
        )
        if r.status_code >= 400:
            print(f"[RECALL ERROR] {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────
# Fetch transcript after meeting ends
# ─────────────────────────────────────────

async def get_download_url(bot_id: str) -> str:
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{RECALL_BASE}/bot/{bot_id}/",
            headers=HEADERS,
            timeout=30
        )
        r.raise_for_status()
        bot = r.json()

    try:
        return (
            bot["recordings"][0]
               ["media_shortcuts"]
               ["transcript"]
               ["data"]
               ["download_url"]
        )
    except (KeyError, IndexError):
        raise Exception(f"Transcript not ready yet for bot: {bot_id}")


async def download_raw_transcript(download_url: str) -> list[dict]:
    async with httpx.AsyncClient() as client:
        r = await client.get(download_url, timeout=60)
        r.raise_for_status()
        return r.json()


async def fetch_speaker_transcript(bot_id: str) -> dict:
    """
    Returns transcript grouped by speaker with email info:
    {
        "Rahul Kumar": {
            "email":      "rahul@company.com",   # null if calendar not connected
            "utterances": ["we should ship this", "I'll send the PR"]
        },
        "Priya Sharma": {
            "email":      "priya@company.com",
            "utterances": ["agreed, let's go"]
        }
    }
    """
    download_url = await get_download_url(bot_id)
    raw          = await download_raw_transcript(download_url)

    # speaker_map: { name -> { email, utterances[] } }
    speaker_map = {}

    for segment in raw:
        participant = segment.get("participant", {})
        name  = participant.get("name")  or "Unknown"
        email = participant.get("email") or None   # only present if calendar connected

        text  = " ".join(w["text"] for w in segment.get("words", [])).strip()
        if not text:
            continue

        if name not in speaker_map:
            speaker_map[name] = {"email": email, "utterances": []}

        # update email if it was null before but is now available
        if email and not speaker_map[name]["email"]:
            speaker_map[name]["email"] = email

        speaker_map[name]["utterances"].append(text)

    return speaker_map


def format_transcript(speaker_map: dict) -> str:
    """
    Converts speaker map into a clean string for the LLM.
    Shows email next to name if available.

    Rahul Kumar (rahul@company.com):
      - we should ship this
      - I'll send the PR

    Priya Sharma (no email):
      - agreed, let's go
    """
    lines = []
    for name, data in speaker_map.items():
        email  = data.get("email")
        label  = f"{name} ({email})" if email else f"{name} (no email)"
        lines.append(f"{label}:")
        for u in data["utterances"]:
            lines.append(f"  - {u}")
        lines.append("")
    return "\n".join(lines)