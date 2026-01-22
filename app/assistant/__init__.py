"""AI Assistant package for deal summaries using z.ai (Grok)."""

from app.assistant.routes import router
from app.assistant.zai_service import ZAIService, generate_deal_summary

__all__ = ["router", "ZAIService", "generate_deal_summary"]
