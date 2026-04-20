from __future__ import annotations

import time

from rich.align import Align as _Align
from rich.console import ConsoleRenderable, RichCast
from rich.panel import Panel as _Panel
from rich.progress import ProgressColumn, Task
from rich.text import Text as _Text

_PANEL_STYLES: dict[str, str] = {"info": "bright_blue", "warn": "yellow", "error": "red"}

_Renderable = ConsoleRenderable | RichCast | str


def _panel(content: _Renderable, title: str, style: str = "info") -> _Panel:
    return _Panel(content, title=title, border_style=_PANEL_STYLES[style], title_align="left")


class _DotBarColumn(ProgressColumn):
    def render(self, task: Task) -> _Text:
        width = 20
        if task.total is None or task.total == 0:
            pulse = int(time.time() * 4) % width
            dots = "○" * pulse + "●" + "○" * (width - pulse - 1)
            return _Text(dots, style="yellow")
        filled = round(task.completed / task.total * width)
        return _Text("●" * filled + "○" * (width - filled), style="green")


class _HybridProgressColumn(ProgressColumn):
    def __init__(self, width: int = 20, speed: float = 16.0) -> None:
        self._width = width
        self._speed = speed
        super().__init__()

    def render(self, task: Task) -> _Text:
        width = self._width
        if task.total is None or task.total == 0:
            pulse = int(time.time() * self._speed) % width
            return _Text("○" * pulse + "●" + "○" * (width - pulse - 1), style="dim")
        green = min(width, round(task.completed / task.total * width))
        pending = width - green
        if pending == 0:
            return _Text("●" * width, style="green")
        cycle = max(1, pending * 2 - 2)
        tick = int(time.time() * self._speed) % cycle
        pulse_pos = tick if tick < pending else cycle - tick
        text = _Text()
        text.append("●" * green, style="green")
        if pulse_pos > 0:
            text.append("○" * pulse_pos, style="dim")
        text.append("●", style="yellow")
        if pending - pulse_pos - 1 > 0:
            text.append("○" * (pending - pulse_pos - 1), style="dim")
        return text


def _bar(value: int, maximum: int, width: int = 18) -> str:
    filled = round(value / maximum * width) if maximum else 0
    return "●" * filled + "○" * (width - filled)


def _lang_color(pending_count: int) -> str:
    return "yellow" if pending_count > 0 else "green"


def _proportional_width(count: int, max_count: int, max_width: int = 20) -> int:
    if max_count == 0:
        return 0
    return max(1, round(count / max_count * max_width))


def _enriched_bar(enriched_count: int, total_count: int, width: int) -> str:
    filled = round(enriched_count / total_count * width) if total_count else 0
    return "●" * filled + "○" * (width - filled)


def _color_legend() -> _Align:
    markup = (
        "[green]●[/green] all enriched"
        "  [dim]|[/dim]  "
        "[yellow]●[/yellow] has pending"
        "  [dim]|[/dim]  "
        "[yellow]○[/yellow] not yet enriched"
    )
    return _Align(markup, align="right")
