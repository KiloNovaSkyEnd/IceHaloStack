"""Service boundaries for WinUI-native parity workspaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from ..exposure_wb import _ewb_build_correction_table, _ewb_default_config
from ..node_workflow import NODE_ORDER, flow_exec_order, node_enabled


class NodeWorkflowService:
    def inspect(self, flow: Mapping[str, Any]) -> dict[str, Any]:
        """Validate graph topology and return its executable native-page model."""
        if not isinstance(flow, Mapping):
            raise ValueError("flow 必须是对象。")
        candidate = dict(flow)
        candidate.setdefault("cfg", {})
        candidate.setdefault("present_nodes", [key for key, _ in NODE_ORDER])
        candidate.setdefault("edges", [])
        order = flow_exec_order(candidate)
        return {
            "present_nodes": list(candidate["present_nodes"]),
            "execution_order": order,
            "enabled_nodes": [key for key in order if node_enabled(candidate, key)],
            "edges": [list(edge) for edge in candidate["edges"]],
        }


class ExposureSmoothingService:
    def build(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Build the keyframe-smoothed correction table without any Tk state."""
        exposure = params.get("exposure_metric")
        red_log = params.get("rlog_metric")
        blue_log = params.get("blog_metric")
        if not all(isinstance(item, Sequence) and not isinstance(item, (str, bytes))
                   for item in (exposure, red_log, blue_log)):
            raise ValueError("曝光与白平衡测量值必须是数组。")
        if not (len(exposure) == len(red_log) == len(blue_log)) or not exposure:
            raise ValueError("三个测量数组必须长度相同且非空。")
        config = _ewb_default_config()
        supplied = params.get("config", {})
        if not isinstance(supplied, Mapping):
            raise ValueError("config 必须是对象。")
        config.update(supplied)
        table = _ewb_build_correction_table(exposure, red_log, blue_log, config)
        return {
            key: value.tolist() if hasattr(value, "tolist") else value
            for key, value in table.items()
        }


class StorageInspectionService:
    def inspect(self, paths: Sequence[str | Path]) -> dict[str, Any]:
        """Describe user-selected files/directories for a future storage page."""
        entries = []
        total = 0
        for raw in paths:
            path = Path(raw).expanduser().resolve()
            if path.is_file():
                size, count = path.stat().st_size, 1
            elif path.is_dir():
                files = [item for item in path.rglob("*") if item.is_file()]
                size, count = sum(item.stat().st_size for item in files), len(files)
            else:
                size, count = 0, 0
            total += size
            entries.append({"path": str(path), "exists": path.exists(), "bytes": size, "files": count})
        return {"entries": entries, "total_bytes": total}
