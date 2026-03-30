"""
app/services/recall_service.py
-------------------------------
All Recall.ai API interactions:
  - Creating and sending the bot into a meeting
  - Fetching the transcript after the meeting ends
"""
import json 
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
    """
    Sends a bot into the Google Meet.
    Uses Recall's default built-in transcription — no extra config needed.
    Recall will POST to /webhook/recall when the meeting ends.
    """
    payload = {
        "meeting_url": meet_url,
        "bot_name":    bot_name,
        "webhook_url": f"{PUBLIC_URL}/webhook/recall",
        "recording_config": {
            "transcript": {
                    "provider": {
                       # "recallai_streaming": {
                        #    "language": "auto",
                        #    "identify_speaker": True
                        #}
                        "assembly_ai_async_chunked": {
                    "speaker_labels": True,
                    "language_detection": True,
                    "format_text": True,
                    "punctuate": True,
                    "keyterms_prompt": [],        # ← keep empty, GPT-4o handles rest
                    "disfluencies": False         # ← removes umm, ahh automatically
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
        # Print exact error from Recall if it fails
        if r.status_code >= 400:
            print(f"[RECALL ERROR] {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()


# ─────────────────────────────────────────
# Fetch transcript after meeting ends
# ─────────────────────────────────────────

async def get_download_url(bot_id: str) -> str:
    """
    Calls GET /api/v1/bot/{bot_id}/ and extracts the transcript download URL.
    """
    async with httpx.AsyncClient() as client:
        r = await client.get(
            f"{RECALL_BASE}/bot/{bot_id}/",
            headers=HEADERS,
            timeout=30
        )
        r.raise_for_status()
        bot = r.json()

        #print(f"\n[DEBUG] Downloaded transcript type: {type(bot)}")

        print(f"\n[DEBUG] Full bot response: {json.dumps(bot, indent=2)}")

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
    """Downloads the raw transcript JSON array from Recall's CDN."""
    async with httpx.AsyncClient() as client:
        r = await client.get(download_url, timeout=60)
        r.raise_for_status()
        return r.json()


async def fetch_speaker_transcript(bot_id: str) -> dict[str, list[str]]:
    """
    Full two-step fetch. Returns transcript grouped by speaker:
    {
        "Rahul Kumar": ["we should ship this", "I'll send the PR"],
        "Priya Sharma": ["agreed, let's go"]
    }
    """
    download_url = await get_download_url(bot_id)
    raw          = await download_raw_transcript(download_url)

    speaker_map = defaultdict(list)
    for segment in raw:
        name  = segment.get("participant", {}).get("name") or "Unknown"
        
        
        words = segment.get("words", [])
        text  = " ".join(w["text"] for w in words).strip()
        if text:
            speaker_map[name].append(text)

    return dict(speaker_map)


def format_transcript(speaker_map: dict[str, list[str]]) -> str:
    """
    Converts speaker map into a clean string for the LLM.
    """
    lines = []
    for name, utterances in speaker_map.items():
        lines.append(f"{name}:")
        for u in utterances:
            lines.append(f"  - {u}")
        lines.append("")
    return "\n".join(lines)