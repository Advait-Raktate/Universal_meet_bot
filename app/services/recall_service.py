
"""
app/services/recall_service.py
-------------------------------
All Recall.ai API interactions:
  - Creating and sending the bot into a meeting
  - Fetching the transcript after the meeting ends (with participant emails)
"""

import httpx
#from collections import defaultdict
from app.core.config import settings

# ─────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────

def seconds_to_mmss(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs    = int(seconds % 60)
    return f"[{minutes:02d}:{secs:02d}]"

# ─────────────────────────────────────────
# Create bot and send into meeting
# ─────────────────────────────────────────

async def create_bot(meet_url: str, bot_name: str) -> dict:
    payload = {
        "meeting_url": meet_url,
        "bot_name":    bot_name,
        "webhook_url": settings.webhook_recall_url,
        "recording_config": {
            "transcript": {
                "provider": {
                    "assembly_ai_async_chunked": {
                    "speaker_labels":     True,
                    "language_detection": True,
                    "format_text":        True,
                    "punctuate":          True,
                    #"speech_model":       "universal-3-pro",  # ← uncomment this
                    "keyterms_prompt":    [],
                    "disfluencies":       False,
}
                    }
                }
            }
        }
    

    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{settings.recall_base_v1}/bot/",
            headers={**settings.recall_headers, "Content-Type": "application/json"},
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
            f"{settings.recall_base_v1}/bot/{bot_id}/",
            headers=settings.recall_headers_accept,
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


async def fetch_speaker_transcript(bot_id: str) -> list[dict]:
    """
    Returns transcript as an ordered list of segments:
    [
        { "name": "Advait Raktate",  "text": "Good morning Mahinder." },
        { "name": "Mahendra Yadav",  "text": "Again it's afternoon." },
        ...
    ]
    """
    download_url = await get_download_url(bot_id)
    raw          = await download_raw_transcript(download_url)

    segments = []
    for segment in raw:
        name = segment.get("participant", {}).get("name") or "Unknown"
        text = " ".join(w["text"] for w in segment.get("words", [])).strip()
        if not text:
            continue
        segments.append({"name": name, "text": text})

    return segments

def map_names_to_emails(segments: list[dict], attendees: list[dict]) -> list[dict]:
    name_to_email = {}
    for seg in segments:
        name = seg["name"]
        if name in name_to_email:
            continue
        first_name = name.split()[0].lower()

        matched = next(
            (a["email"] for a in attendees
             if a.get("displayName", "").strip() == name.strip()), None
        )
        if not matched:
            matched = next(
                (a["email"] for a in attendees
                 if a["email"].split("@")[0].lower() == first_name), None
            )
        if not matched:
            matched = name

        name_to_email[name] = matched

    return [
        {
            "name":  name_to_email[s["name"]],
            "text":  s["text"],
            "start": s.get("start", ""),   # ← use .get() so it works with or without
            "end":   s.get("end", ""),
        }
        for s in segments
    ]


def format_transcript(segments: list[dict]) -> str:
    """
    Converts ordered segments into a clean sequential conversation string.

    Advait Raktate: Good morning Mahinder.
    Mahendra Yadav: Again it's afternoon.
    Advait Raktate: That's okay. So what are you doing today?
    """
    #return "\n".join(f"{s['name']}: {s['text']}" for s in segments)
    lines = []
    for s in segments:
        start = s.get("start", "")
        end   = s.get("end", "")
        if start and end:
            lines.append(f"{start} - {end} {s['name']}:")
            lines.append(f"  - {s['text']}")
            lines.append("")
        else:
            lines.append(f"{s['name']}: {s['text']}")
    return "\n".join(lines)