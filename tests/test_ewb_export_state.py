from types import SimpleNamespace

from ihs.ui.exposure_wb_window import _ewb_invalidate
from ihs.ui.batch_control_state import sync_batch_controls


class _Value:
    def __init__(self, value=False):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


def test_node_owner_controls_export_state_after_reference_invalidation():
    calls = []
    owner = SimpleNamespace(
        ewb_exposure_enabled=_Value(False),
        ewb_wb_enabled=_Value(False),
        ewb_deflicker_enabled=_Value(True),
        ewb_status=_Value(),
        _ewb_anchors=[],
        _ewb_additional_smoothing_rounds=0,
        _ewb_table=None,
        _ewb_display_table=None,
        _ewb_correction_signature=None,
        reference_master=object(),
        _ewb_reference_invalidated=lambda: calls.append("refresh"),
    )

    _ewb_invalidate(owner, "toggle")

    assert owner.reference_master is None
    assert calls == ["refresh"]


class _Button:
    def __init__(self, state):
        self.state = state

    def cget(self, _key):
        return self.state

    def configure(self, *, state):
        self.state = state


class _Worker:
    def __init__(self, running):
        self.running = running

    def is_alive(self):
        return self.running


def test_batch_controls_self_heal_from_worker_state():
    owner = SimpleNamespace(
        worker=_Worker(False), start_btn=_Button("disabled"), cancel_btn=_Button("normal")
    )
    sync_batch_controls(owner)
    assert owner.start_btn.state == "normal"
    assert owner.cancel_btn.state == "disabled"

    owner.worker.running = True
    sync_batch_controls(owner)
    assert owner.start_btn.state == "disabled"
    assert owner.cancel_btn.state == "normal"
