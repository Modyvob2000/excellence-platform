"""
File Extractors — واجهة موحّدة FileExtractor.extract(path) -> List[ExtractedPage]
لكل نوع ملف (PDF/DOCX/XLSX)، بحيث يتعامل الـImport Pipeline مع أي نوع ملف
بدون معرفة تفاصيله.

⚠️ صادقة بالكامل: PdfExtractor وDocxExtractor وXlsxExtractor تستخدم مكتبات
حقيقية (pypdf / python-docx / openpyxl) عبر استيراد محمي (try/except) — هذه
المكتبات **غير مثبَّتة في بيئة التطوير الحالية** (لا يوجد اتصال إنترنت لتثبيتها)
ولذلك **لم يتم اختبار هذه الفئات الثلاث فعليًا هنا**. عند التثبيت الفعلي
(`pip install -r requirements.txt`) تعمل مباشرة بدون تعديل.

ما تم اختباره فعليًا: MockFileExtractor (تحاكي أي نوع ملف بنص جاهز) وكل
Import Pipeline المبني فوق الواجهة (import_pipeline.py + tests) — أي أن
منطق الأنابيب بالكامل (Batch/Extract/Parse/Classify/Dedup/Review) مُختبر
فعليًا، والجزء غير المختبر محصور تمامًا في "قراءة البايتات الخام من كل
تنسيق ملف" خلف هذه الواجهة الرفيعة.
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class ExtractedPage:
    page_number: Optional[int]
    text: str


class FileExtractor(ABC):
    @abstractmethod
    def extract(self, file_path: str) -> List[ExtractedPage]:
        raise NotImplementedError


class MockFileExtractor(FileExtractor):
    """✅ مُختبرة فعليًا. تُستخدم في اختبارات الـpipeline بدل قراءة ملفات حقيقية."""

    def __init__(self, pages: List[str]):
        self._pages = pages

    def extract(self, file_path: str) -> List[ExtractedPage]:
        return [ExtractedPage(page_number=i + 1, text=p) for i, p in enumerate(self._pages)]


class PdfExtractor(FileExtractor):
    """⚠️ غير مُختبرة هنا — تحتاج حزمة pypdf (أو OCR لصور/PDF ممسوح ضوئيًا عبر pytesseract)."""

    def extract(self, file_path: str) -> List[ExtractedPage]:
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError(
                "حزمة pypdf غير مثبَّتة. ثبّتها عبر requirements.txt لتفعيل استخراج PDF."
            ) from e
        reader = PdfReader(file_path)
        pages = []
        for i, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            if not text.strip():
                # صفحة بلا نص قابل للاستخراج مباشرة = على الأغلب PDF ممسوح ضوئيًا (صورة)
                text = self._ocr_fallback(page)
            pages.append(ExtractedPage(page_number=i, text=text))
        return pages

    def _ocr_fallback(self, page) -> str:
        try:
            import pytesseract  # noqa: F401
        except ImportError:
            return ""  # لا OCR متاح — تُترك فارغة بدل اختراع نص، وتُسجَّل في الـbatch كخطأ صفحة
        # TODO: تحويل الصفحة لصورة (pdf2image) ثم pytesseract.image_to_string — غير منفَّذ/مختبر هنا.
        return ""


class DocxExtractor(FileExtractor):
    """⚠️ غير مُختبرة هنا — تحتاج حزمة python-docx."""

    def extract(self, file_path: str) -> List[ExtractedPage]:
        try:
            import docx
        except ImportError as e:
            raise RuntimeError(
                "حزمة python-docx غير مثبَّتة. ثبّتها عبر requirements.txt لتفعيل استخراج Word."
            ) from e
        document = docx.Document(file_path)
        full_text = "\n".join(p.text for p in document.paragraphs)
        return [ExtractedPage(page_number=None, text=full_text)]  # Word ليس له "صفحات" منطقية بسهولة


class XlsxExtractor(FileExtractor):
    """⚠️ غير مُختبرة هنا — تحتاج حزمة openpyxl. تُعيد كل صف كسطر CSV-like ليمر عبر csv_parser."""

    def extract(self, file_path: str) -> List[ExtractedPage]:
        try:
            import openpyxl
        except ImportError as e:
            raise RuntimeError(
                "حزمة openpyxl غير مثبَّتة. ثبّتها عبر requirements.txt لتفعيل استيراد Excel."
            ) from e
        wb = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
        sheet = wb.active
        lines = [",".join("" if c.value is None else str(c.value) for c in row) for row in sheet.iter_rows()]
        return [ExtractedPage(page_number=None, text="\n".join(lines))]


def get_extractor(file_type: str) -> FileExtractor:
    file_type = file_type.upper()
    if file_type == "PDF":
        return PdfExtractor()
    if file_type in ("DOC", "DOCX", "WORD"):
        return DocxExtractor()
    if file_type in ("XLSX", "EXCEL"):
        return XlsxExtractor()
    raise ValueError(f"نوع ملف غير مدعوم: {file_type}")
