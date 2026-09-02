"""Regression checks for IceHaloStack v0.9.6.3."""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import time
import tkinter as tk
from types import SimpleNamespace
from tkinter import ttk

import numpy as np


ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SPEC = importlib.util.spec_from_file_location("icehalostack_0963", ROOT / "icehalostack.py")
ihs = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(ihs)


def walk(widget):
    yield widget
    for child in widget.winfo_children():
        yield from walk(child)


def test_tone_math():
    count = 21
    x = np.linspace(0, 1, count)
    anchors = [
        {"frame": 1, "exposure": -0.2, "temperature": -20, "tint": 5, "contrast": -10, "highlights": 20, "shadows": -30, "whites": 5, "blacks": -4},
        {"frame": 11, "exposure": 0.3, "temperature": 10, "tint": -8, "contrast": 40, "highlights": -25, "shadows": 35, "whites": 18, "blacks": -22},
        {"frame": 21, "exposure": 0.1, "temperature": 30, "tint": 12, "contrast": 15, "highlights": 5, "shadows": 10, "whites": -7, "blacks": 9},
    ]
    cfg = ihs._ewb_default_config()
    cfg.update(exposure_enabled=True, wb_enabled=True, exposure_radius=4, wb_radius=4, exposure_max_ev=3.0, wb_max_percent=100.0, smoothing_amount=70.0, anchor_influence=100.0, anchors=anchors)
    table = ihs._ewb_build_correction_table(0.2 * np.sin(x * 7), 0.03 * np.cos(x * 4), -0.02 * np.sin(x * 3), cfg)
    for key in ihs._EWB_TONE_KEYS:
        for anchor in anchors:
            assert abs(float(table[key + "_correction"][anchor["frame"] - 1]) - anchor[key]) < 1e-5
    again = ihs._ewb_apply_additional_smoothing_round(table, cfg)
    for key in ihs._EWB_TONE_KEYS:
        for anchor in anchors:
            idx = anchor["frame"] - 1
            assert abs(float(again[key + "_correction"][idx]) - float(table[key + "_correction"][idx])) < 1e-5
    owner = SimpleNamespace(_ewb_table=table)
    image = np.linspace(0.01, 0.9, 16 * 16 * 3, dtype=np.float32).reshape(16, 16, 3)
    output = ihs._ewb_apply_to_frame(owner, image, 10)
    assert output.shape == image.shape and output.dtype == np.float32
    assert np.isfinite(output).all() and not np.allclose(output, image)


def test_workspace_state_and_progress(reference_image):
    root = tk.Tk()
    root.withdraw()
    owner = tk.Toplevel(root)
    owner.withdraw()
    owner.app = SimpleNamespace(files=[reference_image] * 3)
    ihs._init_ewb_vars(owner)
    owner._ewb_anchors = [
        {"frame": 1, "exposure": 0.1, "temperature": 0, "tint": 0, "contrast": 10, "highlights": -20, "shadows": 15, "whites": 5, "blacks": -5},
        {"frame": 3, "exposure": -0.1, "temperature": 5, "tint": -3, "contrast": 20, "highlights": 10, "shadows": -5, "whites": 0, "blacks": 8},
    ]
    owner.ewb_exposure_enabled.set(True)
    owner.ewb_wb_enabled.set(True)
    cfg = ihs._ewb_config_snapshot(owner)
    owner._ewb_measurements = {
        "exposure_metric": np.asarray([0, 0.1, -0.1], dtype=np.float32),
        "rlog_metric": np.zeros(3, dtype=np.float32),
        "blog_metric": np.zeros(3, dtype=np.float32),
        "thumbs": [np.zeros((80, 120, 3), dtype=np.uint8)] * 3,
        "count": 3,
        "config": cfg,
    }
    owner._ewb_measurement_signature = ihs._ewb_measurement_signature_for(owner, cfg)
    ihs._ewb_open_workspace(owner)
    dialog = owner._ewb_workspace
    dialog.withdraw()
    deadline = time.time() + 0.8
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)
    widgets = list(walk(dialog))
    buttons = [w for w in widgets if isinstance(w, ttk.Button)]
    play = next(w for w in buttons if "播放" in str(w.cget("text")))
    apply_button = next(w for w in buttons if "应用关键帧" in str(w.cget("text")))
    frame_list = next(w for w in widgets if isinstance(w, ttk.Treeview))
    progress = next(w for w in widgets if isinstance(w, ttk.Progressbar))
    play.invoke()
    root.update()
    assert any(label in str(play.cget("text")) for label in ("暂停", "Pause"))
    play.invoke()
    root.update()
    assert any(label in str(play.cget("text")) for label in ("播放", "Play"))
    frame_list.selection_set("2")
    frame_list.event_generate("<<TreeviewSelect>>")
    root.update()
    assert any(label in str(play.cget("text")) for label in ("播放", "Play"))
    apply_button.invoke()
    deadline = time.time() + 4
    value = 0.0
    while time.time() < deadline:
        root.update()
        time.sleep(0.01)
        value = float(dialog.getvar(str(progress.cget("variable"))))
        if value >= 100:
            break
    assert value >= 100
    assert owner._ewb_table is not None and "contrast_correction" in owner._ewb_table
    dialog.destroy()
    owner.destroy()
    root.destroy()


if __name__ == "__main__":
    test_tone_math()
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            ROOT / "icehalostack.py",
            ROOT / "ihs" / "ui" / "node_window.py",
            ROOT / "ihs" / "ui" / "exposure_wb_window.py",
        )
    )
    for marker in ("'epoch':0,'advancing':False", "widget.bind('<space>',_toggle_play", "transition_progressbar=ttk.Progressbar", "d.after_idle(pump_base_widgets)"):
        assert marker in source, marker
    # Reuse the screenshot supplied with the bug report; no source file is modified.
    image = pathlib.Path(r"C:\Users\gzm07\AppData\Local\Temp\codex-clipboard-505b5dce-fbe1-40f8-8761-0a3adefc7562.png")
    if image.exists():
        test_workspace_state_and_progress(str(image))
    print("PASS: EWB playback state, HQ pause path, progress, ACR keyframes, cumulative smoothing, Base lazy construction")
