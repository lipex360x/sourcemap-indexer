import os
from pathlib import Path


def bad_write_text(p: Path) -> None:
    # ruleid: python-non-atomic-write
    p.write_text("content")


def bad_write_bytes(p: Path) -> None:
    # ruleid: python-non-atomic-write
    p.write_bytes(b"content")


def ok_atomic_text(p: Path) -> None:
    # ok: python-non-atomic-write
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text("content")
    os.replace(tmp, p)


def ok_atomic_bytes(p: Path) -> None:
    # ok: python-non-atomic-write
    tmp = p.with_suffix(".tmp")
    tmp.write_bytes(b"content")
    os.replace(tmp, p)


def ok_write_to_named_tmp(output: Path) -> None:
    # ok: python-non-atomic-write
    tmp_path = output.with_suffix(output.suffix + ".tmp")
    tmp_path.write_text("data")
    os.replace(tmp_path, output)
