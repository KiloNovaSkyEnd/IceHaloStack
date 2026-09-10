# IceHaloStack v0.9.6.8c WinUI 3 front-end

This is the native C# front-end for the canonical Python image engine. It contains three service-backed pages:

- a single-image page that calls `process_file` with the shared processing pipeline;
- a stacking page that collects multiple image paths, displays an explicit
  input queue and output-group queue, selects `mean` or `maximum`, and calls
  `stack_files`.
- a timelapse-sequence page that reuses the same queue/grouping model, applies
  the processing pipeline, exports TIFF masters, and can stream final frames
  directly to FFmpeg for MP4, MOV, ProRes, or GIF output.

The first batch on the stacking page becomes an explicit “all images → one
master” group. Additional checked inputs can form more groups, and each group
chooses its own TIFF 32-bit Float output. The UI sends the visual queue as
`input_paths`, zero-based `groups`, and `output_paths`; no image algorithm is
duplicated in C#.

The native node workspace retains the established three-column operation flow.
Remaining keyframe and storage pages are migrated behind shared service
contracts instead of copying Tk state or image algorithms into WinUI. The
default package no longer duplicates the Classic Python runtime.

## Development launch

From the source root, set the interpreter that has the IceHaloStack runtime
dependencies, then run the project:

```powershell
$env:ICEHALOSTACK_PYTHON = "C:\path\to\python.exe"
dotnet run --project .\winui\IceHaloStack.WinUI\IceHaloStack.WinUI.csproj --arch x64
```

The app walks upward from its build directory to locate `ihs/services/ipc.py`.
If the engine lives elsewhere, set `ICEHALOSTACK_ENGINE_ROOT` to the source
root. Release packaging will replace this source resolver with a bundled Python
engine worker; the page and `IpcClient` contract stay unchanged.

The project references `../IceHaloStack.WinUI.Client`, which owns all
JSON-lines process communication, task-ID cancellation, and bindable task
progress. Stack progress is phase-local (`decode`, `stack`, `export`), so the
page displays the current phase and progress instead of presenting a misleading
single global percentage.

## UI performance diagnostics

Set `ICEHALOSTACK_SHOW_PERF=1` before launch to show a non-interactive overlay
with FPS, average frame time, P95 frame time, and frames slower than 50 ms.
Release QA can set `ICEHALOSTACK_PERF_SMOKE_PATH` to a JSON output path; the app
then measures cold and cached navigation for the stack and timelapse pages,
writes the report, and exits. Page lists remain inside finite viewports with
explicit `ItemsStackPanel` virtualization, and heavyweight editors use deferred
XAML loading.
