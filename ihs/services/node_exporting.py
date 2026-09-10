"""UI-independent multi-flow node workflow export."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from pathlib import Path

from .contracts import ExportRequest, PipelineRequest, PreviewRequest, StackRequest, VideoExportRequest
from .exporting import ExportService
from .ewb_processing import prepare_ewb_frames
from .processing import ImageProcessingService
from .stacking import StackService
from .video_exporting import VideoExportService


def _safe_name(value: object, fallback: str) -> str:
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "").strip()).rstrip(". ")
    return clean or fallback


class NodeWorkflowExportService:
    def __init__(self, *, progress=None, cancellation=None):
        self.progress = progress
        self.cancellation = cancellation

    def save(self, params: Mapping[str, object]) -> dict[str, object]:
        inputs = params.get("input_paths")
        groups = params.get("groups")
        flows = params.get("flows")
        if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)) or not inputs:
            raise ValueError("节点工作流需要输入图像。")
        if not isinstance(groups, Sequence) or isinstance(groups, (str, bytes)) or not groups:
            raise ValueError("节点工作流需要至少一个堆栈分组。")
        if not isinstance(flows, Sequence) or isinstance(flows, (str, bytes)) or not flows:
            raise ValueError("节点工作流需要至少一个启用流程。")
        output = Path(str(params.get("output_directory", ""))).expanduser().resolve()
        output.mkdir(parents=True, exist_ok=True)

        processor = ImageProcessingService(progress=self.progress, cancellation=self.cancellation)
        decoded = [processor.load(path) for path in inputs]
        decoded = prepare_ewb_frames(decoded, params.get("ewb"), progress=self.progress, cancellation=self.cancellation)
        stacker = StackService(progress=self.progress, cancellation=self.cancellation)
        exporter = ExportService(progress=self.progress, cancellation=self.cancellation)
        enabled = [flow for flow in flows if isinstance(flow, Mapping) and flow.get("enabled", True)]
        if not enabled:
            raise ValueError("没有启用的节点流程。")

        video_frames: list[list[object]] = [[] for _ in enabled]
        saved: list[str] = []
        masters = stacker.iter_masters(
            StackRequest(groups, str(params.get("method", "mean")), backend=str(params.get("backend", "auto"))),
            lambda index: decoded[int(index)],
        )
        for group_number, master in enumerate(masters, 1):
            for flow_index, flow in enumerate(enabled):
                config = flow.get("config", {})
                curves = flow.get("curve_points")
                if not isinstance(config, Mapping):
                    raise ValueError("流程 config 必须是对象。")
                image = processor.process(PipelineRequest(master, config, curves))
                flow_name = _safe_name(flow.get("name"), f"流程_{flow_index + 1:02d}")
                flow_root = output / flow_name
                if flow.get("save_sequence", True):
                    sequence = flow_root / "sequence"
                    path = sequence / f"{flow_name}_{group_number:06d}.tif"
                    saved.append(str(exporter.save(ExportRequest(path, image, "TIFF 32-bit Float"))))
                if flow.get("save_video", False):
                    video_frames[flow_index].append(image)

        videos: list[str] = []
        for flow_index, flow in enumerate(enabled):
            if not flow.get("save_video", False):
                continue
            flow_name = _safe_name(flow.get("name"), f"流程_{flow_index + 1:02d}")
            video_format = str(flow.get("video_format", "MP4 H.264"))
            suffix = ".mov" if video_format.startswith("MOV") else ".gif" if video_format == "GIF" else ".mp4"
            path = output / flow_name / f"{flow_name}{suffix}"
            videos.append(str(VideoExportService(progress=self.progress, cancellation=self.cancellation).save(
                VideoExportRequest(path, video_frames[flow_index], video_format, float(flow.get("fps", 24.0)))
            )))
        return {
            "output_directory": str(output), "output_paths": saved, "video_paths": videos,
            "flows": len(enabled), "groups": len(groups), "backend": stacker.backend_info.to_dict(),
        }


class NodeWorkflowPreviewService:
    def __init__(self, *, progress=None, cancellation=None):
        self.progress = progress
        self.cancellation = cancellation

    def save(self, params: Mapping[str, object]) -> dict[str, object]:
        inputs = params.get("input_paths")
        group = params.get("group")
        config = params.get("config", {})
        if not isinstance(inputs, Sequence) or isinstance(inputs, (str, bytes)) or not inputs:
            raise ValueError("预览需要输入图像。")
        if not isinstance(group, Sequence) or isinstance(group, (str, bytes)) or not group:
            raise ValueError("预览需要一个堆栈分组。")
        if not isinstance(config, Mapping):
            raise ValueError("预览 config 必须是对象。")
        processor = ImageProcessingService(progress=self.progress, cancellation=self.cancellation)
        decoded = [processor.load(path) for path in inputs]
        decoded = prepare_ewb_frames(decoded, params.get("ewb"), progress=self.progress, cancellation=self.cancellation)
        stacker = StackService(progress=self.progress, cancellation=self.cancellation)
        master = next(stacker.iter_masters(
            StackRequest([group], str(params.get("method", "mean")), backend=str(params.get("backend", "auto"))),
            lambda index: decoded[int(index)],
        ))
        image, scale = processor.preview(PreviewRequest(
            master, config, params.get("curve_points"), max_side=int(params.get("max_side", 1200))
        ))
        path = ExportService(progress=self.progress, cancellation=self.cancellation).save(
            ExportRequest(str(params.get("output_path", "")), image, "PNG 8-bit", "Fast")
        )
        return {"output_path": str(path), "scale": scale, "backend": stacker.backend_info.to_dict()}
