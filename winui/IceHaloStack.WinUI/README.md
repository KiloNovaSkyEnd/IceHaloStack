# IceHaloStack WinUI 3 shell

This is the first runnable C# front-end for the existing Python image engine.
It currently contains three migration pages:

- a single-image page that calls `process_file` with a PNG output path;
- a stacking page that collects multiple image paths, displays an explicit
  input queue and output-group queue, selects `mean` or `maximum`, and calls
  `stack_files`.
- a timelapse-sequence page that reuses the same queue/grouping model, defaults
  to a sliding time window, and exports one TIFF master per group through the
  same `stack_files` task.

The first batch on the stacking page becomes an explicit “all images → one
master” group. Additional checked inputs can form more groups, and each group
chooses its own TIFF 32-bit Float output. The UI sends the visual queue as
`input_paths`, zero-based `groups`, and `output_paths`; no image algorithm is
duplicated in C#.

The timelapse page is intentionally limited to the first useful migration
slice: grouped master TIFF sequence export. The legacy reference preview,
processing-chain settings, asynchronous encoder, and final video export need
their own engine/IPC contracts and are not represented as completed WinUI
features yet.

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
