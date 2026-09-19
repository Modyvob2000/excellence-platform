"""
AI Question Generation — مسار منفصل تمامًا عن "استخراج من مصدر" (import_pipeline.py).

فرق جوهري:
- استخراج (import_pipeline): يأخذ نصًا موجودًا فعليًا في ملف ويستخرج منه أسئلة موجودة بالفعل.
- توليد (هذا الملف): يطلب من AI Gateway اختراع أسئلة جديدة بناءً على وصف
  (مرحلة/صف/مادة/وحدة/درس/عدد/نوع) — المحتوى الناتج **ليس** من مصدر موثّق.

لذلك كل سؤال هنا يُعلَّم دائمًا:
  source_type = "AI_GENERATED"
  status = "NEEDS_REVIEW"  (أبدًا APPROVED تلقائيًا مهما كانت جودة رد الـAI)
ويُسجَّل provider/model المستخدم لكل سؤال شفافيةً كاملة.

مفصول عن AIGateway الفعلي عبر حقن AIGateway (DI) — قابل للاختبار الكامل بمزود وهمي
بدون أي اتصال إنترنت حقيقي (انظر test_ai_question_generator.py).
"""
import json
from dataclasses import dataclass, field
from typing import List, Optional

from app.ai_gateway import AIGateway


class GenerationError(Exception):
    pass


@dataclass
class GeneratedQuestion:
    question: str
    answer: str
    canonical_type: str
    source_type: str = "AI_GENERATED"
    status: str = "NEEDS_REVIEW"  # قاعدة صارمة: لا يوجد مسار آخر يغيّر هذا هنا
    ai_provider: Optional[str] = None
    ai_model: Optional[str] = None


@dataclass
class GenerationRequest:
    lesson_id: int
    lesson_name: str
    count: int
    question_type: str  # MCQ | TRUE_FALSE | WHO_IS | ... (نوع واحد لكل طلب توليد، كما في المواصفة)


PROMPT_TEMPLATE = """أنت مساعد تعليمي. اكتب {count} سؤال من نوع {qtype} عن درس بعنوان: "{lesson}".
أرجع النتيجة بصيغة JSON فقط، كمصفوفة عناصر بالشكل التالي بالضبط، بدون أي نص إضافي:
[{{"question": "...", "answer": "..."}}, ...]"""


def build_prompt(request: GenerationRequest) -> str:
    if request.count <= 0:
        raise GenerationError("عدد الأسئلة المطلوب يجب أن يكون أكبر من صفر.")
    if request.count > 50:
        raise GenerationError("الحد الأقصى لكل طلب توليد هو 50 سؤالًا (لتفادي إغراق طابور المراجعة).")
    return PROMPT_TEMPLATE.format(count=request.count, qtype=request.question_type, lesson=request.lesson_name)


def _parse_ai_json(raw_text: str) -> List[dict]:
    """يحلل رد الـAI بأمان. أي فشل في التحليل يُرفع كخطأ واضح بدل اختراع نتيجة فارغة صامتة."""
    text = raw_text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise GenerationError(f"رد الذكاء الاصطناعي لم يكن JSON صالحًا: {e}") from e
    if not isinstance(parsed, list):
        raise GenerationError("رد الذكاء الاصطناعي لم يكن مصفوفة أسئلة كما هو متوقع.")
    return parsed


def generate_questions(gateway: AIGateway, request: GenerationRequest) -> List[GeneratedQuestion]:
    prompt = build_prompt(request)
    response = gateway.ask(prompt)

    if response.status != "success":
        raise GenerationError(f"فشل التوليد عبر مزودي الذكاء الاصطناعي المتاحين: {response.error}")

    items = _parse_ai_json(response.text)
    results = []
    for item in items:
        question = (item.get("question") or "").strip()
        answer = (item.get("answer") or "").strip()
        if not question:
            continue  # لا نخترع نصًا لعنصر فارغ من الـAI نفسه
        results.append(GeneratedQuestion(
            question=question, answer=answer, canonical_type=request.question_type,
            ai_provider=response.provider, ai_model=response.model,
        ))

    if not results:
        raise GenerationError("لم يُستخرج أي سؤال صالح من رد الذكاء الاصطناعي.")
    return results
