from __future__ import annotations

from ihs.services.native_workspaces import (
    ExposureSmoothingService,
    NodeWorkflowService,
    StorageInspectionService,
)
from ihs.image_io import save_tiff
import numpy as np


def test_node_workflow_service_reports_execution_order():
    result = NodeWorkflowService().inspect({
        "cfg": {"stretch": True, "basic": False},
        "present_nodes": ["stack", "stretch", "basic", "output"],
        "edges": [["stack", "stretch"], ["stretch", "basic"], ["basic", "output"]],
    })
    assert result["execution_order"] == ["stretch", "basic"]
    assert result["enabled_nodes"] == ["stretch"]


def test_exposure_service_builds_json_table():
    result = ExposureSmoothingService().build({
        "exposure_metric": [0.0, 0.1, -0.1],
        "rlog_metric": [0.0, 0.0, 0.0],
        "blog_metric": [0.0, 0.0, 0.0],
        "config": {"exposure_enabled": True},
    })
    assert len(result["ev_correction"]) == 3


def test_exposure_service_analyzes_frames_and_renders_preview(tmp_path):
    image = np.full((24, 32, 3), 0.2, dtype=np.float32)
    image[..., 0] *= 1.1
    paths = [tmp_path / "a.tif", tmp_path / "b.tif"]
    save_tiff(paths[0], image, float32=True)
    save_tiff(paths[1], image * 1.2, float32=True)
    service = ExposureSmoothingService()
    table = service.analyze({
        "input_paths": [str(path) for path in paths],
        "config": {"exposure_enabled": True, "anchors": [{"frame": 1, "exposure": 0.2}]},
    })
    assert table["count"] == 2
    assert table["file_names"] == ["a.tif", "b.tif"]
    target = tmp_path / "preview.png"
    result = service.preview({
        "input_path": str(paths[0]), "output_path": str(target),
        "frame_index": 0, "table": table,
    })
    assert result["frame_index"] == 0
    assert target.is_file()
    smoother = service.resmooth({"table": table, "config": {"exposure_enabled": True}})
    assert smoother["additional_smoothing_rounds"] == 1


def test_storage_service_inspects_selected_paths(tmp_path):
    item = tmp_path / "data.bin"
    item.write_bytes(b"12345")
    result = StorageInspectionService().inspect([item])
    assert result["total_bytes"] == 5
    assert result["entries"][0]["files"] == 1
