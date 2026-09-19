import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.ai_gateway import AIGateway, AIResponse, BaseAIProvider  # noqa: E402
from app.services.ai_question_generator import (  # noqa: E402
    GenerationError, GenerationRequest, build_prompt, generate_questions,
)


class FakeProvider(BaseAIProvider):
    def __init__(self, name, response_text=None, should_fail=False):
        self.name = name
        self.default_model = f"{name}-model"
        self._response_text = response_text
        self._should_fail = should_fail

    def _call(self, prompt, model=None):
        if self._should_fail:
            raise RuntimeError("انقطع الاتصال (محاكاة)")
        return self._response_text


VALID_JSON_RESPONSE = (
    '[{"question": "من هو أحمد عرابي؟", "answer": "قائد عسكري"}, '
    '{"question": "من هو سعد زغلول؟", "answer": "زعيم وطني"}]'
)


class TestBuildPrompt(unittest.TestCase):
    def test_prompt_includes_lesson_and_type(self):
        req = GenerationRequest(lesson_id=1, lesson_name="الثورة العرابية", count=3, question_type="WHO_IS")
        prompt = build_prompt(req)
        self.assertIn("الثورة العرابية", prompt)
        self.assertIn("WHO_IS", prompt)
        self.assertIn("3", prompt)

    def test_zero_count_rejected(self):
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=0, question_type="MCQ")
        with self.assertRaises(GenerationError):
            build_prompt(req)

    def test_excessive_count_rejected(self):
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=1000, question_type="MCQ")
        with self.assertRaises(GenerationError):
            build_prompt(req)


class TestGenerateQuestions(unittest.TestCase):
    def test_successful_generation_marks_needs_review_and_ai_generated(self):
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", VALID_JSON_RESPONSE)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="الثورة العرابية", count=2, question_type="WHO_IS")
        results = generate_questions(gateway, req)

        self.assertEqual(len(results), 2)
        for r in results:
            self.assertEqual(r.status, "NEEDS_REVIEW")
            self.assertEqual(r.source_type, "AI_GENERATED")
            self.assertEqual(r.ai_provider, "gemini")
        self.assertNotEqual(results[0].status, "APPROVED")

    def test_never_returns_approved_status_under_any_circumstance(self):
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", VALID_JSON_RESPONSE)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=2, question_type="MCQ")
        for r in generate_questions(gateway, req):
            self.assertNotEqual(r.status, "APPROVED")

    def test_all_providers_failing_raises_generation_error(self):
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", should_fail=True)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=1, question_type="MCQ")
        with self.assertRaises(GenerationError):
            generate_questions(gateway, req)

    def test_fallback_provider_used_when_primary_fails(self):
        gateway = AIGateway(
            providers={
                "gemini": FakeProvider("gemini", should_fail=True),
                "openai": FakeProvider("openai", VALID_JSON_RESPONSE),
            },
            primary="gemini", fallback="openai",
        )
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=2, question_type="MCQ")
        results = generate_questions(gateway, req)
        self.assertEqual(results[0].ai_provider, "openai")

    def test_invalid_json_response_raises_clear_error(self):
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", "هذا ليس JSON على الإطلاق")},
                             primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=1, question_type="MCQ")
        with self.assertRaises(GenerationError):
            generate_questions(gateway, req)

    def test_markdown_fenced_json_is_handled(self):
        fenced = f"```json\n{VALID_JSON_RESPONSE}\n```"
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", fenced)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=2, question_type="WHO_IS")
        results = generate_questions(gateway, req)
        self.assertEqual(len(results), 2)

    def test_empty_question_items_skipped_not_invented(self):
        response = '[{"question": "", "answer": "شيء"}, {"question": "سؤال حقيقي", "answer": "جواب"}]'
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", response)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=2, question_type="MCQ")
        results = generate_questions(gateway, req)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].question, "سؤال حقيقي")

    def test_all_empty_raises_error_instead_of_returning_nothing_silently(self):
        response = '[{"question": "", "answer": ""}]'
        gateway = AIGateway(providers={"gemini": FakeProvider("gemini", response)}, primary="gemini")
        req = GenerationRequest(lesson_id=1, lesson_name="درس", count=1, question_type="MCQ")
        with self.assertRaises(GenerationError):
            generate_questions(gateway, req)


if __name__ == "__main__":
    unittest.main(verbosity=2)
