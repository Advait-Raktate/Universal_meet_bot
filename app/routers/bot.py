"""
app/routers/bot.py
------------------
Endpoints:
  POST /bot/join            — send bot into a meeting
  POST /bot/{bot_id}/process — manually re-run pipeline for a bot
"""

import asyncio
from fastapi import APIRouter
from app.models.schemas import JoinMeetingRequest, JoinMeetingResponse, MeetingNotesResponse
from app.services.recall_service import create_bot, fetch_speaker_transcript, format_transcript
from app.services.llm_service import summarize_meeting

from app.services.llm_service import summarize_meeting, summarize_per_speaker
from app.models.schemas import JoinMeetingRequest, JoinMeetingResponse, MeetingNotesResponse, PerSpeakerSummaryResponse

router = APIRouter()


@router.post("/join", response_model=JoinMeetingResponse)
async def join_meeting(body: JoinMeetingRequest):
    """
    Sends the bot into a Google Meet.
    Recall will call /webhook/recall automatically when the meeting ends.
    """
    bot = await create_bot(body.meet_url, body.bot_name)

    return JoinMeetingResponse(
        bot_id=bot["id"],
        status="joining",
        message=f"Bot '{body.bot_name}' is joining the meeting. Notes will be ready after it ends."
    )


@router.post("/{bot_id}/process", response_model=MeetingNotesResponse)

async def process_bot(bot_id: str):
    """
    Manually triggers transcript fetch + LLM summarization for a bot.
    Use this if the webhook missed, or to re-run on an already finished meeting.
    """
    speaker_map = await fetch_speaker_transcript(bot_id)
    formatted   = format_transcript(speaker_map)
    notes       = await summarize_meeting(formatted)

    
   
    return MeetingNotesResponse(
        bot_id=bot_id,
        transcript=formatted,
        
        notes=notes
    )

    

   





@router.post("/{bot_id}/summary", response_model=PerSpeakerSummaryResponse)
async def per_speaker_summary(bot_id: str):
    """
    Returns per-person transcript + individual summary for each speaker.
    """
    speaker_map = await fetch_speaker_transcript(bot_id)
    formatted   = format_transcript(speaker_map)
    summaries   = await summarize_per_speaker(speaker_map)

    return PerSpeakerSummaryResponse(
        bot_id=bot_id,
        transcript=formatted,
        per_speaker_summary=summaries
    )


@router.get("/{bot_id}/transcript")
async def get_transcript(bot_id: str):
    speaker_map = await fetch_speaker_transcript(bot_id)
    formatted   = format_transcript(speaker_map)
    return {
        "bot_id": bot_id,
        "transcript": formatted
    }
