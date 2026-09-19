"""
Bulk Text Paste Parser (Phase 12) — يفصل نصًا كبيرًا مُلصَقًا يحوي عشرات/مئات
الأسئلة إلى عناصر منفصلة، بدون أي اعتماد على مكتبات خارجية.

الصيغة المدعومة (الأكثر شيوعًا في أوراق الامتحانات المصرية):
    1- نص السؤال؟
    الإجابة: نص الإجابة
    2- نص السؤال التالي؟
    ...

أو أرقام بأي شكل من: "1-", "1.", "1)", "س1:", "السؤال 1:".
الإجابة تُكتشف من سطر يبدأ بـ"الإجابة" أو "ج:" أو "الجواب".

هذا Parser لا يخترع أي محتوى: أي جزء غامض يُترك كسؤال بلا إجابة مكتشفة
(answer=None) ليذهب لـNEEDS_REVIEW بدل تخمين إجابة غير موجودة في النص.
"""
import re
from dataclasses import dataclass
from typing import List, Optional

_QUESTION_START = re.compile(
    r"^\s*(?:(?:السؤال|س)\s*\d+\s*[:\-.\)]|\d+\s*[-.\)])\s*"
)
_ANSWER_START = re.compile(r"^\s*(?:الإجابة|الاجابة|الجواب|ج)\s*[:\-]\s*(.*)$")


@dataclass
class ParsedQuestion:
    raw_text: str
    question: str
    answer: Optional[str] = None


def parse_bulk_text(text: str) -> List[ParsedQuestion]:
    if not text or not text.strip():
        return []

    lines = [ln for ln in text.splitlines()]
    blocks: List[List[str]] = []
    current: List[str] = []

    for line in lines:
        if _QUESTION_START.match(line):
            if current:
                blocks.append(current)
            current = [_QUESTION_START.sub("", line).strip()]
        elif current:
            current.append(line.strip())
    if current:
        blocks.append(current)

    # لا يوجد أي ترقيم صريح في النص كله؟ عاملها كسؤال واحد كامل (fallback آمن، لا يُسقط شيئًا)
    if not blocks:
        blocks = [[ln.strip() for ln in lines if ln.strip()]]

    results: List[ParsedQuestion] = []
    for block in blocks:
        if not block or not block[0]:
            continue
        question_lines, answer_lines = [block[0]], []
        found_answer = False
        for line in block[1:]:
            m = _ANSWER_START.match(line)
            if m:
                found_answer = True
                if m.group(1):
                    answer_lines.append(m.group(1))
                continue
            (answer_lines if found_answer else question_lines).append(line)

        question_text = " ".join(x for x in question_lines if x).strip()
        answer_text = " ".join(x for x in answer_lines if x).strip() or None
        if question_text:
            results.append(ParsedQuestion(
                raw_text="\n".join(block), question=question_text, answer=answer_text))
    return results
