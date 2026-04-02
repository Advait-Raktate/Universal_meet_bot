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


class SpeakerInfo(BaseModel):
    email:      Optional[str]        # null if calendar not connected or duplicate name
    utterances: list[str]


class SpeakerTranscript(BaseModel):
    bot_id:   str
    speakers: dict[str, SpeakerInfo]  # { "Rahul Kumar": { email, utterances } }