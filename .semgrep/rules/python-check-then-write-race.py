from pathlib import Path


def bad_write_text(p: Path) -> None:
    # ruleid: python-check-then-write-race
    if not p.exists():
        p.write_text("data")


def bad_write_bytes(p: Path) -> None:
    # ruleid: python-check-then-write-race
    if not p.exists():
        p.write_bytes(b"data")


def ok_direct_write(p: Path) -> None:
    # ok: python-check-then-write-race
    p.write_text("data")


def ok_exists_no_write(p: Path) -> bool:
    # ok: python-check-then-write-race
    return p.exists()
