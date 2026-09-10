from __future__ import annotations

from ihs.services.native_workspaces import (
    ExposureSmoothingService,
    NodeWorkflowService,
    StorageInspectionService,
)


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


def test_storage_service_inspects_selected_paths(tmp_path):
    item = tmp_path / "data.bin"
    item.write_bytes(b"12345")
    result = StorageInspectionService().inspect([item])
    assert result["total_bytes"] == 5
    assert result["entries"][0]["files"] == 1
