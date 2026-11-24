# Chloe GLB with PyQt6 QWebEngineView

This isolated proof of concept checks Three.js inside a real PyQt6 desktop window. It does not change the JARVIS UI, its QPainter HUD, or project dependencies.

## Requirements

- Windows with Python 3.10 or newer and Node.js/npm.
- The original `chloe_detroit_become_human.glb` at the project root.
- Network access only to create the temporary Python environment and download npm packages. Runtime model, Three.js bundle, and viewer page are served from this machine; external requests are blocked.

The tested combination was Python 3.13.17, PyQt6/Qt 6.12.0, PyQt6-WebEngine 6.140.1, and PyQt6-WebEngine-Qt6 6.140.0. Keep WebEngine in its own virtual environment; do not add it to the project's primary environment for this PoC.

## Build and run

From the repository root in PowerShell:

```powershell
$pocVenv = Join-Path $env:TEMP 'jarvis-chloe-qwebengine-poc\venv'
py -3.13 -m venv (Split-Path $pocVenv)
& (Join-Path $pocVenv 'Scripts\python.exe') -m pip install 'PyQt6==6.12.0' 'PyQt6-WebEngine==6.140.1'
npm --prefix tools/chloe_qwebengine_poc ci
npm --prefix tools/chloe_qwebengine_poc run build
& (Join-Path $pocVenv 'Scripts\python.exe') tools/chloe_qwebengine_poc/run_poc.py --mode window --self-test
& (Join-Path $pocVenv 'Scripts\python.exe') tools/chloe_qwebengine_poc/run_poc.py --mode layout --self-test
```

`window` checks the independent viewer. `layout` reproduces the JARVIS side columns, the 1180×760 default window, the 960×640 minimum, the central HUD stack, and a content panel below it. Its stack switches between the actual `HudCanvas` imported from `ui.py` and `QWebEngineView`; the app source itself is not modified. Each mode writes a PNG and a JSON diagnostic report beside this README.

## Captured checks

- WebGL 2 context, GLB materials/textures, 11 meshes, 11 skinned meshes, 66 bones, and the 16.63-second `idle` animation.
- Resizing, the QPainter/WebEngine page switch, minimize/restore, frame resumption, close, JS/Qt/WebGL diagnostics, and non-local request blocking.
- The layout test captures the WebEngine page selected in the HUD slot after restore. Its screenshot is a visual check of the rendered model, while the JSON records animation frames and model structure.

Screenshots and reports are generated artifacts and may be replaced by rerunning the PoC.
