"""
CSV Import Parser (Phase 11) — stdlib فقط (csv module)، بدون أي حزمة خارجية.
XLSX تُقرأ عبر app/services/import_parsers/xlsx_parser.py (يحتاج openpyxl،
موثّق بوضوح أنه غير مُختبر في هذه البيئة)، لكن كليهما يُنتجان نفس البنية
ويمران عبر نفس map_row() هنا — التوحيد يمنع ازدواج منطق الأعمدة.
"""
import csv
import io
from dataclasses import dataclass
from typing import Dict, List, Optional

# أسماء الأعمدة الشائعة بالعربي/الإنجليزي → الحقل الموحّد الداخلي
COLUMN_ALIASES: Dict[str, List[str]] = {
    "question": ["السؤال", "question", "نص السؤال"],
    "answer": ["الإجابة", "الاجابة", "answer", "الجواب"],
    "type": ["النوع", "type", "نوع السؤال"],
    "choice_a": ["أ", "a", "choice_a", "الاختيار الاول"],
    "choice_b": ["ب", "b", "choice_b", "الاختيار الثاني"],
    "choice_c": ["ج", "c", "choice_c", "الاختيار الثالث"],
    "choice_d": ["د", "d", "choice_d", "الاختيار الرابع"],
    "correction": ["التصحيح", "correction"],
    "lesson": ["الدرس", "lesson"],
    "source": ["المصدر", "source"],
}


@dataclass
class ParsedRow:
    question: str
    answer: Optional[str] = None
    original_type: Optional[str] = None
    choice_a: Optional[str] = None
    choice_b: Optional[str] = None
    choice_c: Optional[str] = None
    choice_d: Optional[str] = None
    correction: Optional[str] = None
    lesson_hint: Optional[str] = None
    source: Optional[str] = None
    row_number: int = 0


def _build_header_map(header_row: List[str]) -> Dict[str, str]:
    """يطابق كل عمود فعلي في الملف مع الحقل الموحّد المقابل له (غير حساس لحالة/مسافات الأحرف)."""
    normalized = {h.strip().lower(): h for h in header_row}
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = alias.strip().lower()
            if key in normalized:
                mapping[field] = normalized[key]
                break
    return mapping


def parse_csv(content: str, delimiter: str = ",") -> List[ParsedRow]:
    """
    يقرأ CSV ويُعيد صفوفًا مُهيكَلة. لا يخترع أي عمود غير موجود: أي حقل غير
    مكتشف يبقى None (وليس نصًا مُخمَّنًا)، ليقرر المدير لاحقًا في المراجعة.
    """
    reader = csv.reader(io.StringIO(content), delimiter=delimiter)
    rows = list(reader)
    if not rows:
        return []

    header_map = _build_header_map(rows[0])
    if "question" not in header_map:
        raise ValueError(
            "لم يتم التعرف على عمود السؤال في الملف. الأعمدة المتاحة: "
            f"{rows[0]} — الأعمدة المعروفة: {COLUMN_ALIASES['question']}")

    header_index = {name: idx for idx, name in enumerate(rows[0])}

    def cell(row: List[str], field: str) -> Optional[str]:
        col_name = header_map.get(field)
        if col_name is None:
            return None
        idx = header_index[col_name]
        return row[idx].strip() if idx < len(row) and row[idx].strip() else None

    results = []
    for i, row in enumerate(rows[1:], start=2):  # الصف 1 هو الهيدر
        question = cell(row, "question")
        if not question:
            continue  # صف فارغ من ناحية السؤال — يُتجاهل بدون اختراع محتوى
        results.append(ParsedRow(
            question=question, answer=cell(row, "answer"), original_type=cell(row, "type"),
            choice_a=cell(row, "choice_a"), choice_b=cell(row, "choice_b"),
            choice_c=cell(row, "choice_c"), choice_d=cell(row, "choice_d"),
            correction=cell(row, "correction"), lesson_hint=cell(row, "lesson"),
            source=cell(row, "source"), row_number=i,
        ))
    return results
