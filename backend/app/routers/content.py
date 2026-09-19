"""Content API — grades/subjects/units/lessons. ⚠️ غير مُشغَّل عبر HTTP هنا (FastAPI غير مثبَّتة)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Grade, Lesson, Subject, Unit
from app.security import require_roles

router = APIRouter(prefix="/content", tags=["content"])


class NodeIn(BaseModel):
    name: str
    parent_id: Optional[int] = None
    order_index: int = 0


class NodeOut(BaseModel):
    id: int
    name: str
    is_hidden: bool

    class Config:
        from_attributes = True


def _crud_for(model, parent_field: Optional[str]):
    def list_items(db: Session, parent_id: Optional[int] = None, include_hidden: bool = False):
        q = db.query(model)
        if parent_field and parent_id is not None:
            q = q.filter(getattr(model, parent_field) == parent_id)
        if not include_hidden:
            q = q.filter(model.is_hidden.is_(False))
        return q.order_by(model.id).all()
    return list_items


@router.get("/grades", response_model=list[NodeOut])
def list_grades(stage_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Grade).filter(Grade.is_hidden.is_(False))
    if stage_id:
        q = q.filter(Grade.stage_id == stage_id)
    return q.order_by(Grade.order_index).all()


@router.post("/grades", response_model=NodeOut)
def create_grade(payload: NodeIn, db: Session = Depends(get_db),
                  user=Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    grade = Grade(name=payload.name, stage_id=payload.parent_id, order_index=payload.order_index)
    db.add(grade)
    db.commit()
    db.refresh(grade)
    return grade


@router.patch("/grades/{grade_id}/hide")
def hide_grade(grade_id: int, db: Session = Depends(get_db),
                user=Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    grade = db.get(Grade, grade_id)
    if not grade:
        raise HTTPException(404, "الصف غير موجود.")
    grade.is_hidden = True
    db.commit()
    return {"status": "hidden"}


@router.patch("/grades/{grade_id}/restore")
def restore_grade(grade_id: int, db: Session = Depends(get_db),
                   user=Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    grade = db.get(Grade, grade_id)
    if not grade:
        raise HTTPException(404, "الصف غير موجود.")
    grade.is_hidden = False
    db.commit()
    return {"status": "restored"}


@router.get("/subjects", response_model=list[NodeOut])
def list_subjects(grade_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Subject).filter(Subject.is_hidden.is_(False))
    if grade_id:
        q = q.filter(Subject.grade_id == grade_id)
    return q.all()


@router.get("/units", response_model=list[NodeOut])
def list_units(subject_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Unit).filter(Unit.is_hidden.is_(False), Unit.is_deleted.is_(False))
    if subject_id:
        q = q.filter(Unit.subject_id == subject_id)
    return q.order_by(Unit.order_index).all()


@router.get("/lessons", response_model=list[NodeOut])
def list_lessons(unit_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Lesson).filter(Lesson.is_hidden.is_(False), Lesson.is_deleted.is_(False))
    if unit_id:
        q = q.filter(Lesson.unit_id == unit_id)
    return q.order_by(Lesson.order_index).all()


@router.post("/units", response_model=NodeOut)
def create_unit(payload: NodeIn, db: Session = Depends(get_db),
                 user=Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    unit = Unit(name=payload.name, subject_id=payload.parent_id, order_index=payload.order_index)
    db.add(unit)
    db.commit()
    db.refresh(unit)
    return unit


@router.delete("/units/{unit_id}")
def soft_delete_unit(unit_id: int, db: Session = Depends(get_db),
                      user=Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    """حذف منطقي فقط (is_deleted=True) — أبدًا DELETE حقيقي من قاعدة البيانات."""
    from datetime import datetime, timezone
    unit = db.get(Unit, unit_id)
    if not unit:
        raise HTTPException(404, "الوحدة غير موجودة.")
    unit.is_deleted = True
    unit.deleted_at = datetime.now(timezone.utc)
    db.commit()
    return {"status": "soft_deleted"}


@router.post("/lessons", response_model=NodeOut)
def create_lesson(payload: NodeIn, db: Session = Depends(get_db),
                   user=Depends(require_roles("TEACHER", "ADMIN", "SUPER_ADMIN"))):
    lesson = Lesson(name=payload.name, unit_id=payload.parent_id, order_index=payload.order_index)
    db.add(lesson)
    db.commit()
    db.refresh(lesson)
    return lesson
