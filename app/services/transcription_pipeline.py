"""
services/transcription_pipeline.py
------------------------------------
Post-meeting pipelines.
  run_pipeline_zoom()   — Zoom: fetch → format → send downstream
  run_pipeline_gmeet()  — GMeet: fetch → clean → map emails → save JSON
"""
from app.services.recall_service import(
    get_download_url,
    download_raw_transcript,
    seconds_to_mmss,
    map_names_to_emails,
    format_transcript,
)

from app.services.calendar_service import get_attendees_by_meet_url
from app.services.helper import _send_to_downstream


def _parse_segments(raw: list[dict]) -> list[dict]:
    """
    Parses raw AssemblyAI transcript into segments with timestamps.
    Raw format from Recall:
    [
        {
            "participant": {"name": "Sanika"},
            "words": [
                {"text": "Hello", "start_timestamp": {"relative": 1.2}, ...},
                ...
            ]
        },
        ...
    ]
    Output:
    [
        {"name": "Sanika", "text": "Hello everyone", "start": "[00:01]", "end": "[00:05]"},
        ...
    ]
    """
    segments = []
    for segment in raw:
        name  = segment.get("participant", {}).get("name") or "Unknown"
        words = segment.get("words", [])
        if not words:
            continue
        text       = " ".join(w["text"] for w in words).strip()
        start_secs = words[0].get("start_timestamp", {}).get("relative", 0)
        end_secs   = words[-1].get("end_timestamp",  {}).get("relative", start_secs)
        if text:
            segments.append({
                "name":  name,
                "text":  text,
                "start": seconds_to_mmss(start_secs),
                "end":   seconds_to_mmss(end_secs),
            })
    return segments
async def run_pipeline(bot_id: str, meeting_title: str = "", meet_url: str = "" , attendee_emails: list = []):
    """
    Full post-meeting pipeline for any platform (GMeet, Zoom, Teams):
      1. Fetch raw AssemblyAI transcript from Recall
      2. Parse into segments with timestamps
      3. Fetch attendees from calendar
      4. Map speaker names → emails
      5. Format transcript
      6. Send to downstream API
    """
    print(f"\n[PIPELINE] Starting for bot: {bot_id} | title: {meeting_title}")

    try:
        # Step 1 — fetch raw transcript from Recall/AssemblyAI
        download_url = await get_download_url(bot_id)
        raw          = await download_raw_transcript(download_url)

        if not raw:
            print(f"[PIPELINE] Empty transcript for {bot_id}")
            return

        print(f"[PIPELINE] Raw segments count: {len(raw)}")

        # Step 2 — parse raw into segments with timestamps
        segments = _parse_segments(raw)


         # Step 3 — build attendees from pre-fetched emails
        attendees = [{"email": e, "displayName": e.split("@")[0]} for e in attendee_emails if e]
        print(f"[PIPELINE] Attendees: {[a['email'] for a in attendees]}")

        


        # Step 4 — map speaker names → emails
        email_segments = map_names_to_emails(segments, attendees)

        # Step 5 — format into readable transcript
        email_transcript = format_transcript(email_segments)
        print(f"\n── Transcript ───────────────────────────\n{email_transcript}")

        # Step 6 — send to downstream
        await _send_to_downstream({
            "project_name":  meeting_title,
            "transcription": email_transcript,
        })

        print(f"\n✅ [PIPELINE] Done for bot: {bot_id}")

    except Exception as e:
        print(f"[PIPELINE] Error for {bot_id}: {e}")
        raise