"""
Route Ordering Safety Test — يمنع تكرار الـbug المكتشف في routers/questions.py:
مسار حرفي مثل "/bulk/approve" كان يُخطَف بمسار "/{question_id}/approve"
المُسجَّل قبله، لأن FastAPI/Starlette يطابق المسارات بترتيب التسجيل، و
"{question_id}" (بلا محدّد نوع صريح في نص المسار) يُطابق أي segment نصي بما
فيه الكلمة الحرفية "bulk".

هذا الاختبار **لا يحتاج FastAPI مثبَّتة**: يقرأ ملفات الراوترز عبر وحدة
`ast` القياسية (Python stdlib) لاستخراج كل (method, path, function_name)
بترتيب التسجيل الفعلي في الملف، ثم يُحاكي منطق مطابقة Starlette (كل
`{name}` يطابق segment واحد فقط، أول تطابق هيكلي يفوز) للتحقق أن مسارات
اختبارية محددة تصل فعليًا للدالة المقصودة — تمامًا نفس الحافز الذي كشف
الـbug الأصلي.

✅ يعمل ويُشغَّل فعليًا بدون أي حزمة خارجية.
"""
import ast
import os
import re
import unittest

ROUTERS_DIR = os.path.join(os.path.dirname(__file__), "..", "routers")

HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def extract_routes_in_order(file_path: str, prefix: str = ""):
    """يُرجع [(method, full_path, function_name), ...] بترتيب التسجيل الفعلي في الملف."""
    with open(file_path, encoding="utf-8") as f:
        tree = ast.parse(f.read(), filename=file_path)

    routes = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        for deco in node.decorator_list:
            if not isinstance(deco, ast.Call):
                continue
            attr = deco.func
            if not (isinstance(attr, ast.Attribute) and attr.attr in HTTP_METHODS):
                continue
            if not (isinstance(attr.value, ast.Name) and attr.value.id == "router"):
                continue
            if not deco.args or not isinstance(deco.args[0], ast.Constant):
                continue
            path = deco.args[0].value
            routes.append((attr.attr.upper(), prefix.rstrip("/") + path, node.name))
    return routes


def compile_path_regex(path_template: str) -> re.Pattern:
    """يحاكي Starlette: {name} -> segment واحد بلا شرطة مائلة (نفس السلوك الافتراضي)."""
    pattern = re.sub(r"\{[^}/]+\}", r"[^/]+", path_template)
    return re.compile(f"^{pattern}$")


def resolve(routes_in_order, method: str, request_path: str):
    """يُرجع اسم الدالة لأول مسار مُسجَّل يُطابق هيكليًا — يُحاكي سلوك Starlette الفعلي."""
    for m, template, func_name in routes_in_order:
        if m != method:
            continue
        if compile_path_regex(template).match(request_path):
            return func_name
    return None


class TestQuestionsRouterOrdering(unittest.TestCase):
    """الاختبار الذي كان سيكتشف الـbug الأصلي فورًا لو وُجد وقتها."""

    @classmethod
    def setUpClass(cls):
        cls.routes = extract_routes_in_order(
            os.path.join(ROUTERS_DIR, "questions.py"), prefix="/questions")

    def test_bulk_approve_resolves_to_bulk_handler_not_single_question(self):
        resolved = resolve(self.routes, "POST", "/questions/bulk/approve")
        self.assertEqual(resolved, "bulk_approve",
                          "bulk/approve يجب أن يصل لمعالج bulk_approve، وليس approve(question_id='bulk').")

    def test_bulk_reject_resolves_to_bulk_handler_not_single_question(self):
        resolved = resolve(self.routes, "POST", "/questions/bulk/reject")
        self.assertEqual(resolved, "bulk_reject")

    def test_bulk_delete_resolves_correctly(self):
        resolved = resolve(self.routes, "POST", "/questions/bulk/delete")
        self.assertEqual(resolved, "bulk_delete")

    def test_bulk_change_type_resolves_correctly(self):
        resolved = resolve(self.routes, "POST", "/questions/bulk/change_type")
        self.assertEqual(resolved, "bulk_change_type")

    def test_bulk_change_lesson_resolves_correctly(self):
        resolved = resolve(self.routes, "POST", "/questions/bulk/change_lesson")
        self.assertEqual(resolved, "bulk_change_lesson")

    def test_search_resolves_to_search_handler_not_single_question(self):
        resolved = resolve(self.routes, "GET", "/questions/search/")
        self.assertEqual(resolved, "search",
                          "search/ يجب أن يصل لمعالج البحث، وليس get_one(question_id='search').")

    def test_individual_question_routes_still_work_normally(self):
        self.assertEqual(resolve(self.routes, "GET", "/questions/42"), "get_one")
        self.assertEqual(resolve(self.routes, "POST", "/questions/42/approve"), "approve")
        self.assertEqual(resolve(self.routes, "POST", "/questions/42/reject"), "reject")
        self.assertEqual(resolve(self.routes, "PATCH", "/questions/42"), "update")
        self.assertEqual(resolve(self.routes, "DELETE", "/questions/42"), "delete")

    def test_no_literal_route_is_ever_shadowed_by_an_earlier_parameterized_route(self):
        """
        فحص عام (وليس فقط للحالات المعروفة أعلاه): لكل مسار حرفي بالكامل (بدون
        أي {param})، تأكد أن أول تطابق هيكلي في القائمة هو هو نفسه، لا مسار
        سبقه يحتوي {param} بنفس البنية.
        """
        literal_routes = [(m, p, f) for m, p, f in self.routes if "{" not in p]
        for method, path, func_name in literal_routes:
            resolved = resolve(self.routes, method, path)
            self.assertEqual(
                resolved, func_name,
                f"المسار الحرفي {method} {path} (المفترض أن يصل إلى {func_name}) "
                f"يُخطَف فعليًا إلى {resolved} بسبب ترتيب تسجيل خاطئ.")


class TestAllRoutersOrdering(unittest.TestCase):
    """نفس الفحص العام، لكن مُطبَّق تلقائيًا على كل راوترز المشروع، وليس questions.py فقط."""

    ROUTER_PREFIXES = {
        "auth.py": "/auth", "content.py": "/content", "questions.py": "/questions",
        "exams.py": "/exams", "results.py": "/results", "import_.py": "/import",
        "review.py": "/review", "users.py": "/users", "audit.py": "/audit",
        "search.py": "/search", "ai_generation.py": "/ai",
    }

    def test_no_router_has_a_shadowed_literal_route(self):
        problems = []
        for filename, prefix in self.ROUTER_PREFIXES.items():
            file_path = os.path.join(ROUTERS_DIR, filename)
            if not os.path.exists(file_path):
                continue
            routes = extract_routes_in_order(file_path, prefix=prefix)
            literal_routes = [(m, p, f) for m, p, f in routes if "{" not in p]
            for method, path, func_name in literal_routes:
                resolved = resolve(routes, method, path)
                if resolved != func_name:
                    problems.append(f"{filename}: {method} {path} -> توقع {func_name}، وصل فعليًا {resolved}")
        self.assertEqual(problems, [], "مسارات حرفية مخطوفة بمسارات مُعامَلة سابقة:\n" + "\n".join(problems))


if __name__ == "__main__":
    unittest.main(verbosity=2)
