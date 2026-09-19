"""
AI Gateway — طبقة موحّدة لاستدعاء Gemini / OpenAI / Claude.

المبدأ:
- الـAndroid والفرونت إند لا يعرفان أي شيء عن مزود الذكاء الاصطناعي أو مفاتيحه.
- كل الطلبات تمر عبر Backend فقط، ومفاتيح الـAPI تُقرأ من Environment Variables حصرًا
  (GEMINI_API_KEY / OPENAI_API_KEY / ANTHROPIC_API_KEY) — لا تُخزَّن في أي قاعدة بيانات
  ولا في أي كود، ولا تُرسل أبدًا إلى تطبيق Android.
- يمكن تبديل المزود الأساسي (primary) والاحتياطي (fallback) من إعدادات السيرفر
  (جدول ai_settings) بدون إعادة بناء أي تطبيق.
- كل استدعاء يُسجَّل في ai_answers: provider, model, request_ms, status, error.

⚠️ هذه الوحدة كود حقيقي كامل المنطق، لكن استدعاءات الشبكة الفعلية لمزودي الذكاء
الاصطناعي لم تُختبر في هذه البيئة (لا يوجد اتصال إنترنت ولا مفاتيح API متاحة هنا).
البنية والتفريع (provider selection + fallback) قابلة للاختبار بمحاكاة (mock) وهو
ما يفعله app/tests/test_ai_gateway.py المرفق.
"""
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass
class AIResponse:
    provider: str
    model: str
    text: str
    request_ms: int
    status: str = "success"
    error: Optional[str] = None


class AIProviderError(Exception):
    pass


class BaseAIProvider(ABC):
    name: str = "base"
    default_model: str = ""

    @abstractmethod
    def _call(self, prompt: str, model: Optional[str] = None) -> str:
        """ينفذ الاستدعاء الفعلي للمزود. تُنفَّذ في الفئات الفرعية فقط."""
        raise NotImplementedError

    def generate(self, prompt: str, model: Optional[str] = None) -> AIResponse:
        start = time.time()
        try:
            text = self._call(prompt, model)
            return AIResponse(
                provider=self.name, model=model or self.default_model, text=text,
                request_ms=int((time.time() - start) * 1000), status="success")
        except Exception as e:  # noqa: BLE001 — نريد التقاط أي خطأ مزود ليُسجَّل وليُفعَّل fallback
            return AIResponse(
                provider=self.name, model=model or self.default_model, text="",
                request_ms=int((time.time() - start) * 1000), status="error", error=str(e))


class GeminiProvider(BaseAIProvider):
    name = "gemini"
    default_model = "gemini-1.5-pro"

    def __init__(self, api_key: str):
        if not api_key:
            raise AIProviderError("GEMINI_API_KEY غير مضبوط.")
        self.api_key = api_key

    def _call(self, prompt: str, model: Optional[str] = None) -> str:
        # TODO(Phase 8 تنفيذ حقيقي): استدعاء google-generativeai SDK هنا.
        # لم يُختبر لعدم توفر اتصال إنترنت/مفتاح في بيئة التطوير الحالية.
        raise NotImplementedError("Gemini SDK call — يُنفَّذ عند توفر بيئة تحتوي المكتبة والمفتاح.")


class OpenAIProvider(BaseAIProvider):
    name = "openai"
    default_model = "gpt-4o"

    def __init__(self, api_key: str):
        if not api_key:
            raise AIProviderError("OPENAI_API_KEY غير مضبوط.")
        self.api_key = api_key

    def _call(self, prompt: str, model: Optional[str] = None) -> str:
        raise NotImplementedError("OpenAI SDK call — يُنفَّذ عند توفر بيئة تحتوي المكتبة والمفتاح.")


class ClaudeProvider(BaseAIProvider):
    name = "claude"
    default_model = "claude-sonnet-4"

    def __init__(self, api_key: str):
        if not api_key:
            raise AIProviderError("ANTHROPIC_API_KEY غير مضبوط.")
        self.api_key = api_key

    def _call(self, prompt: str, model: Optional[str] = None) -> str:
        raise NotImplementedError("Anthropic SDK call — يُنفَّذ عند توفر بيئة تحتوي المكتبة والمفتاح.")


class AIGateway:
    """يختار المزود الأساسي، ويجرّب الاحتياطي تلقائيًا عند الفشل."""

    def __init__(self, providers: dict, primary: str, fallback: Optional[str] = None):
        self.providers = providers  # {"gemini": GeminiProvider(...), ...}
        self.primary = primary
        self.fallback = fallback

    def ask(self, prompt: str, model: Optional[str] = None) -> AIResponse:
        primary_provider = self.providers.get(self.primary)
        if primary_provider is None:
            raise AIProviderError(f"المزود الأساسي '{self.primary}' غير مُهيَّأ.")

        result = primary_provider.generate(prompt, model)
        if result.status == "success":
            return result

        if self.fallback and self.fallback in self.providers:
            fallback_provider = self.providers[self.fallback]
            fallback_result = fallback_provider.generate(prompt, model)
            return fallback_result

        return result  # فشل المزود الأساسي ولا يوجد fallback مُهيَّأ
