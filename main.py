"""
main.py
-------
Entry point. Registers all routers.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI
<<<<<<< HEAD
from app.routers import bot, webhook
#from app.routers.auth import router as auth_router

=======
from app.routers import bot, webhook,calendar
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d

app = FastAPI(title="Meeting Bot MVP")

app.include_router(bot.router,     prefix="/bot",     tags=["Bot"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
<<<<<<< HEAD
#app.include_router(auth_router)
=======
app.include_router(calendar.router, prefix="/calendar", tags=["Calendar"])
>>>>>>> 84ce54fa2c59c182c238b90a087ab7453143c47d

@app.get("/health")
async def health():
    return {"status": "ok"}
