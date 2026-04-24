from pathlib import Path


def bad_read_text(p: Path) -> str:
    # ruleid: python-toctou-exists-then-read
    if p.exists():
        return p.read_text()
    return ""


def bad_read_bytes(p: Path) -> bytes:
    # ruleid: python-toctou-exists-then-read
    if p.exists():
        return p.read_bytes()
    return b""


def ok_try_except(p: Path) -> str:
    # ok: python-toctou-exists-then-read
    try:
        return p.read_text()
    except FileNotFoundError:
        return ""


def ok_exists_no_read(p: Path) -> None:
    # ok: python-toctou-exists-then-read
    if p.exists():
        print("found")


def ok_read_without_exists(p: Path) -> str:
    # ok: python-toctou-exists-then-read
    return p.read_text()


def ok_exists_then_try_read(p: Path) -> str:
    # ok: python-toctou-exists-then-read
    if p.exists():
        try:
            return p.read_text()
        except OSError:
            return ""
    return ""
