from datetime import datetime, timezone

from app.services.recall_service import fetch_speaker_transcript, format_transcript
from app.services.helper import _schedule_bot_for_event,_send_to_downstream,_fetch_bot_title

async def run_pipeline(bot_id: str, meeting_title: str = ""):
    """
    Full post-meeting pipeline:
      1. Resolve meeting title (payload → bot metadata API → fallback)
      2. Fetch transcript from Recall (grouped by speaker)
      3. Format into readable text
      4. Summarize with LLM, passing the title for context
      5. Save notes to file named after the meeting
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id}")

    
    print(f"[PIPELINE] Meeting title: {meeting_title}")

    try:
        segments = await fetch_speaker_transcript(bot_id)
        if not segments:
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return
        speaker_map = format_transcript(segments) 
        payload = {
            "project_name":  meeting_title,
            "transcription": speaker_map,
        }
        print(payload)
        # ✅ Pass the title to summarize_meeting so the LLM has context
        await _send_to_downstream(payload)
        
    except Exception as e:
        print(f"[PIPELINE] Error for {bot_id}: {e}")
        