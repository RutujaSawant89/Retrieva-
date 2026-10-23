from fastapi import APIRouter

from app.api.v1 import admin, analytics, auth, chat, collections, documents, evaluation, research

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(admin.router)
api_router.include_router(documents.router)
api_router.include_router(collections.router)
api_router.include_router(chat.router)
api_router.include_router(analytics.router)
api_router.include_router(research.router)
api_router.include_router(evaluation.router)
