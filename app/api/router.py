"""The one router the app mounts. A new resource module is added here."""

from fastapi import APIRouter

from app.api import auth, chat, user

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(user.router)
api_router.include_router(chat.router)
