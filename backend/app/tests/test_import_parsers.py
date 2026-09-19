import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from app.services.import_parsers.bulk_text_parser import parse_bulk_text  # noqa: E402
from app.services.import_parsers.csv_parser import parse_csv  # noqa: E402


class TestBulkTextParser(unittest.TestCase):
    def test_numbered_dash_format(self):
        text = (
            "1- ما هي عاصمة مصر؟\n"
            "الإجابة: القاهرة\n"
            "2- من هو مؤسس مصر الحديثة؟\n"
            "الإجابة: محمد علي\n"
        )
        result = parse_bulk_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].question, "ما هي عاصمة مصر؟")
        self.assertEqual(result[0].answer, "القاهرة")
        self.assertEqual(result[1].answer, "محمد علي")

    def test_dotted_and_parenthesis_numbering(self):
        text = "1. سؤال أول؟\nج: إجابة أولى\n2) سؤال ثاني؟\nج: إجابة ثانية"
        result = parse_bulk_text(text)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[1].question, "سؤال ثاني؟")

    def test_question_without_detected_answer_kept_with_none(self):
        text = "1- سؤال بدون إجابة واضحة في النص"
        result = parse_bulk_text(text)
        self.assertEqual(len(result), 1)
        self.assertIsNone(result[0].answer)  # لا يُخترع جواب غير موجود

    def test_multiline_question_and_answer(self):
        text = (
            "1- سؤال طويل يمتد\n"
            "على أكثر من سطر واحد؟\n"
            "الإجابة: جواب\n"
            "يمتد أيضًا على سطرين"
        )
        result = parse_bulk_text(text)
        self.assertIn("يمتد", result[0].question)
        self.assertIn("جواب", result[0].answer)
        self.assertIn("سطرين", result[0].answer)

    def test_empty_input_returns_empty_list(self):
        self.assertEqual(parse_bulk_text(""), [])
        self.assertEqual(parse_bulk_text("   \n  "), [])

    def test_unnumbered_text_falls_back_to_single_question_not_dropped(self):
        text = "نص بلا أي ترقيم على الإطلاق"
        result = parse_bulk_text(text)
        self.assertEqual(len(result), 1)  # لا يُسقط أي محتوى حتى بدون تنسيق معروف
        self.assertEqual(result[0].question, text)

    def test_raw_text_preserved_verbatim_for_audit(self):
        text = "1- سؤال؟\nالإجابة: جواب"
        result = parse_bulk_text(text)
        self.assertIn("سؤال؟", result[0].raw_text)
        self.assertIn("جواب", result[0].raw_text)


class TestCsvParser(unittest.TestCase):
    def test_arabic_headers_recognized(self):
        csv_text = "السؤال,الإجابة,النوع\nما عاصمة مصر؟,القاهرة,من يكون\n"
        rows = parse_csv(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].question, "ما عاصمة مصر؟")
        self.assertEqual(rows[0].answer, "القاهرة")
        self.assertEqual(rows[0].original_type, "من يكون")

    def test_english_headers_also_recognized(self):
        csv_text = "question,answer,type\nWhat is the capital?,Cairo,who_is\n"
        rows = parse_csv(csv_text)
        self.assertEqual(rows[0].question, "What is the capital?")

    def test_choice_columns_mapped(self):
        csv_text = "السؤال,أ,ب,ج,د\nسؤال اختياري؟,اختيار1,اختيار2,اختيار3,اختيار4\n"
        rows = parse_csv(csv_text)
        self.assertEqual(rows[0].choice_a, "اختيار1")
        self.assertEqual(rows[0].choice_d, "اختيار4")

    def test_missing_question_column_raises_clear_error(self):
        csv_text = "عمود_غريب,عمود_اخر\nقيمة1,قيمة2\n"
        with self.assertRaises(ValueError):
            parse_csv(csv_text)

    def test_rows_with_empty_question_are_skipped_not_invented(self):
        csv_text = "السؤال,الإجابة\n,بدون سؤال\nسؤال حقيقي؟,جواب حقيقي\n"
        rows = parse_csv(csv_text)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].question, "سؤال حقيقي؟")

    def test_row_numbers_tracked_for_source_metadata(self):
        csv_text = "السؤال\nسؤال1\nسؤال2\nسؤال3\n"
        rows = parse_csv(csv_text)
        self.assertEqual([r.row_number for r in rows], [2, 3, 4])

    def test_hundreds_of_rows_handled(self):
        header = "السؤال,الإجابة\n"
        body = "".join(f"سؤال رقم {i}؟,جواب {i}\n" for i in range(500))
        rows = parse_csv(header + body)
        self.assertEqual(len(rows), 500)


if __name__ == "__main__":
    unittest.main(verbosity=2)
