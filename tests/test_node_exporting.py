from pathlib import Path
import shutil

from ihs.services.node_exporting import NodeWorkflowExportService, NodeWorkflowPreviewService


def test_native_node_export_runs_multiple_flows(tmp_path, reference_image):
    inputs = []
    for index in range(3):
        path = tmp_path / f"input_{index}.png"
        shutil.copyfile(reference_image, path)
        inputs.append(str(path))

    result = NodeWorkflowExportService().save({
        "input_paths": inputs,
        "groups": [[0, 1], [1, 2]],
        "method": "mean",
        "backend": "cpu",
        "output_directory": str(tmp_path / "out"),
        "flows": [
            {"name": "素材 USM", "config": {"usm": False}, "save_sequence": True},
            {"name": "素材 通道", "config": {"channel": False}, "save_sequence": True},
        ],
    })

    assert result["flows"] == 2
    assert result["groups"] == 2
    assert result["backend"]["selected"] == "cpu"
    assert len(result["output_paths"]) == 4
    assert all(Path(path).is_file() for path in result["output_paths"])


def test_native_node_preview_writes_bounded_png(tmp_path, reference_image):
    output = tmp_path / "preview.png"
    result = NodeWorkflowPreviewService().save({
        "input_paths": [reference_image], "group": [0], "method": "mean", "backend": "cpu",
        "config": {"stretch": False, "basic": False}, "output_path": str(output), "max_side": 64,
    })
    assert output.is_file()
    assert result["backend"]["selected"] == "cpu"
