"""
app/services/recall_service.py
-------------------------------
All Recall.ai API interactions:
  - Creating and sending the bot into a meeting
  - Fetching the transcript after the meeting ends
"""
import os
import asyncio
import httpx
from dotenv import load_dotenv
#from app.services.recall_service import RECALL_HEADERS, RECALL_BASE_V2


load_dotenv()

RECALL_API_KEY = os.getenv("RECALL_API_KEY")
RECALL_REGION  = os.getenv("RECALL_REGION", "us-west-2")
RECALL_BASE    = f"https://{RECALL_REGION}.recall.ai/api/v1"
PUBLIC_URL     = os.getenv("PUBLIC_URL")

RECALL_BASE_V2 = f"https://{RECALL_REGION}.recall.ai/api/v2"


RECALL_HEADERS = {
    "Authorization": f"Token {RECALL_API_KEY}",
    "Accept":        "application/json",
}


# ─────────────────────────────────────────
# Create bot and send into meeting
# ─────────────────────────────────────────

async def create_bot(meet_url: str, bot_name: str) -> dict:
    """
    Sends a bot into the Google Meet.
    Recall will POST to /webhook/recall when the meeting ends.
    """
    payload = {
        "meeting_url": meet_url,
        "bot_name":    bot_name,
        "webhook_url": f"{PUBLIC_URL}/webhook/recall",
        "recording_config": {
            "transcript": {
                "provider": {
                    "assembly_ai_async_chunked": {
                        "speaker_labels":     True,
                        "language_detection": True,
                        #"speech_model":       "universal-3-pro",
                        "format_text":        True,
                        "punctuate":          True,
                        "keyterms_prompt":    [],
                        "disfluencies":       False
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
# Helpers
# ─────────────────────────────────────────

def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs    = int(seconds % 60)
    return f"[{minutes:02d}:{secs:02d}]"


# ─────────────────────────────────────────
# Fetch transcript after meeting ends
# ─────────────────────────────────────────

async def get_download_url(bot_id: str) -> str:
    """
    Calls GET /api/v1/bot/{bot_id}/ and extracts the transcript download URL.
    Retries up to 10 times with 15s gap — AssemblyAI takes time after bot.done.
    """
    max_retries  = 10
    wait_seconds = 15

    for attempt in range(max_retries):
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{RECALL_BASE}/bot/{bot_id}/",
                headers=RECALL_HEADERS,
                timeout=30
            )
             # bot not found — likely created with different API key
            if r.status_code == 404:
                raise Exception(f"Bot {bot_id} not found — may have been created with a different API key")
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
            print(f"[RECALL] Attempt {attempt+1}/{max_retries} — transcript URL not ready, waiting {wait_seconds}s...")
            await asyncio.sleep(wait_seconds)

    raise Exception(f"Transcript not ready after {max_retries} retries for bot: {bot_id}")


async def download_raw_transcript(download_url: str) -> list[dict]:
    """Downloads the raw transcript JSON array from Recall's CDN."""
    async with httpx.AsyncClient() as client:
        r = await client.get(download_url, timeout=60)
        r.raise_for_status()
        return r.json()


async def fetch_speaker_transcript(bot_id: str) -> list[dict]:
    """
    Returns transcript as ordered conversation list with timestamps:
    [
        {
            "name":  "Sanika Patane",
            "text":  "Hello. Good afternoon.",
            "start": "[01:00]",
            "end":   "[01:05]"
        },
        ...
    ]
    Retries if transcript content is empty.
    """
    max_retries  = 10
    wait_seconds = 15

    raw = []
    for attempt in range(max_retries):
        download_url = await get_download_url(bot_id)
        raw          = await download_raw_transcript(download_url)

        print(f"[DEBUG] raw transcript length: {len(raw)}")

        if len(raw) > 0:
            break

        print(f"[RECALL] Attempt {attempt+1}/{max_retries} — transcript empty, waiting {wait_seconds}s...")
        await asyncio.sleep(wait_seconds)

    segments = []
    for segment in raw:
        name  = segment.get("participant", {}).get("name") or "Unknown"
        words = segment.get("words", [])
        if not words:
            continue
        text       = " ".join(w["text"] for w in words).strip()
        start_secs = words[0].get("start_timestamp", {}).get("relative", 0)
        end_secs   = words[-1].get("end_timestamp", {}).get("relative", start_secs)
        if text:
            segments.append({
                "name":  name,
                "text":  text,
                "start": seconds_to_mmss(start_secs),
                "end":   seconds_to_mmss(end_secs)
    })

    return segments

def map_names_to_emails(
    segments:  list[dict],
    attendees: list[dict]
) -> list[dict]:
    """
    Replaces speaker names with emails in ordered segments.
    Matching priority:
      1. Exact full displayName match
      2. First name vs email prefix
      3. Fallback to original name
    """
    name_to_email = {}

    for seg in segments:
        name = seg["name"]
        if name in name_to_email:
            continue

        first_name = name.split()[0].lower()

        # Priority 1
        matched = next(
            (a["email"] for a in attendees
             if a.get("displayName", "").strip() == name.strip()),
            None
        )
        print(f"[MAP] '{name}' → Priority 1 (displayName): {matched}")

        # Priority 2
        if not matched:
            matched = next(
                (a["email"] for a in attendees
                 if a["email"].split("@")[0].lower() == first_name),
                None
            )
            print(f"[MAP] '{name}' → Priority 2 (first name): {matched}")

        # Priority 3
        if not matched:
            matched = name
            print(f"[MAP] '{name}' → Priority 3 (fallback): {matched}")

        name_to_email[name] = matched

    return [
        {
            "name":  name_to_email[s["name"]],
            "text":  s["text"],
            "start": s["start"],
            "end":   s["end"]
        }
        for s in segments
    ]


def format_transcript(segments: list[dict]) -> str:
    """
    Formats ordered conversation with time ranges.
    Output:
      [01:00 - 01:05] sanika@arcitech.ai:
        - Hello. Good afternoon.

      [01:06 - 01:10] vaibhavi@arcitech.ai:
        - Hi how are you
    """
    if not segments:
        return ""

    lines = []
    for seg in segments:
        lines.append(f"{seg['start']} - {seg['end']} {seg['name']}:")
        lines.append(f"  - {seg['text']}")
        lines.append("")

    return "\n".join(lines)


async def fetch_and_format_transcript(bot_id: str) -> str:
    """
    Full pipeline:
      1. Fetch raw transcript from Recall (with retry)
      2. Format as ordered conversation with timestamps
      3. Fix Hindi → Hinglish + tech terms via GPT-4o
      4. Return clean LLM-ready transcript string
    """
    #from app.services.llm_service import fix_technical_terms

    segments      = await fetch_speaker_transcript(bot_id)
    raw_formatted = format_transcript(segments)

    print("[TRANSCRIPT] Raw formatted transcript:\n", raw_formatted)

    if not raw_formatted.strip():
        print("[TRANSCRIPT] Empty transcript — skipping fix_technical_terms")
        return ""

        return raw_formatted 


def format_transcript_with_timestamps(segments: list[dict]) -> str:
    """
    Timestamped format for JSON file.
    [00:13] - [00:18] sanika@arcitech.ai:
      - Hello good morning
    """
    if not segments:
        return ""
    lines = []
    for seg in segments:
        lines.append(f"{seg['start']} - {seg['end']} {seg['name']}:")
        lines.append(f"  - {seg['text']}")
        lines.append("")
    return "\n".join(lines)


async def get_meet_url_from_bot(bot_id: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        res = await client.get(
            f"{RECALL_BASE_V1}/bot/{bot_id}/",
            headers=RECALL_HEADERS,
            timeout=30
        )

    if res.status_code != 200 or not res.content:
        print(f"[BOT] Failed to fetch bot {bot_id}: {res.status_code}")
        return "", ""

    try:
        data = res.json()
    except Exception as e:
        print(f"[BOT] JSON parse error: {e}")
        return "", ""

    meet_url = data.get("meeting_url", "")
    title    = data.get("metadata", {}).get("title", "")
    return meet_url, title  # ← returns tuple
