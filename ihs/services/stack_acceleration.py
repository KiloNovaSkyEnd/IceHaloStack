"""CPU/CUDA reduction backends for the UI-independent stack service."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import shutil
import sys
import tempfile
from typing import Any

from ..dependencies import _deps, detect_cuda_backend


@dataclass(frozen=True)
class StackBackendInfo:
    requested: str
    selected: str
    available: bool
    description: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "requested": self.requested,
            "selected": self.selected,
            "gpu_available": self.available,
            "description": self.description,
        }


def normalize_backend(value: str | None) -> str:
    normalized = str(value or "auto").strip().lower()
    aliases = {
        "自动": "auto", "auto": "auto",
        "cpu": "cpu",
        "gpu": "gpu", "cuda": "gpu", "nvidia cuda": "gpu",
    }
    if normalized not in aliases:
        raise ValueError(f"不支持的计算后端：{value!r}。")
    return aliases[normalized]


@lru_cache(maxsize=1)
def probe_cuda() -> tuple[bool, str, Any | None]:
    """Probe and execute a small CUDA reduction before advertising support."""
    available, description, cp = detect_cuda_backend()
    if not available or cp is None:
        return False, description, None
    try:
        # PyInstaller relocates CuPy's bundled headers. Add that runtime path
        # explicitly so NVRTC kernels do not retain the build-machine path.
        from cupy.cuda import compiler
        package_root = Path(getattr(sys, "_MEIPASS", Path(cp.__file__).resolve().parent.parent))
        packaged_include = package_root / "cupy" / "_core" / "include"
        packaged_cuda_include = package_root / "cuda" / "include"
        # NVRTC 11.x cannot reliably resolve non-ASCII Windows paths. Stage
        # headers once under the ASCII temp root before compiling kernels.
        include_dir = Path(tempfile.gettempdir()) / f"IceHaloStack-CuPy-{cp.__version__}"
        if not (include_dir / "cupy" / "complex.cuh").is_file():
            shutil.copytree(packaged_include, include_dir, dirs_exist_ok=True)
        cuda_include_dir = include_dir / "cuda_include"
        if packaged_cuda_include.is_dir() and not (cuda_include_dir / "cuda_fp16.h").is_file():
            shutil.copytree(packaged_cuda_include, cuda_include_dir, dirs_exist_ok=True)
        previous_include_options = compiler._get_extra_include_dir_opts
        compiler._get_extra_include_dir_opts = lambda: tuple(previous_include_options()) + tuple(
            f"-I{path}" for path in (include_dir, cuda_include_dir) if path.is_dir()
        )
        sample = cp.arange(48, dtype=cp.float32).reshape(4, 4, 3)
        result = float(cp.mean(sample).get())
        cp.cuda.Stream.null.synchronize()
        if abs(result - 23.5) > 1e-5:
            raise RuntimeError("CUDA 自检结果不正确")
        return True, description + " · 自检通过", cp
    except Exception as exc:
        return False, f"{description} · CUDA 自检失败：{exc}", None


def inspect_backends(refresh: bool = False) -> dict[str, Any]:
    if refresh:
        probe_cuda.cache_clear()
    available, description, _ = probe_cuda()
    return {
        "cpu": {"available": True, "description": "NumPy float32 累加 / SIMD"},
        "gpu": {"available": available, "description": description},
        "automatic_selection": "gpu" if available else "cpu",
    }


def select_backend(requested: str | None) -> tuple[StackBackendInfo, Any | None]:
    choice = normalize_backend(requested)
    if choice == "cpu":
        return StackBackendInfo(choice, "cpu", True, "NumPy float32 累加 / SIMD"), None
    available, description, cp = probe_cuda()
    if available:
        return StackBackendInfo(choice, "gpu", True, description), cp
    suffix = "；已自动回退 CPU" if choice == "gpu" else "；自动选择 CPU"
    return StackBackendInfo(choice, "cpu", False, description + suffix), None


class StackAccumulator:
    """One-group reducer that keeps only a sum/maximum working image."""

    def __init__(self, method: str, backend: StackBackendInfo, cupy_module=None):
        self.method = method
        self.backend = backend
        self.cp = cupy_module
        self.value = None
        self.count = 0

    def add(self, image) -> None:
        np, *_ = _deps()
        self.count += 1
        if self.backend.selected == "gpu":
            incoming = self.cp.asarray(image, dtype=self.cp.float32)
            if self.value is None:
                self.value = incoming.copy()
            elif self.method == "maximum":
                self.cp.maximum(self.value, incoming, out=self.value)
            else:
                self.cp.add(self.value, incoming, out=self.value)
            return

        incoming = np.asarray(image, dtype=np.float32)
        if self.value is None:
            self.value = incoming.copy()
        elif self.method == "maximum":
            np.maximum(self.value, incoming, out=self.value)
        else:
            np.add(self.value, incoming, out=self.value)

    def finish(self):
        np, *_ = _deps()
        if self.value is None or self.count < 1:
            raise ValueError("堆栈分组没有可用帧。")
        if self.backend.selected == "gpu":
            if self.method == "mean":
                self.value /= float(self.count)
            self.cp.cuda.Stream.null.synchronize()
            return self.cp.asnumpy(self.value).astype(np.float32, copy=False)
        if self.method == "mean":
            self.value /= float(self.count)
        return self.value.astype(np.float32, copy=False)
