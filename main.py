"""
main.py
-------
Entry point. Registers all routers.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI
from app.core.config import settings
from app.routers import manual_trigger_bot, webhook, calendar

app = FastAPI(
    title="Meeting Bot MVP",
    debug=settings.debug,
)

app.include_router(manual_trigger_bot.router,     prefix="/bot",     tags=["Bot"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
app.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
