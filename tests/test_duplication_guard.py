"""这个仓库只允许出现自己的业务逻辑，框架已经有的东西不再复制一份。"""

from __future__ import annotations

import unittest
from pathlib import Path

import oldman
from oldman.testing.duplication import (
    duplicate_functions,
    forbidden_attributes,
    forbidden_imports,
    identical_files,
)

ROOT = Path(__file__).resolve().parents[1]
FRAMEWORK = Path(oldman.__file__).resolve().parent
PROJECT_SOURCES = (ROOT / "apps", ROOT / "config", ROOT / "services", ROOT / "scripts")

# 还没有搬走的重复，逐条写明原因；修掉一条就从这里删掉一条。
ALLOWED_FRAMEWORK_DUPLICATES: frozenset[str] = frozenset()


class ProjectDoesNotCopyTheFrameworkTest(unittest.TestCase):
    def test_no_project_function_repeats_a_framework_implementation(self) -> None:
        unexpected = []
        for source in PROJECT_SOURCES:
            if not source.exists():
                continue
            for item in duplicate_functions(source, FRAMEWORK, min_lines=6):
                if item.name in ALLOWED_FRAMEWORK_DUPLICATES:
                    continue
                unexpected.append(item.describe(left_root=ROOT, right_root=FRAMEWORK.parent))

        self.assertEqual([], unexpected)

    def test_no_project_file_is_a_byte_copy_of_a_framework_file(self) -> None:
        matches = [
            item.describe(left_root=ROOT, right_root=FRAMEWORK.parent)
            for source in PROJECT_SOURCES
            if source.exists()
            for item in identical_files(source, FRAMEWORK, suffixes=(".py", ".html"))
        ]

        self.assertEqual([], matches)

    def test_project_code_uses_public_entry_points(self) -> None:
        # Admin 内部实现不是公共 API；模板环境要走 render_template/render_fragment。
        # 这个演示本身就是内置 Admin 的宿主，它可以用公开的安装入口，但不该去摸内部模块。
        private_imports = [
            item.describe(root=ROOT)
            for source in PROJECT_SOURCES
            if source.exists()
            for item in forbidden_imports(
                source,
                modules=("oldman.apps.admin",),
                allowed_names=("AdminSite", "install_admin", "ModelAdmin", "AdminUserModelAdmin"),
            )
        ]
        # 视图不直接摸模板环境；服务的 init() 才是安装 loader 和全局变量的地方。
        raw_environment = [
            item.describe(root=ROOT)
            for item in forbidden_attributes(ROOT / "apps", attributes=("app.ext.environment",))
        ]

        self.assertEqual([], private_imports)
        self.assertEqual([], raw_environment)


if __name__ == "__main__":
    unittest.main()
