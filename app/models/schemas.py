from pydantic import BaseModel
from typing import Optional


class JoinMeetingRequest(BaseModel):
    meet_url: str
    bot_name: Optional[str] = "Notes Bot"


class JoinMeetingResponse(BaseModel):
    bot_id:  str
    status:  str
    message: str


class MeetingNotesResponse(BaseModel):
    bot_id:     str
    transcript: str
    notes:      str


class SpeakerInfo(BaseModel):
    email:      Optional[str]        # null if calendar not connected or duplicate name
    utterances: list[str]


class SpeakerTranscript(BaseModel):
    bot_id:   str

    speakers: dict[str, list[str]]   # { "Rahul": ["said this", "said that"] }



class PerSpeakerSummaryResponse(BaseModel):
    bot_id: str
    transcript: str
    per_speaker_summary: dict

    speakers: dict[str, SpeakerInfo]  # { "Rahul Kumar": { email, utterances } }

