"""
app/services/llm_service.py
----------------------------
Sends the formatted transcript to OpenAI GPT-4o and returns
structured meeting notes: summary, decisions, action items.
"""

import os
from openai import AsyncOpenAI
from dotenv import load_dotenv

load_dotenv()

client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

SYSTEM_PROMPT = """
You are a professional meeting assistant.
You receive a meeting transcript with speaker names and what each person said.
Produce clean structured meeting notes.

Always respond in this exact format:

## Summary
2-3 sentences on what the meeting was about and the outcome.

## Key Decisions
- Decision made — agreed by whom

## Action Items
- [ ] Action — Owner: Name — Deadline: (if mentioned, else "Not specified")

## Key Discussion Points
- Important topics discussed without a clear decision

## Open Questions
- Unresolved questions from the meeting

Rules:
- Be concise and factual
- Only include what was actually said
- Do not invent or assume anything
- If the transcript has Hindi or Hinglish, still write notes in English
"""


async def summarize_meeting(formatted_transcript: str) -> str:
    """
    Sends transcript to GPT-4o, returns structured meeting notes as a string.
    """
    response = await client.chat.completions.create(
        model="gpt-4o",
        max_tokens=1500,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",   "content": f"Here is the meeting transcript:\n\n{formatted_transcript}"}
        ]
    )
    return response.choices[0].message.content


async def summarize_per_speaker(speaker_map: dict) -> dict:
    """
    Sends each speaker's text to GPT-4o separately.
    Returns a summary per person.
    """
    summaries = {}
    for name, utterances in speaker_map.items():
        combined = " ".join(utterances)
        response = await client.chat.completions.create(
            model="gpt-4o",
            max_tokens=500,
            messages=[
                {"role": "system", "content": "You are a helpful meeting assistant."},
                {"role": "user", "content": f"Summarize what {name} said in bullet points:\n\n{combined}"}
            ]
        )
        summaries[name] = response.choices[0].message.content
    return summaries
