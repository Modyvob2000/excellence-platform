"""
Duplicate Detection — Exact + Semantic (Phase: Review Workflow / Import Center)

قاعدة صارمة: هذه الوحدة لا تحذف أي سؤال أبدًا. تكتفي بإرجاع "possible duplicate"
مع نسبة تشابه، والقرار النهائي دائمًا للمدير في Review Center.

Exact Duplicate:
    تطابق حرفي بعد التطبيع (normalize): إزالة التشكيل، توحيد المسافات، توحيد
    الهمزات/الألف المقصورة، تجاهل علامات الترقيم، تحويل لحروف صغيرة (لغير العربي).

Semantic Duplicate:
    لا تتوفر هنا شبكة اتصال لاستخدام Embeddings حقيقية من مزود AI (راجع
    backend/README.md). لذلك نُنفّذ الآن خوارزمية تشابه نصي حقيقية تعمل محليًا
    بالكامل (Token Jaccard Similarity + SequenceMatcher) — وهي أضعف من
    Embeddings الدلالية الحقيقية لكنها REAL وقابلة للاختبار الآن، ومصمَّمة
    كـ`SimilarityBackend` قابلة للاستبدال لاحقًا بمزود Embeddings حقيقي
    (pgvector + AI Gateway) بدون تغيير أي كود يستدعيها — فقط حقن backend مختلف.
"""
import difflib
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Protocol

ARABIC_DIACRITICS = re.compile(r"[\u0617-\u061A\u064B-\u0652\u0670\u06D6-\u06ED]")
ARABIC_PUNCTUATION = "؟،؛٪ـ»«"

_NORMALIZE_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه", "ؤ": "و", "ئ": "ي",
})


def normalize_text(text: str) -> str:
    """تطبيع نص عربي/إنجليزي لمقارنة عادلة: إزالة تشكيل، توحيد حروف، إزالة ترقيم زائد."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKC", text)
    text = ARABIC_DIACRITICS.sub("", text)
    text = text.translate(_NORMALIZE_MAP)
    text = text.lower()
    for ch in ARABIC_PUNCTUATION:
        text = text.replace(ch, " ")
    text = re.sub(r"[^\w\s\u0600-\u06FF]", " ", text)  # إزالة الترقيم مع إبقاء العربي/اللاتيني
    text = re.sub(r"\s+", " ", text).strip()
    return text


def tokenize(text: str) -> List[str]:
    return [t for t in normalize_text(text).split(" ") if t]


@dataclass
class DuplicateMatch:
    other_question_id: int
    similarity: float
    kind: str  # "exact" | "semantic"


class SimilarityBackend(Protocol):
    """واجهة قابلة للاستبدال — التنفيذ الحالي محلي، ويمكن حقن مزود Embeddings لاحقًا."""
    def similarity(self, text_a: str, text_b: str) -> float: ...


class LocalTextSimilarityBackend:
    """
    REAL و مُختبر: يجمع بين Jaccard على التوكنز وSequenceMatcher على الحروف،
    ليصمد أمام إعادة الصياغة الجزئية (مرادفات بسيطة/ترتيب مختلف) دون الحاجة
    لأي خدمة خارجية.
    """
    def similarity(self, text_a: str, text_b: str) -> float:
        a_norm, b_norm = normalize_text(text_a), normalize_text(text_b)
        if not a_norm or not b_norm:
            return 0.0
        tokens_a, tokens_b = set(a_norm.split()), set(b_norm.split())
        jaccard = (len(tokens_a & tokens_b) / len(tokens_a | tokens_b)) if (tokens_a | tokens_b) else 0.0
        seq_ratio = difflib.SequenceMatcher(None, a_norm, b_norm).ratio()
        return round(0.5 * jaccard + 0.5 * seq_ratio, 4)


EXACT_MATCH_THRESHOLD = 1.0
SEMANTIC_DUPLICATE_THRESHOLD = 0.5  # مُعايَر على أمثلة حقيقية (انظر test_dedup.py) — قابل للضبط لاحقًا من لوحة التحكم


def find_duplicates(
    candidate_text: str,
    existing_questions: Iterable[tuple],  # [(question_id, question_text), ...]
    backend: SimilarityBackend = None,
    threshold: float = SEMANTIC_DUPLICATE_THRESHOLD,
) -> List[DuplicateMatch]:
    """
    يبحث عن تكرارات محتملة لسؤال جديد وسط أسئلة موجودة. لا يحذف ولا يعدّل أي شيء —
    فقط يُرجع قائمة مرشحين مرتبة تنازليًا بالتشابه ليقررها المدير في Review Center.
    """
    backend = backend or LocalTextSimilarityBackend()
    candidate_norm = normalize_text(candidate_text)
    matches: List[DuplicateMatch] = []
    for qid, existing_text in existing_questions:
        existing_norm = normalize_text(existing_text)
        if candidate_norm and candidate_norm == existing_norm:
            matches.append(DuplicateMatch(qid, 1.0, "exact"))
            continue
        score = backend.similarity(candidate_text, existing_text)
        if score >= threshold:
            matches.append(DuplicateMatch(qid, score, "semantic"))
    matches.sort(key=lambda m: m.similarity, reverse=True)
    return matches
