from __future__ import annotations

import time

from rich.progress import ProgressColumn, Task
from rich.text import Text as _Text


class _DotBarColumn(ProgressColumn):
    def render(self, task: Task) -> _Text:
        width = 20
        if task.total is None or task.total == 0:
            pulse = int(time.time() * 4) % width
            dots = "○" * pulse + "●" + "○" * (width - pulse - 1)
            return _Text(dots, style="yellow")
        filled = round(task.completed / task.total * width)
        return _Text("●" * filled + "○" * (width - filled), style="green")


def _bar(value: int, maximum: int, width: int = 18) -> str:
    filled = round(value / maximum * width) if maximum else 0
    return "●" * filled + "○" * (width - filled)


def _lang_color(pending_count: int) -> str:
    return "yellow" if pending_count > 0 else "green"


def _proportional_width(count: int, max_count: int, max_width: int = 20) -> int:
    if max_count == 0:
        return 0
    return max(1, round(count / max_count * max_width))
