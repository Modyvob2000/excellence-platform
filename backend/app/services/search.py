"""
Smart Search (Phase 9 / 24) — بحث داخل الدروس/الأسئلة/بنك الأسئلة.

يدعم الآن:
- Keyword Search: تطابق مباشر بعد التطبيع.
- "شبه-دلالي" (quasi-semantic): نفس LocalTextSimilarityBackend المستخدم في
  dedup.py (Jaccard + SequenceMatcher) — REAL ومحلي بالكامل بدون أي embeddings
  حقيقية (تلك تحتاج مزود AI + pgvector غير متاحين هنا، راجع backend/README.md).

هذا مصمَّم كطبقة أولى صادقة (Baseline)، قابلة للاستبدال لاحقًا بـEmbeddings
حقيقية عبر AI Gateway + pgvector بدون تغيير الواجهة العامة (rank_by_relevance).

⚠️ حد صادق معروف: هذا الـbackend المحلي (تشابه كلمات/حروف) أضعف بكثير من
Embeddings دلالية حقيقية عند عبارات عربية قصيرة بلا كلمات مشتركة أو جذور
متقاربة — الفارق بين "مرتبط" و"غير مرتبط" قد يكون ضيقًا (اختُبر بأمثلة حقيقية
في test_search.py، والعتبة 0.25 معايَرة عليها لا افتراضية). يبقى Keyword
Search دقيقًا تمامًا؛ الجزء "شبه الدلالي" تحسين إضافي وليس بديلاً كامل الدقة.
"""
from typing import List, Tuple

from app.services.dedup import LocalTextSimilarityBackend, normalize_text

_backend = LocalTextSimilarityBackend()


def rank_by_relevance(query: str, candidates: List[Tuple[int, str]], limit: int = 20) -> List[Tuple[int, float]]:
    """
    يُرجع [(id, score)] مرتبة تنازليًا. يجمع بين:
    - تطابق كلمة مفتاحية مباشرة (تعزيز الدرجة +0.3 لو الاستعلام يظهر حرفيًا).
    - تشابه نصي عام (يلتقط استعلامات بمعنى قريب حتى بدون تطابق حرفي للكلمات،
      كما في مثال المستخدم: "أسئلة أسباب قيام الحضارات القديمة").
    """
    if not query or not query.strip():
        return []

    query_norm = normalize_text(query)
    scored = []
    for item_id, text in candidates:
        text_norm = normalize_text(text)
        if not text_norm:
            continue
        score = _backend.similarity(query, text)
        if query_norm in text_norm:
            score = min(1.0, score + 0.3)
        if score > 0.25:
            scored.append((item_id, round(score, 4)))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored[:limit]
