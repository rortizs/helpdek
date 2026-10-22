"""22/10/2026 - Prueba de compatibilidad con Python 3.11+ (lo que pide pyproject.toml).

Encontre que con Python 3.14 todo pasaba, pero en 3.11-3.13 el proyecto no
importaba: una clase con un metodo `list` y anotaciones `list[...]` sin
`from __future__ import annotations`. Esta prueba revisa el codigo fuente, asi
que falla aunque la suite se ejecute con 3.14.
"""

from __future__ import annotations

import ast
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent / "app"


def _defines_method_named_list(tree: ast.Module) -> bool:
    # 22/10/2026 - Busco clases con un metodo `list`: son las que tapan al tipo nativo.
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "list":
                    return True
    return False


def _has_future_annotations(tree: ast.Module) -> bool:
    return any(
        isinstance(node, ast.ImportFrom)
        and node.module == "__future__"
        and any(alias.name == "annotations" for alias in node.names)
        for node in tree.body
    )


def test_modules_that_shadow_list_postpone_annotations():
    # 22/10/2026 - Cada modulo que define un metodo `list` debe posponer las anotaciones.
    offenders = []
    for path in sorted(APP_DIR.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        if _defines_method_named_list(tree) and not _has_future_annotations(tree):
            offenders.append(str(path.relative_to(APP_DIR.parent)))
    assert offenders == []
