"""Service boundaries for WinUI-native parity workspaces."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..exposure_wb import (
    _ewb_apply_to_frame,
    _ewb_apply_additional_smoothing_round,
    _ewb_build_correction_table,
    _ewb_default_config,
    _ewb_measure_proxy,
)
from ..image_io import make_float_preview_proxy
from ..node_workflow import NODE_ORDER, flow_exec_order, node_enabled
from .contracts import ExportRequest, ProgressEvent, ServiceCancelled
from .exporting import ExportService
from .processing import ImageProcessingService, _cancelled


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
    def __init__(self, *, progress=None, cancellation=None):
        self.progress = progress
        self.cancellation = cancellation

    def _emit(self, phase: str, completed: int, total: int, message: str) -> None:
        if self.progress is not None:
            self.progress(ProgressEvent(phase, completed, total, message))

    def analyze(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Measure source frames and build a reusable native keyframe table."""
        paths = params.get("input_paths")
        if not isinstance(paths, Sequence) or isinstance(paths, (str, bytes)) or not paths:
            raise ValueError("input_paths 必须是非空数组。")
        config = _ewb_default_config()
        supplied = params.get("config", {})
        if not isinstance(supplied, Mapping):
            raise ValueError("config 必须是对象。")
        config.update(supplied)
        processor = ImageProcessingService(cancellation=self.cancellation)
        exposure: list[float] = []
        red_log: list[float] = []
        blue_log: list[float] = []
        names: list[str] = []
        total = len(paths)
        for index, raw_path in enumerate(paths):
            if _cancelled(self.cancellation):
                raise ServiceCancelled("曝光/白平衡分析已取消。")
            path = Path(raw_path).expanduser().resolve()
            if not path.is_file():
                raise FileNotFoundError(f"找不到第 {index + 1} 帧：{path}")
            image = processor.load(path)
            proxy, _ = make_float_preview_proxy(image, int(config.get("proxy_max_side", 512)))
            e, r, b = _ewb_measure_proxy(proxy, config)
            exposure.append(e); red_log.append(r); blue_log.append(b); names.append(path.name)
            self._emit("ewb-analysis", index + 1, total, f"分析曝光/白平衡 {index + 1}/{total}")
        result = self.build({
            "exposure_metric": exposure,
            "rlog_metric": red_log,
            "blog_metric": blue_log,
            "config": config,
        })
        result["input_paths"] = [str(Path(path).expanduser().resolve()) for path in paths]
        result["file_names"] = names
        return result

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

    def preview(self, params: Mapping[str, Any]) -> dict[str, Any]:
        """Render one corrected proxy from an already-built correction table."""
        input_path = params.get("input_path")
        output_path = params.get("output_path")
        original_output_path = params.get("original_output_path")
        table = params.get("table")
        if not isinstance(input_path, (str, Path)) or not isinstance(output_path, (str, Path)):
            raise ValueError("preview 需要 input_path 和 output_path。")
        if not isinstance(table, Mapping):
            raise ValueError("preview.table 必须是修正表对象。")
        index = int(params.get("frame_index", 0))
        processor = ImageProcessingService(cancellation=self.cancellation)
        image = processor.load(input_path)
        proxy, scale = make_float_preview_proxy(image, max(128, min(2048, int(params.get("max_side", 1000)))))
        original_saved = None
        if isinstance(original_output_path, (str, Path)):
            original_saved = ExportService(cancellation=self.cancellation).save(
                ExportRequest(original_output_path, proxy, "PNG 8-bit", "Fast")
            )
        corrected = _ewb_apply_to_frame(SimpleNamespace(_ewb_table=dict(table)), proxy, index)
        saved = ExportService(cancellation=self.cancellation).save(
            ExportRequest(output_path, corrected, "PNG 8-bit", "Fast")
        )
        self._emit("ewb-preview", 1, 1, "关键帧修正预览已生成")
        return {
            "output_path": str(saved),
            "original_output_path": str(original_saved) if original_saved else None,
            "frame_index": index,
            "scale": float(scale),
        }

    def resmooth(self, params: Mapping[str, Any]) -> dict[str, Any]:
        table, supplied = params.get("table"), params.get("config", {})
        if not isinstance(table, Mapping) or not isinstance(supplied, Mapping):
            raise ValueError("resmooth 需要 table 和 config 对象。")
        config = _ewb_default_config(); config.update(supplied)
        result = _ewb_apply_additional_smoothing_round(dict(table), config)
        return {key: value.tolist() if hasattr(value, "tolist") else value for key, value in result.items()}


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
