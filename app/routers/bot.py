"""
app/routers/bot.py
------------------
Endpoints:
  POST /bot/join              — send bot into a meeting
  POST /bot/{bot_id}/process  — manually re-run pipeline for a bot
  POST /bot/{bot_id}/summary  — per speaker summary
  GET  /bot/{bot_id}/transcript — get raw transcript
"""


import json
import asyncio
from pathlib import Path
from fastapi import APIRouter
from app.schemas.schemas import JoinMeetingRequest, JoinMeetingResponse, MeetingNotesResponse
from app.services.recall_service import create_bot, fetch_speaker_transcript, format_transcript
#from app.services.llm_service import summarize_meeting, summarize_per_speaker

router = APIRouter()

# ─── Persistent bot store (survives server restarts) ─────────────────────────

"""
BOT_STORE_FILE = Path("bot_store.json")

def save_bot_store(bot_id: str, meet_url: str, title: str = ""):
    store = {}
    if BOT_STORE_FILE.exists():
        store = json.loads(BOT_STORE_FILE.read_text())
    store[bot_id] = {"meet_url": meet_url, "title": title}
    BOT_STORE_FILE.write_text(json.dumps(store, indent=2))

    

def get_meet_url(bot_id: str) -> str:
    if not BOT_STORE_FILE.exists():
        return ""
    store = json.loads(BOT_STORE_FILE.read_text())
    entry = store.get(bot_id, {})
    return entry.get("meet_url", "") if isinstance(entry, dict) else entry

    

def get_meeting_title(bot_id: str) -> str:
    if not BOT_STORE_FILE.exists():
        return ""
    store = json.loads(BOT_STORE_FILE.read_text())
    entry = store.get(bot_id, {})
    return entry.get("title", "") if isinstance(entry, dict) else ""


    """


# ─── Join meeting ─────────────────────────────────────────────────────────────
@router.post("/join", response_model=JoinMeetingResponse)
async def join_meeting(body: JoinMeetingRequest):
    """
    Sends the bot into a Google Meet.
    Recall will call /webhook/recall automatically when the meeting ends.
    """
    bot = await create_bot(body.meet_url, body.bot_name)
    save_bot_store(bot["id"], body.meet_url)  # ← persisted to file
    print(f"[BOT] Saved bot_id={bot['id']} → meet_url={body.meet_url}")
    return JoinMeetingResponse(
        bot_id=bot["id"],
        status="joining",
        message=f"Bot '{body.bot_name}' is joining the meeting. Notes will be ready after it ends."
    )


# ─── Manually re-run pipeline ─────────────────────────────────────────────────
@router.post("/{bot_id}/process", response_model=MeetingNotesResponse)
async def process_bot(bot_id: str):
    """
    Manually triggers transcript fetch + LLM summarization for a bot.
    Use this if the webhook missed, or to re-run on an already finished meeting.
    """
    speaker_map = await fetch_speaker_transcript(bot_id)
    formatted   = format_transcript(speaker_map)
    #notes       = await summarize_meeting(formatted)

    return MeetingNotesResponse(
        bot_id=bot_id,
        transcript=formatted,
        notes=notes
    )


# ─── Get raw transcript ───────────────────────────────────────────────────────
@router.get("/{bot_id}/transcript")
async def get_transcript(bot_id: str):
    speaker_map = await fetch_speaker_transcript(bot_id)
    formatted   = format_transcript(speaker_map)
    return {
        "bot_id":     bot_id,
        "transcript": formatted
    }