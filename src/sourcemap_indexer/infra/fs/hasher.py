from __future__ import annotations

import hashlib
from pathlib import Path

from sourcemap_indexer.domain.value_objects import ContentHash
from sourcemap_indexer.lib.either import Either, left, right


def hash_content(data: bytes) -> ContentHash:
    return ContentHash(hashlib.sha256(data).hexdigest())


def hash_file(path: Path) -> Either[str, ContentHash]:
    try:
        return right(hash_content(path.read_bytes()))
    except FileNotFoundError:
        return left("file-not-found")
    except OSError as error:
        return left(f"read-error: {error}")
