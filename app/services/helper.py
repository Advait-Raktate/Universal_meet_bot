import asyncio
from datetime import datetime, timezone
import httpx
from fastapi import APIRouter, Request
from app.core.config import settings
from app.services.recall_service import fetch_speaker_transcript, format_transcript

        
async def _send_to_downstream(payload: dict):
    """
    POSTs { project_name, transcription } to your downstream API.
    Swap the URL / auth headers to match your API's requirements.
    """
    if not settings.downstream_api:
        print("[DOWNSTREAM] DOWNSTREAM_API_URL not set — skipping")
        return

    async with httpx.AsyncClient() as client:
        res = await client.post(
            settings.downstream_api,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )

    if res.status_code in (200, 201):
        print(f"[DOWNSTREAM] ✅ Sent successfully: {res.status_code}")
    else:
        print(f"[DOWNSTREAM] ❌ Failed: {res.status_code} — {res.text}")        
        
