"""Focused v0.9.6.4 UI/deflicker/batch-export regression checks."""
import pathlib
import shutil
import sys
import time

import numpy as np
import tkinter as tk
from tkinter import ttk

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import icehalostack as ihs


def main():
    app = ihs.App()
    app.withdraw()
    # The production app schedules hardware detection; it is unrelated to this
    # deterministic export test and may probe local CUDA installations.
    for after_id in app.tk.call('after', 'info'):
        try:
            app.after_cancel(after_id)
        except Exception:
            pass

    style = ttk.Style(app)
    assert 'IHS.light.Checkbutton.indicator' in repr(style.layout('TCheckbutton'))
    assert 'Vertical.Scrollbar.thumb' in repr(style.layout('IHS.Vertical.TScrollbar'))
    choice = tk.StringVar(value='PNG 8-bit')
    combo = ttk.Combobox(app, textvariable=choice, state='readonly', values=['PNG 8-bit', 'JPEG', 'TIFF 16-bit'])
    combo.pack()
    app.update()
    combo.current(2)
    combo.event_generate('<<ComboboxSelected>>')
    app.update()
    assert choice.get() == 'TIFF 16-bit' and not combo.selection_present()

    # A synthetic alternating brightness signal should lose its short-period
    # flicker while a display-only curve snapshot survives keyframe changes.
    class Owner:
        pass
    owner = Owner()
    ihs._init_ewb_vars(owner)
    owner.app = type('FakeApp', (), {'files': [f'f{i}' for i in range(101)]})()
    owner.reference_master = None
    owner.ewb_deflicker_enabled.set(True)
    owner.ewb_exposure_max_ev.set(2.0)
    exposure = np.asarray([0.25 * (-1) ** i for i in range(101)], dtype=np.float32)
    zero = np.zeros_like(exposure)
    table = ihs._ewb_build_correction_table(exposure, zero, zero, ihs._ewb_config_snapshot(owner), [])
    assert float(np.std(exposure + table['ev_correction'])) < float(np.std(exposure)) * 0.02
    owner._ewb_table = table
    ihs._ewb_invalidate(owner, 'keyframe changed', analysis=False)
    assert owner._ewb_table is None and owner._ewb_display_table is table

    # Batch export must not require a previously generated reference master.
    out = pathlib.Path(__file__).with_name('_regression_batch_output')
    if out.exists():
        shutil.rmtree(out)
    app.files = ['fake1', 'fake2', 'fake3']
    window = ihs.TimelapseNodeWindow(app)
    window.withdraw()
    window.window_size.set(2)
    window.step.set(1)
    window.output_folder.set(str(out))
    window._ref_lum = lambda: 1.0
    window._decode = lambda idx, ref: np.full((16, 16, 3), 0.1 + 0.1 * idx, dtype=np.float32)
    flow = window.flows[0]
    flow['output'].update(export_enabled=True, save_sequence=True, save_video=False, sequence_format='TIFF 16-bit')
    real_thread = ihs.threading.Thread
    class CapturedThread:
        def __init__(self, target=None, args=(), **_kwargs):
            self.target = target
            self.args = args
            self.started = False
        def start(self):
            self.started = True
        def is_alive(self):
            return False
    ihs.threading.Thread = CapturedThread
    try:
        window.start_batch()
        captured = window.worker
        assert captured.started and captured.target == window._batch_worker
        settings = captured.args[0]
    finally:
        ihs.threading.Thread = real_thread
    # Run the captured job on this main thread. AsyncOutputPipeline still uses
    # its real writer thread, so actual TIFF encoding/writing is exercised.
    window._batch_worker(settings)
    exported = list(out.rglob('*.tif')) if out.exists() else []
    assert len(exported) == 2, (window.status.get(), exported)
    assert window.reference_master is None
    print('CHECKMARK=PASS')
    print('CONTINUOUS_SCROLLBAR=PASS')
    print('COMBOBOX_SWITCH_AND_SELECTION=PASS')
    print('DEFLICKER=PASS')
    print('CURVE_PRESERVATION=PASS')
    print('BATCH_EXPORT_WITHOUT_REFERENCE=PASS')
    window.destroy()
    app.destroy()
    shutil.rmtree(out)


if __name__ == '__main__':
    main()
