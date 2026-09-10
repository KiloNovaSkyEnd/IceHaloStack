"""State-derived Tk batch controls shared by legacy workflow windows."""

from __future__ import annotations


def sync_batch_controls(owner):
    """Heal stale button state from the authoritative worker lifecycle."""
    try:
        running = bool(owner.worker and owner.worker.is_alive())
        start_state = "disabled" if running else "normal"
        cancel_state = "normal" if running else "disabled"
        if str(owner.start_btn.cget("state")) != start_state:
            owner.start_btn.configure(state=start_state)
        if str(owner.cancel_btn.cget("state")) != cancel_state:
            owner.cancel_btn.configure(state=cancel_state)
    except Exception:
        pass
