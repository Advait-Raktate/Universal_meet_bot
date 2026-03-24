"""
app/models/schemas.py
---------------------
Pydantic models for request bodies and response shapes.
"""

from pydantic import BaseModel
from typing import Optional


# ─────────────────────────────────────────
# Request models
# ─────────────────────────────────────────

class JoinMeetingRequest(BaseModel):
    meet_url: str                          # https://meet.google.com/xxx-yyy-zzz
    bot_name: Optional[str] = "Notes Bot"  # name shown in the meeting


# ─────────────────────────────────────────
# Response models
# ─────────────────────────────────────────

class JoinMeetingResponse(BaseModel):
    bot_id:  str
    status:  str
    message: str


class MeetingNotesResponse(BaseModel):
    bot_id:     str
    transcript: str   # formatted speaker → utterances
    notes:      str   # LLM generated summary + action items


class TranscriptSegment(BaseModel):
    speaker:  str
    text:     str


class SpeakerTranscript(BaseModel):
    bot_id:   str
    speakers: dict[str, list[str]]   # { "Rahul": ["said this", "said that"] }
