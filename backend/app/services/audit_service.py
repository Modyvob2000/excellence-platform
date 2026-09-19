"""
Audit Log Service — تسجيل العمليات الحساسة والبحث/الفلترة فيها.
منطق خالص عبر AuditStore (Protocol) — قابل للاختبار الكامل.

يُستدعى من نقاط حساسة عبر النظام (اعتماد/رفض سؤال، تغيير دور مستخدم، حذف،
استيراد دفعة) — التسجيل نفسه يحدث فعليًا داخل كل خدمة (review_workflow يسجل
عبر log_action الخاص به، وهنا الواجهة الموحّدة للاستعلام والتقارير الإدارية).
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional, Protocol


@dataclass
class AuditEntry:
    id: Optional[int]
    user_id: Optional[int]
    action: str
    entity: str
    entity_id: Optional[int]
    result: str = "success"          # success | failure
    details: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class AuditStore(Protocol):
    def insert(self, entry: AuditEntry) -> int: ...
    def query(self, user_id=None, action=None, entity=None, entity_id=None,
              result=None, since=None, until=None) -> List[AuditEntry]: ...


SENSITIVE_ACTIONS = {
    "APPROVE", "REJECT", "SOFT_DELETE", "RESTORE", "CHANGE_TYPE", "CHANGE_LESSON",
    "CREATE_USER", "DEACTIVATE_USER", "REACTIVATE_USER", "CHANGE_ROLE", "RESET_PASSWORD",
    "IMPORT_BATCH", "BULK_APPROVE", "BULK_REJECT", "BULK_DELETE",
}


def record(store: AuditStore, user_id: Optional[int], action: str, entity: str,
           entity_id: Optional[int] = None, result: str = "success", **details) -> AuditEntry:
    entry = AuditEntry(id=None, user_id=user_id, action=action, entity=entity,
                        entity_id=entity_id, result=result, details=details)
    entry.id = store.insert(entry)
    return entry


def search_logs(store: AuditStore, user_id=None, action=None, entity=None, entity_id=None,
                 result=None, since=None, until=None) -> List[AuditEntry]:
    return sorted(
        store.query(user_id=user_id, action=action, entity=entity, entity_id=entity_id,
                    result=result, since=since, until=until),
        key=lambda e: e.created_at, reverse=True,
    )


def entity_history(store: AuditStore, entity: str, entity_id: int) -> List[AuditEntry]:
    """كل ما جرى على كيان بعينه (سؤال، مستخدم، امتحان...) بترتيب زمني تصاعدي."""
    return sorted(store.query(entity=entity, entity_id=entity_id), key=lambda e: e.created_at)
