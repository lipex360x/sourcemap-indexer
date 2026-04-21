from __future__ import annotations

from sourcemap_indexer.cli._rendering import (
    EnrichProgressDisplay,
    _DotBarColumn,
    _HeartbeatColumn,
    _StaticProgressColumn,
)


def _make_task(completed: float = 0, total: float | None = None):  # type: ignore[return]
    from rich.progress import Progress

    prog = Progress()
    task_id = prog.add_task("t", total=total)
    if completed:
        prog.update(task_id, completed=completed)
    return prog.tasks[0]


def test_dot_bar_indeterminate_has_one_bullet() -> None:
    col = _DotBarColumn()
    task = _make_task(total=None)
    text = col.render(task)
    assert text.plain.count("●") == 1
    assert len(text.plain) == 20


def test_dot_bar_filled_is_all_green() -> None:
    col = _DotBarColumn()
    task = _make_task(completed=20, total=20)
    text = col.render(task)
    assert text.plain == "●" * 20


def test_static_column_no_total_returns_dim_dots() -> None:
    col = _StaticProgressColumn()
    task = _make_task(total=None)
    text = col.render(task)
    plain = text.plain
    assert plain == "○" * 16
    assert all(s.style == "dim" for s in text._spans)


def test_static_column_zero_total_returns_dim_dots() -> None:
    col = _StaticProgressColumn()
    task = _make_task(total=0)
    text = col.render(task)
    assert text.plain == "○" * 16


def test_static_column_half_progress() -> None:
    col = _StaticProgressColumn()
    task = _make_task(completed=8, total=16)
    text = col.render(task)
    assert text.plain == "●" * 8 + "○" * 8


def test_static_column_full_progress() -> None:
    col = _StaticProgressColumn()
    task = _make_task(completed=16, total=16)
    text = col.render(task)
    assert text.plain == "●" * 16


def test_static_column_total_width_is_16() -> None:
    col = _StaticProgressColumn()
    for completed in (0, 4, 8, 12, 16):
        task = _make_task(completed=completed, total=16)
        assert len(col.render(task).plain) == 16


def test_heartbeat_brightness_peak_at_dot() -> None:
    col = _HeartbeatColumn()
    peak_zero_time = col._PERIOD * 0.25
    assert col._brightness(0, peak_zero_time) == 1.0


def test_heartbeat_brightness_falloff_one_dot() -> None:
    col = _HeartbeatColumn()
    peak_zero_time = col._PERIOD * 0.25
    brightness = col._brightness(1, peak_zero_time)
    assert abs(brightness - (1 - 1 / 3)) < 0.01


def test_heartbeat_brightness_falloff_three_dots_is_zero() -> None:
    col = _HeartbeatColumn()
    peak_zero_time = col._PERIOD * 0.25
    brightness = col._brightness(3, peak_zero_time)
    assert brightness == 0.0


def test_heartbeat_brightness_clamps_at_zero() -> None:
    col = _HeartbeatColumn()
    for dot in range(4):
        assert col._brightness(dot, 0.0) >= 0.0


def test_heartbeat_color_zero_brightness() -> None:
    col = _HeartbeatColumn()
    assert col._color(0.0) == "grey42"


def test_heartbeat_color_low_brightness() -> None:
    col = _HeartbeatColumn()
    assert col._color(0.2) == "#885500"  # noqa: WPS432


def test_heartbeat_color_mid_brightness() -> None:
    col = _HeartbeatColumn()
    assert col._color(0.55) == "#cc8800"  # noqa: WPS432


def test_heartbeat_color_full_brightness() -> None:
    col = _HeartbeatColumn()
    assert col._color(1.0) == "#ffcc00"


def test_heartbeat_render_always_uses_bullet_symbol() -> None:
    col = _HeartbeatColumn()
    task = _make_task(total=None)
    text = col.render(task)
    assert text.plain == "●" * 4


def test_heartbeat_render_returns_four_chars() -> None:
    col = _HeartbeatColumn()
    task = _make_task(total=None)
    text = col.render(task)
    assert len(text.plain) == 4


def test_heartbeat_render_complete_is_full_green() -> None:
    col = _HeartbeatColumn()
    task = _make_task(completed=10, total=10)
    text = col.render(task)
    assert text.plain == "●" * 4
    assert all(s.style == "green" for s in text._spans)


def test_heartbeat_wave_cycles_without_crash() -> None:
    col = _HeartbeatColumn()
    task = _make_task(total=None)
    for _step in range(20):
        text = col.render(task)
        assert len(text.plain) == 4


def test_enrich_progress_display_create() -> None:
    display = EnrichProgressDisplay.create()
    assert display.renderable() is not None


def test_enrich_progress_display_on_scan_complete() -> None:
    display = EnrichProgressDisplay.create()
    display.on_scan_complete()
    prog = display.renderable()
    assert prog.tasks[0].visible is False
    assert prog.tasks[1].visible is True


def test_enrich_progress_display_on_file_single() -> None:
    display = EnrichProgressDisplay.create()
    display.on_scan_complete()
    display.on_file("src/a.py", True, 1, 1)
    prog = display.renderable()
    assert prog.tasks[1].completed == 1
    assert prog.tasks[1].total == 1
    assert "1 file" in prog.tasks[1].description


def test_enrich_progress_display_on_file_plural() -> None:
    display = EnrichProgressDisplay.create()
    display.on_scan_complete()
    display.on_file("src/a.py", True, 1, 5)
    prog = display.renderable()
    assert "5 files" in prog.tasks[1].description


def test_enrich_progress_display_progress_callback_is_callable() -> None:
    display = EnrichProgressDisplay.create()
    callback = display.progress_callback()
    assert callable(callback)
    display.on_scan_complete()
    callback("src/a.py", True, 1, 3)
    assert display.renderable().tasks[1].completed == 1
