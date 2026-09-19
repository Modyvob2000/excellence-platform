"""
منصة التميز التعليمية — Backend API (FastAPI)
⚠️ لم يتم تشغيل هذا التطبيق فعليًا في بيئة التطوير الحالية لعدم توفر حزمة
FastAPI (لا يوجد اتصال إنترنت لتثبيتها). الكود سليم صياغيًا (py_compile)
ويعتمد على وحدات مُختبرة فعليًا (auth_core, ai_gateway). راجع README.md.
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.database import init_db
from app.routers import ai_generation, audit, auth, content, exams, import_, questions, results, review, search, users

app = FastAPI(
    title="منصة التميز التعليمية API",
    version="0.1.0",
    description="Backend عام لمنصة تعليمية متعددة المراحل والمواد.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # TODO: تقييدها لنطاقات لوحة التحكم/التطبيق فعليًا قبل الإنتاج
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(content.router)
app.include_router(questions.router)
app.include_router(exams.router)
app.include_router(results.router)
app.include_router(import_.router)
app.include_router(review.router)
app.include_router(users.router)
app.include_router(audit.router)
app.include_router(ai_generation.router)
app.include_router(search.router)


@app.on_event("startup")
def on_startup():
    init_db()


@app.get("/health")
def health():
    return {"status": "ok", "service": "excellence-platform-backend"}
