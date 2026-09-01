IceHaloStack v0.9.4.7 Color Emboss

Changes in v0.9.4.7:
- Color Emboss is now the default and preserves the original RGB/chroma in flat areas.
- Gray Emboss remains available for a classic neutral-gray Photoshop-like emboss body.
- Emboss adds Normal / Overlay / Soft Light / Linear Light blend modes and 0–100% opacity.
- Standalone editor, timelapse processing and node workflows share the same Emboss implementation.

=====================================

This version intentionally keeps the v0.9.4 processing baseline.
Changes since v0.9.4.1 are environment/launcher improvements only.

Recommended Windows Python
--------------------------
- Python 3.14 64-bit (preferred)
- Python 3.13 64-bit
- Python 3.12 64-bit

Normal use
----------
1. Install a supported 64-bit Python on Windows.
2. Extract this ZIP.
3. Double-click launch_IceHaloStack.bat.

The Smart Launcher will:
- locate a supported Python automatically (prefers 3.14, then 3.13, then 3.12),
- create a private virtual environment under LOCALAPPDATA,
- repair pip with ensurepip if required,
- install missing runtime dependencies,
- verify Python, NumPy, Pillow, tifffile, rawpy/LibRaw, OpenCV, Tkinter and FFmpeg,
- launch IceHaloStack.

The private runtime is stored at:
  %LOCALAPPDATA%\IceHaloStackRuntime0942\venv

This avoids placing thousands of Python files in a deep project path.

Diagnostics
-----------
Run:
  check_environment.bat

to print versions and verify the current private environment.

If the private environment becomes corrupted, run:
  repair_environment.bat

It removes/rebuilds ONLY IceHaloStack's private venv.

Standalone EXE
--------------
Run:
  build_release.bat

The separate build environment is stored at:
  %LOCALAPPDATA%\IceHaloStackBuild0942\venv

Successful builds appear under:
  dist\IceHaloStack\IceHaloStack.exe

For a console-enabled diagnostic build, run:
  build_debug_console.bat

Publishing an onedir build
---------------------------
Copy the entire:
  dist\IceHaloStack\
folder. Do not copy only IceHaloStack.exe because _internal contains the bundled Python runtime and native libraries.


v0.9.4.3 Global Mouse Wheel: all editor tabs, the full timelapse left control column, node settings, and Flow/Base Curves are vertically scrollable. Node canvas: wheel=vertical, Shift+wheel=horizontal, Ctrl+wheel=zoom.