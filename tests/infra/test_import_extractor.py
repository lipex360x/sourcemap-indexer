from __future__ import annotations

from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.import_extractor import _EXTRACTORS, PythonImportExtractor


def test_extract_simple_import_to_path() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("import my_module", "src/app.py")
    assert result == ["my_module.py"]


def test_extract_dotted_import_to_nested_path() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("import my_package.sub.module", "src/app.py")
    assert result == ["my_package/sub/module.py"]


def test_extract_from_import_returns_module_path() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("from my_package.utils import helper", "src/app.py")
    assert result == ["my_package/utils.py"]


def test_extract_multiple_names_from_same_module_deduplicates() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("from my_package.utils import foo, bar", "src/app.py")
    assert result == ["my_package/utils.py"]


def test_extract_filters_relative_imports() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("from . import sibling\nfrom .utils import helper", "src/app.py")
    assert result == []


def test_extract_filters_stdlib_import() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("import os\nimport sys\nimport pathlib", "src/app.py")
    assert result == []


def test_extract_filters_stdlib_from_import() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("from pathlib import Path\nfrom typing import Any", "src/app.py")
    assert result == []


def test_extract_filters_external_packages() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("import pytest\nimport httpx", "src/app.py")
    assert result == []


def test_extract_mixed_content_returns_local_only() -> None:
    extractor = PythonImportExtractor()
    content = (
        "import os\n"
        "import my_domain.entity\n"
        "from . import sibling\n"
        "from my_infra.repo import SqliteRepo\n"
        "import pytest\n"
    )
    result = extractor.extract(content, "src/app.py")
    assert "my_domain/entity.py" in result
    assert "my_infra/repo.py" in result
    assert len(result) == 2


def test_extract_handles_syntax_error_gracefully() -> None:
    extractor = PythonImportExtractor()
    result = extractor.extract("not valid python !!!###", "src/app.py")
    assert result == []


def test_extractors_registry_has_python() -> None:
    assert Language.PY in _EXTRACTORS


def test_extractors_registry_python_callable_works() -> None:
    extract_fn = _EXTRACTORS[Language.PY]
    result = extract_fn("import my_local", "src/app.py")
    assert "my_local.py" in result


def test_extractors_registry_unknown_language_absent() -> None:
    assert Language.OTHER not in _EXTRACTORS
