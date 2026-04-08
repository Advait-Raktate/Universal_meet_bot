from datetime import datetime, timezone

from app.services.recall_service import fetch_speaker_transcript, format_transcript
from app.services.helper import _schedule_bot_for_event,_send_to_downstream,_fetch_bot_title
from app.routers.bot import get_meet_url
from app.services.calendar_service import get_attendees_by_meet_url
from app.services.recall_service import map_names_to_emails, format_transcript_with_timestamps


async def run_pipeline(bot_id: str, meeting_title: str = ""):
    ...
    segments  = map_names_to_emails(segments, attendees)

    # for downstream API — simple format
    speaker_map = format_transcript(segments)
    speaker_map = await fix_technical_terms(speaker_map)

    # for JSON file — timestamped format
    email_transcript = format_transcript_with_timestamps(segments)
    email_transcript = await fix_technical_terms(email_transcript)

    # send to downstream
    payload = {
        "project_name":  meeting_title,
        "transcription": speaker_map,  # simple format
    }
    await _send_to_downstream(payload)

    # save to JSON
    result = {
        "bot_id":              bot_id,
        "meeting_title":       meeting_title,
        "meet_url":            meet_url,
        "attendees":           attendees,
        "transcript_by_email": email_transcript,  # timestamped format
    }