"""
main.py
-------
Entry point. Registers all routers.

Run:
    uvicorn main:app --host 0.0.0.0 --port 8000 --reload
"""

from fastapi import FastAPI
from app.routers import bot, webhook
#from app.routers.auth import router as auth_router


app = FastAPI(title="Meeting Bot MVP")

app.include_router(bot.router,     prefix="/bot",     tags=["Bot"])
app.include_router(webhook.router, prefix="/webhook", tags=["Webhook"])
#app.include_router(auth_router)

@app.get("/health")
async def health():
    return {"status": "ok"}
