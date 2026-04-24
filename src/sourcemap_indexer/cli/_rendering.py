from __future__ import annotations

import time
from collections.abc import Callable

from rich.align import Align as _Align
from rich.console import ConsoleRenderable, RichCast
from rich.panel import Panel as _Panel
from rich.progress import (
    MofNCompleteColumn,
    Progress,
    ProgressColumn,
    SpinnerColumn,
    Task,
    TaskID,
    TextColumn,
)
from rich.text import Text as _Text

_PANEL_STYLES: dict[str, str] = {"info": "bright_blue", "warn": "yellow", "error": "red"}

_Renderable = ConsoleRenderable | RichCast | str


class _DotBarColumn(ProgressColumn):
    def render(self, task: Task) -> _Text:
        width = 20
        if task.total is None or task.total == 0:
            pulse = int(time.time() * 4) % width
            dots = "○" * pulse + "●" + "○" * (width - pulse - 1)
            return _Text(dots, style="yellow")
        filled = round(task.completed / task.total * width)
        return _Text("●" * filled + "○" * (width - filled), style="green")


def _panel(content: _Renderable, title: str, style: str = "info") -> _Panel:
    return _Panel(content, title=title, border_style=_PANEL_STYLES[style], title_align="left")


class _StaticProgressColumn(ProgressColumn):
    _WIDTH = 16

    def render(self, task: Task) -> _Text:
        if task.total is None or task.total == 0:
            return _Text("○" * self._WIDTH, style="dim")
        filled = min(self._WIDTH, round(task.completed / task.total * self._WIDTH))
        text = _Text()
        text.append("●" * filled, style="green")
        text.append("○" * (self._WIDTH - filled), style="dim")
        return text


class _HeartbeatColumn(ProgressColumn):
    _N = 4
    _PERIOD = 0.8

    def _brightness(self, dot: int, now: float) -> float:
        phase = (now % self._PERIOD) / self._PERIOD
        peak = phase * (self._N + 4) - 2
        return max(0.0, 1.0 - abs(peak - dot) / 3.0)

    _OFF_THRESHOLD = 0.01
    _DIM_THRESHOLD = 0.40
    _MID_THRESHOLD = 0.70

    def _color(self, brightness: float) -> str:
        if brightness < self._OFF_THRESHOLD:
            return "grey42"
        if brightness < self._DIM_THRESHOLD:
            return "#885500"
        if brightness < self._MID_THRESHOLD:
            return "#cc8800"
        return "#ffcc00"

    def render(self, task: Task) -> _Text:
        text = _Text()
        if task.total and task.completed >= task.total:
            for _ in range(self._N):
                text.append("●", style="green")
            return text
        now = time.time()
        for dot in range(self._N):
            text.append("●", style=self._color(self._brightness(dot, now)))
        return text


class EnrichProgressDisplay:
    def __init__(self, prog: Progress, task_scan: TaskID, task_enrich: TaskID) -> None:
        self._prog = prog
        self._task_scan = task_scan
        self._task_enrich = task_enrich

    @classmethod
    def create(cls) -> EnrichProgressDisplay:
        prog = Progress(
            SpinnerColumn(finished_text="[green]✓[/green]"),
            TextColumn("[progress.description]{task.description}"),
            _StaticProgressColumn(),
            _HeartbeatColumn(),
            MofNCompleteColumn(),
            TextColumn("[dim]{task.fields[file]}[/dim]"),
            refresh_per_second=20,
        )
        task_scan = prog.add_task("Scanning...", total=None, file="")
        task_enrich = prog.add_task("Enriching...", total=None, file="", visible=False)
        return cls(prog, task_scan, task_enrich)

    def renderable(self) -> Progress:
        return self._prog

    def on_scan_complete(self) -> None:
        self._prog.update(self._task_scan, visible=False)
        self._prog.update(self._task_enrich, visible=True, description="Enriching...")

    def on_file(self, path: str, success: bool, current: int, total: int) -> None:
        if current == 1:
            label = "file" if total == 1 else "files"
            self._prog.update(self._task_enrich, description=f"Enriching  {total} {label}")
        self._prog.update(self._task_enrich, completed=current, total=total, file=path)

    def progress_callback(self) -> Callable[[str, bool, int, int], None]:
        return self.on_file


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
