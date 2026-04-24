from __future__ import annotations

from sourcemap_indexer.domain.value_objects import Language
from sourcemap_indexer.infra.parser.import_extractor import _EXTRACTORS, TypeScriptImportExtractor

_EXTS = (".ts", ".tsx", ".js", ".jsx")
_INDEX = ("/index.ts", "/index.tsx")


def _candidates(base: str) -> list[str]:
    return [base + ext for ext in _EXTS] + [base + idx for idx in _INDEX]


def test_default_import_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import X from './utils'", "src/app.ts")
    assert set(result) == set(_candidates("src/utils"))


def test_named_import_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import { a, b } from './helpers'", "src/app.ts")
    assert set(result) == set(_candidates("src/helpers"))


def test_namespace_import_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import * as X from './api'", "src/app.ts")
    assert set(result) == set(_candidates("src/api"))


def test_type_import_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import type { Foo } from './types'", "src/app.ts")
    assert set(result) == set(_candidates("src/types"))


def test_require_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("const x = require('./config')", "src/app.ts")
    assert set(result) == set(_candidates("src/config"))


def test_parent_dir_resolution() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import X from '../utils'", "src/components/Button.tsx")
    assert set(result) == set(_candidates("src/utils"))


def test_absolute_specifier_returns_candidates() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import X from '/shared/utils'", "src/app.ts")
    assert set(result) == set(_candidates("/shared/utils"))


def test_export_from_not_matched() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("export { helper } from './utils'", "src/app.ts")
    assert result == []


def test_nested_parent_resolution() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import X from '../../shared'", "src/a/b/c.ts")
    assert set(result) == set(_candidates("src/shared"))


def test_bare_specifier_filtered() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import React from 'react'", "src/app.tsx")
    assert result == []


def test_scoped_package_filtered() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import { something } from '@scope/package'", "src/app.ts")
    assert result == []


def test_multiple_bare_specifiers_all_filtered() -> None:
    extractor = TypeScriptImportExtractor()
    content = "import React from 'react'\nimport _ from 'lodash'\nimport axios from 'axios'"
    result = extractor.extract(content, "src/app.ts")
    assert result == []


def test_mixed_bare_and_relative_returns_only_relative() -> None:
    extractor = TypeScriptImportExtractor()
    content = "import React from 'react'\nimport { helper } from './utils'"
    result = extractor.extract(content, "src/app.ts")
    assert all("utils" in r for r in result)
    assert not any("react" in r for r in result)


def test_multiple_relative_imports_deduplicates() -> None:
    extractor = TypeScriptImportExtractor()
    content = "import { a } from './utils'\nimport { b } from './utils'"
    result = extractor.extract(content, "src/app.ts")
    assert len([r for r in result if "utils" in r]) == len(_candidates("src/utils"))


def test_empty_content_returns_empty() -> None:
    extractor = TypeScriptImportExtractor()
    assert extractor.extract("", "src/app.ts") == []


def test_no_imports_returns_empty() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("const x = 1\nconst y = 2", "src/app.ts")
    assert result == []


def test_six_candidates_per_specifier() -> None:
    extractor = TypeScriptImportExtractor()
    result = extractor.extract("import X from './foo'", "src/app.ts")
    assert len(result) == 6


def test_extractors_registry_has_ts() -> None:
    assert Language.TS in _EXTRACTORS


def test_extractors_registry_has_js() -> None:
    assert Language.JS in _EXTRACTORS


def test_extractors_registry_has_tsx() -> None:
    assert Language.TSX in _EXTRACTORS


def test_extractors_ts_callable_works() -> None:
    extract_fn = _EXTRACTORS[Language.TS]
    result = extract_fn("import X from './utils'", "src/app.ts")
    assert any("utils" in r for r in result)


def test_extractors_js_callable_works() -> None:
    extract_fn = _EXTRACTORS[Language.JS]
    result = extract_fn("const x = require('./lib')", "src/app.js")
    assert any("lib" in r for r in result)


def test_extractors_tsx_callable_works() -> None:
    extract_fn = _EXTRACTORS[Language.TSX]
    result = extract_fn("import { Component } from './base'", "src/components/App.tsx")
    assert any("base" in r for r in result)
