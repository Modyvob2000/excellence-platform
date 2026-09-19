"""
AI Generation API — مسار منفصل تمامًا عن /import (استخراج من مصدر).
⚠️ غير مُشغَّل عبر HTTP هنا. الاستدعاءات الشبكية الفعلية لمزودي AI غير منفَّذة
بعد (TODO في app/ai_gateway/__init__.py) — هذا المسار سيرفع GenerationError
وقت التشغيل الحقيقي حتى تُستكمل تلك التكاملات، ولن يُظهر أبدًا نجاحًا وهميًا.
"""
import os

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.ai_gateway import AIGateway, ClaudeProvider, GeminiProvider, OpenAIProvider
from app.database import get_db
from app.models import Question
from app.security import CurrentUser, require_roles
from app.services.ai_question_generator import GenerationError, GenerationRequest, generate_questions

router = APIRouter(prefix="/ai", tags=["ai"])


class GenerateIn(BaseModel):
    lesson_id: int
    lesson_name: str
    count: int
    question_type: str


class GeneratedOut(BaseModel):
    question: str
    answer: str
    status: str
    source_type: str
    ai_provider: str | None


def build_gateway() -> AIGateway:
    """يبني AIGateway من متغيرات البيئة فقط — لا مفاتيح مكتوبة في الكود أو مُرسَلة لأي عميل."""
    providers = {}
    if os.environ.get("GEMINI_API_KEY"):
        providers["gemini"] = GeminiProvider(os.environ["GEMINI_API_KEY"])
    if os.environ.get("OPENAI_API_KEY"):
        providers["openai"] = OpenAIProvider(os.environ["OPENAI_API_KEY"])
    if os.environ.get("ANTHROPIC_API_KEY"):
        providers["claude"] = ClaudeProvider(os.environ["ANTHROPIC_API_KEY"])
    if not providers:
        raise HTTPException(503, "لا يوجد مزود ذكاء اصطناعي مُهيَّأ على السيرفر (تحقق من متغيرات البيئة).")
    primary = os.environ.get("AI_PRIMARY_PROVIDER", next(iter(providers)))
    fallback = os.environ.get("AI_FALLBACK_PROVIDER")
    return AIGateway(providers=providers, primary=primary, fallback=fallback)


@router.post("/generate-questions", response_model=list[GeneratedOut])
def generate(payload: GenerateIn, db: Session = Depends(get_db),
             user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    gateway = build_gateway()
    request = GenerationRequest(lesson_id=payload.lesson_id, lesson_name=payload.lesson_name,
                                 count=payload.count, question_type=payload.question_type)
    try:
        generated = generate_questions(gateway, request)
    except GenerationError as e:
        raise HTTPException(502, str(e)) from e

    saved = []
    for g in generated:
        row = Question(
            question=g.question, answer=g.answer, lesson_id=payload.lesson_id,
            original_question_type=g.canonical_type, status=g.status, approved=False,
            source_type=g.source_type, ai_provider=g.ai_provider, ai_model=g.ai_model,
            created_by=user.id,
        )
        db.add(row)
        saved.append(g)
    db.commit()

    return [GeneratedOut(question=g.question, answer=g.answer, status=g.status,
                          source_type=g.source_type, ai_provider=g.ai_provider) for g in saved]
