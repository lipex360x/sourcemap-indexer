from __future__ import annotations

import ast
import importlib.util
import sys
from collections.abc import Callable
from typing import Protocol

from sourcemap_indexer.domain.value_objects import Language


class ImportExtractor(Protocol):
    def extract(self, content: str, file_path: str) -> list[str]: ...


def _module_to_path(module_name: str) -> str:
    return module_name.replace(".", "/") + ".py"


def _is_stdlib(module_name: str) -> bool:
    return module_name in sys.stdlib_module_names


def _is_external(module_name: str) -> bool:
    try:
        spec = importlib.util.find_spec(module_name)
    except (ModuleNotFoundError, ValueError):
        return False
    if spec is None:
        return False
    origin = spec.origin or ""
    return "site-packages" in origin or "dist-packages" in origin


def _should_skip(module_name: str) -> bool:
    return _is_stdlib(module_name) or _is_external(module_name)


class PythonImportExtractor:
    def _add_import(self, alias: ast.alias, seen: set[str], paths: list[str]) -> None:
        top = alias.name.split(".")[0]
        full_path = _module_to_path(alias.name)
        if full_path not in seen and not _should_skip(top):
            seen.add(full_path)
            paths.append(full_path)

    def _add_from(self, node: ast.ImportFrom, seen: set[str], paths: list[str]) -> None:
        if node.level > 0 or node.module is None:
            return
        top = node.module.split(".")[0]
        full_path = _module_to_path(node.module)
        if full_path not in seen and not _should_skip(top):
            seen.add(full_path)
            paths.append(full_path)

    def _gather(self, tree: ast.AST) -> list[str]:
        seen: set[str] = set()
        paths: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_import(alias, seen, paths)
            elif isinstance(node, ast.ImportFrom):
                self._add_from(node, seen, paths)
        return paths

    def extract(self, content: str, file_path: str) -> list[str]:
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return []
        return self._gather(tree)


_EXTRACTORS: dict[Language, Callable[[str, str], list[str]]] = {
    Language.PY: PythonImportExtractor().extract,
}
