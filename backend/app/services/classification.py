"""
Question Classification — توحيد أنواع الأسئلة مع الاحتفاظ بالنوع الأصلي.

يُستخدم في:
1. الترحيل (تم فعلًا في migration/migrate.py بخريطة يدوية للبيانات القديمة).
2. الاستيراد الجديد (PDF/Word/Excel/لصق نص): النص هنا غير موسوم بنوع صريح
   غالبًا، فنحتاج تصنيفًا تلقائيًا بثقة (confidence). إذا كانت الثقة منخفضة
   → NEEDS_CLASSIFICATION ولا يُعتمد السؤال حتى يحدد المدير النوع يدويًا.

هذا تصنيف قائم على قواعد نصية (Rule-based) وليس نموذج تعلّم آلي — REAL ومُختبر
محليًا بالكامل بدون أي اتصال خارجي. قابل للاستبدال لاحقًا بنموذج AI عبر
نفس الواجهة (classify()) دون تغيير المستدعي.
"""
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

CANONICAL_TYPES = [
    "TRUE_FALSE", "MCQ", "COMPLETE", "TERM", "WHO_IS", "WHY",
    "WHAT_HAPPENS", "MAP", "RELATION", "SHORT_ANSWER", "ESSAY", "OTHER",
]

NEEDS_CLASSIFICATION_THRESHOLD = 0.6


@dataclass
class ClassificationResult:
    canonical_type: str
    confidence: float
    original_question_type: Optional[str] = None
    needs_classification: bool = False

    def __post_init__(self):
        self.needs_classification = self.confidence < NEEDS_CLASSIFICATION_THRESHOLD


# قواعد أنماط نصية: (نمط regex، النوع، وزن الثقة عند التطابق)
_RULES: List[Tuple[re.Pattern, str, float]] = [
    (re.compile(r"\bصح\b.*\bخط[أا]\b|\bصح\b.*\bغلط\b"), "TRUE_FALSE", 0.95),
    (re.compile(r"ضع\s*علامة.*صح|صواب\s*أم\s*خط[أا]"), "TRUE_FALSE", 0.9),
    (re.compile(r"اختر|اختياري|من متعدد|أ[\)\.]\s*.+ب[\)\.]"), "MCQ", 0.85),
    (re.compile(r"^أكمل|أكمل ال|املأ الفراغ|complete the"), "COMPLETE", 0.9),
    (re.compile(r"عرّف|عرف مصطلح|المقصود ب|ما المقصود"), "TERM", 0.85),
    (re.compile(r"^من هو|^من هي|من يكون"), "WHO_IS", 0.9),
    (re.compile(r"^بم تفسر|^وضح سبب|^علل|^لماذا"), "WHY", 0.85),
    (re.compile(r"ماذا يحدث إذا|ماذا سيحدث لو|توقع ما يحدث"), "WHAT_HAPPENS", 0.85),
    (re.compile(r"على الخريطة|حدد على الخريطة|أشر على الخريطة"), "MAP", 0.9),
    (re.compile(r"العلاقة بين|قارن بين|ما وجه الشبه"), "RELATION", 0.8),
    (re.compile(r"^اذكر باختصار|في سطرين|في جملة واحدة"), "SHORT_ANSWER", 0.7),
    (re.compile(r"اكتب مقالًا|بحث مقالي|في مقال متكامل|ناقش بالتفصيل"), "ESSAY", 0.8),
]

# خريطة توافق مع القيم النصية العربية القديمة (تُستخدم أيضًا كمرجع إضافي)
LEGACY_TEXT_MAP = {
    "اختيار من متعدد": "MCQ", "اختياري": "MCQ", "اختر": "MCQ",
    "صح وخطأ": "TRUE_FALSE", "صح وغلط": "TRUE_FALSE", "صح أو خطأ": "TRUE_FALSE",
    "أكمل": "COMPLETE", "مصطلح": "TERM", "من يكون": "WHO_IS",
    "خريطة": "MAP", "العلاقة بين": "RELATION", "ماذا يحدث إذا": "WHAT_HAPPENS",
    "بم تفسر": "WHY", "أسئلة قصيرة": "SHORT_ANSWER", "أسئلة مقالية": "ESSAY",
}


def classify(question_text: str, hinted_original_type: Optional[str] = None) -> ClassificationResult:
    """
    يصنّف سؤالًا واحدًا. إذا كان hinted_original_type معروفًا حرفيًا في
    LEGACY_TEXT_MAP (مثلاً قادم من عمود صريح في ملف Excel)، تُعطى له الأولوية
    بثقة كاملة لأنه تصنيف بشري صريح وليس تخمينًا.
    """
    if hinted_original_type:
        mapped = LEGACY_TEXT_MAP.get(hinted_original_type.strip())
        if mapped:
            return ClassificationResult(mapped, 1.0, hinted_original_type)

    text = question_text or ""
    for pattern, canonical, weight in _RULES:
        if pattern.search(text):
            return ClassificationResult(canonical, weight, hinted_original_type)

    # لا تطابق أي قاعدة: OTHER بثقة منخفضة عمدًا → يذهب لـNEEDS_CLASSIFICATION
    return ClassificationResult("OTHER", 0.3, hinted_original_type)
