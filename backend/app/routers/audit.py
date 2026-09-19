"""Audit Logs API — البحث والفلترة في سجل العمليات الحساسة. ⚠️ غير مُشغَّل عبر HTTP هنا."""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import AuditLog
from app.security import CurrentUser, require_roles
from app.services.audit_service import AuditEntry, search_logs

router = APIRouter(prefix="/audit", tags=["audit"])


class AuditEntryOut(BaseModel):
    id: int
    user_id: Optional[int]
    action: str
    entity: str
    entity_id: Optional[int]
    result: str
    created_at: datetime


class SqlAlchemyAuditStore:
    def __init__(self, db: Session):
        self.db = db

    def insert(self, entry: AuditEntry) -> int:
        row = AuditLog(user_id=entry.user_id, action=entry.action, entity=entry.entity,
                        entity_id=entry.entity_id, details_json=entry.details)
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        return row.id

    def query(self, user_id=None, action=None, entity=None, entity_id=None,
              result=None, since=None, until=None) -> List[AuditEntry]:
        q = self.db.query(AuditLog)
        if user_id is not None:
            q = q.filter(AuditLog.user_id == user_id)
        if action is not None:
            q = q.filter(AuditLog.action == action)
        if entity is not None:
            q = q.filter(AuditLog.entity == entity)
        if entity_id is not None:
            q = q.filter(AuditLog.entity_id == entity_id)
        if since is not None:
            q = q.filter(AuditLog.created_at >= since)
        if until is not None:
            q = q.filter(AuditLog.created_at <= until)
        return [
            AuditEntry(id=r.id, user_id=r.user_id, action=r.action, entity=r.entity,
                       entity_id=r.entity_id, result="success", details=r.details_json or {},
                       created_at=r.created_at)
            for r in q.all()
        ]


def get_store(db: Session = Depends(get_db)) -> SqlAlchemyAuditStore:
    return SqlAlchemyAuditStore(db)


@router.get("", response_model=List[AuditEntryOut])
def list_logs(user_id: Optional[int] = None, action: Optional[str] = None,
              entity: Optional[str] = None, entity_id: Optional[int] = None,
              since: Optional[datetime] = None, until: Optional[datetime] = None,
              store: SqlAlchemyAuditStore = Depends(get_store),
              current_user: CurrentUser = Depends(require_roles("ADMIN", "SUPER_ADMIN"))):
    results = search_logs(store, user_id=user_id, action=action, entity=entity,
                           entity_id=entity_id, since=since, until=until)
    return [AuditEntryOut(id=e.id, user_id=e.user_id, action=e.action, entity=e.entity,
                           entity_id=e.entity_id, result=e.result, created_at=e.created_at)
            for e in results]
