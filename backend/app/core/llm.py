"""LLM 工厂：根据配置创建聊天模型。"""

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


def get_llm(settings: Settings | None = None) -> BaseChatModel:
    """按已配置的 API Key 创建模型。

    注意：default_model 需与 provider 匹配（如 claude-* / gpt-*）。
    """
    settings = settings or get_settings()

    if settings.anthropic_api_key:
        return ChatAnthropic(
            model=settings.default_model,
            api_key=settings.anthropic_api_key,
            temperature=0,
        )
    if settings.openai_api_key:
        kwargs: dict = {
            "model": settings.default_model,
            "api_key": settings.openai_api_key,
            "temperature": 0,
        }
        # 支持 OpenAI 兼容服务（DeepSeek 等）
        if settings.openai_base_url:
            kwargs["openai_api_base"] = settings.openai_base_url
        return ChatOpenAI(**kwargs)

    raise RuntimeError(
        "未配置 LLM API Key，请在 backend/.env 中设置 OPENAI_API_KEY 或 ANTHROPIC_API_KEY"
    )
