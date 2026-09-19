import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.ai_gateway import AIGateway, AIProviderError, BaseAIProvider  # noqa: E402


class FakeProvider(BaseAIProvider):
    """مزود وهمي للاختبار بدون أي اتصال شبكة حقيقي."""
    def __init__(self, name, should_fail=False, response_text="ok"):
        self.name = name
        self.default_model = f"{name}-model"
        self._should_fail = should_fail
        self._response_text = response_text

    def _call(self, prompt, model=None):
        if self._should_fail:
            raise RuntimeError(f"{self.name} انقطع الاتصال (محاكاة)")
        return self._response_text


class TestAIGateway(unittest.TestCase):
    def test_primary_success_returns_primary_response(self):
        gw = AIGateway(
            providers={"gemini": FakeProvider("gemini", response_text="رد من Gemini")},
            primary="gemini",
        )
        result = gw.ask("اشرح لي الدرس")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.provider, "gemini")
        self.assertEqual(result.text, "رد من Gemini")

    def test_falls_back_when_primary_fails(self):
        gw = AIGateway(
            providers={
                "gemini": FakeProvider("gemini", should_fail=True),
                "openai": FakeProvider("openai", response_text="رد من OpenAI الاحتياطي"),
            },
            primary="gemini",
            fallback="openai",
        )
        result = gw.ask("اشرح لي الدرس")
        self.assertEqual(result.status, "success")
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.text, "رد من OpenAI الاحتياطي")

    def test_returns_error_when_no_fallback_configured(self):
        gw = AIGateway(
            providers={"gemini": FakeProvider("gemini", should_fail=True)},
            primary="gemini",
        )
        result = gw.ask("اشرح لي الدرس")
        self.assertEqual(result.status, "error")
        self.assertIn("انقطع الاتصال", result.error)

    def test_returns_error_when_both_primary_and_fallback_fail(self):
        gw = AIGateway(
            providers={
                "gemini": FakeProvider("gemini", should_fail=True),
                "openai": FakeProvider("openai", should_fail=True),
            },
            primary="gemini",
            fallback="openai",
        )
        result = gw.ask("اشرح لي الدرس")
        self.assertEqual(result.status, "error")
        self.assertEqual(result.provider, "openai")  # آخر مزود جُرِّب

    def test_raises_when_primary_not_configured(self):
        gw = AIGateway(providers={}, primary="claude")
        with self.assertRaises(AIProviderError):
            gw.ask("اشرح لي الدرس")

    def test_response_records_timing(self):
        gw = AIGateway(providers={"gemini": FakeProvider("gemini")}, primary="gemini")
        result = gw.ask("سؤال")
        self.assertIsInstance(result.request_ms, int)
        self.assertGreaterEqual(result.request_ms, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
