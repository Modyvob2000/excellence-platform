"""
Import API — مركز الاستيراد الذكي. يستدعي:
  file_extractors (⚠️ PDF/DOCX/XLSX غير مُختبرة هنا لعدم توفر المكتبات)
  bulk_text_parser / csv_parser (✅ مُختبرة بالكامل)
  import_pipeline.run_batch (✅ مُختبر بالكامل، بما فيه اختبار التكامل الشامل)

⚠️ طبقة FastAPI هذه نفسها غير مُشغَّلة عبر HTTP هنا.
"""
import uuid
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ImportBatch, ImportedQuestion, ImportFile, Question
from app.security import CurrentUser, require_roles
from app.services.import_parsers.bulk_text_parser import parse_bulk_text
from app.services.import_parsers.csv_parser import parse_csv
from app.services.import_parsers.file_extractors import get_extractor
from app.services.import_pipeline import run_batch

router = APIRouter(prefix="/import", tags=["import"])


class BulkTextIn(BaseModel):
    text: str
    lesson_id: int


class BatchOut(BaseModel):
    batch_number: str
    status: str
    total_questions: int
    needs_review_count: int
    duplicate_count: int
    needs_classification_count: int


def _existing_question_pairs(db: Session):
    rows = db.query(Question.id, Question.question).filter(Question.is_deleted.is_(False)).all()
    return [(r.id, r.question) for r in rows]


def _persist_batch_results(db: Session, batch_number: str, file_id: Optional[int],
                            decisions, summary, created_by: int) -> ImportBatch:
    batch = ImportBatch(
        batch_number=batch_number, import_file_id=file_id, status="NEEDS_REVIEW",
        total_questions=summary.total, needs_review_count=summary.needs_review,
        duplicate_count=summary.duplicate, needs_classification_count=summary.needs_classification,
        created_by=created_by,
    )
    db.add(batch)
    db.commit()
    db.refresh(batch)

    for d in decisions:
        # القرار النهائي (اعتماد) دائمًا بشري لاحقًا عبر /questions/{id}/approve — لا اعتماد هنا أبدًا
        q = Question(
            question=d.question, answer=d.answer, status=d.status,
            original_question_type=d.original_question_type or d.classification.canonical_type,
            source_type="TEXT", approved=False, import_batch_id=batch.id,
            lesson_id=None,  # يُربط لاحقًا يدويًا في المراجعة إن لم يكن معروفًا وقت الاستيراد
        )
        db.add(q)
        db.commit()
        db.refresh(q)
        db.add(ImportedQuestion(
            import_batch_id=batch.id, question_id=q.id, raw_text=d.raw_text,
            page_number=d.page_number, status=d.status,
            duplicate_of_question_id=d.duplicates[0].other_question_id if d.duplicates else None,
            similarity_score=d.duplicates[0].similarity if d.duplicates else None,
        ))
    db.commit()
    batch.status = "COMPLETED"
    db.commit()
    db.refresh(batch)
    return batch


@router.post("/bulk-text", response_model=BatchOut)
def import_bulk_text(payload: BulkTextIn, db: Session = Depends(get_db),
                      user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    parsed = parse_bulk_text(payload.text)
    items = [{"raw_text": p.raw_text, "question": p.question, "answer": p.answer} for p in parsed]
    decisions, summary = run_batch(items, existing_questions=_existing_question_pairs(db))
    batch = _persist_batch_results(
        db, batch_number=f"Batch #{uuid.uuid4().hex[:8]}", file_id=None, decisions=decisions,
        summary=summary, created_by=user.id)
    return BatchOut(batch_number=batch.batch_number, status=batch.status,
                     total_questions=batch.total_questions, needs_review_count=batch.needs_review_count,
                     duplicate_count=batch.duplicate_count,
                     needs_classification_count=batch.needs_classification_count)


@router.post("/csv", response_model=BatchOut)
def import_csv(file: UploadFile = File(...), db: Session = Depends(get_db),
                user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    content = file.file.read().decode("utf-8-sig")
    try:
        rows = parse_csv(content)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e

    items = [{"raw_text": f"صف رقم {r.row_number}", "question": r.question, "answer": r.answer,
              "original_type": r.original_type} for r in rows]
    decisions, summary = run_batch(items, existing_questions=_existing_question_pairs(db))

    file_row = ImportFile(file_name=file.filename, file_type="CSV",
                           storage_path=f"uploads/{uuid.uuid4().hex}_{file.filename}", uploaded_by=user.id)
    db.add(file_row)
    db.commit()
    db.refresh(file_row)

    batch = _persist_batch_results(
        db, batch_number=f"Batch #{uuid.uuid4().hex[:8]}", file_id=file_row.id, decisions=decisions,
        summary=summary, created_by=user.id)
    return BatchOut(batch_number=batch.batch_number, status=batch.status,
                     total_questions=batch.total_questions, needs_review_count=batch.needs_review_count,
                     duplicate_count=batch.duplicate_count,
                     needs_classification_count=batch.needs_classification_count)


@router.post("/file", response_model=BatchOut)
def import_file(file_type: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                 user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    """
    PDF / WORD / EXCEL: يحفظ الملف مؤقتًا ثم يمرّ عبر FileExtractor المناسب.
    ⚠️ لعدم توفر pypdf/python-docx/openpyxl في بيئة التطوير الحالية، هذا المسار
    سيرفع خطأ 501 وقت التشغيل الفعلي حتى تُثبَّت الحزم (راجع requirements.txt)
    — ولا يُعرَض هنا أي نجاح وهمي.
    """
    import tempfile
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(file.file.read())
        tmp_path = tmp.name

    try:
        extractor = get_extractor(file_type)
        pages = extractor.extract(tmp_path)
    except RuntimeError as e:
        raise HTTPException(501, str(e)) from e

    all_text = "\n".join(p.text for p in pages)
    parsed = parse_bulk_text(all_text)
    items = [{"raw_text": p.raw_text, "question": p.question, "answer": p.answer} for p in parsed]
    decisions, summary = run_batch(items, existing_questions=_existing_question_pairs(db))

    file_row = ImportFile(file_name=file.filename, file_type=file_type.upper(),
                           storage_path=tmp_path, uploaded_by=user.id)
    db.add(file_row)
    db.commit()
    db.refresh(file_row)

    batch = _persist_batch_results(
        db, batch_number=f"Batch #{uuid.uuid4().hex[:8]}", file_id=file_row.id, decisions=decisions,
        summary=summary, created_by=user.id)
    return BatchOut(batch_number=batch.batch_number, status=batch.status,
                     total_questions=batch.total_questions, needs_review_count=batch.needs_review_count,
                     duplicate_count=batch.duplicate_count,
                     needs_classification_count=batch.needs_classification_count)


@router.get("/batches", response_model=List[BatchOut])
def list_batches(db: Session = Depends(get_db),
                  user: CurrentUser = Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    """سجل عمليات الاستيراد (Import History)."""
    rows = db.query(ImportBatch).order_by(ImportBatch.created_at.desc()).all()
    return [BatchOut(batch_number=b.batch_number, status=b.status, total_questions=b.total_questions,
                      needs_review_count=b.needs_review_count, duplicate_count=b.duplicate_count,
                      needs_classification_count=b.needs_classification_count) for b in rows]
