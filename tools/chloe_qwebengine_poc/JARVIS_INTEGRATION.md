# JARVIS Chloe 3D integration

## Optional installation

The normal JARVIS installation remains unchanged. The optional Python bindings are imported with `ui.py` so Qt WebEngine is initialized before `QApplication`; the `QWebEngineView`, profile, local server, and Chromium renderer are created only when the user selects Chloe. Without the optional package, the existing QPainter HUD stays active.

```powershell
.venv\Scripts\python.exe -m pip install -r requirements-chloe3d.txt
```

The validated Windows environment is Python 3.13.17, PyQt6/Qt 6.12.0, PyQt6-WebEngine 6.140.1, and PyQt6-WebEngine-Qt6 6.140.0. The WebEngine Qt wheel is a 132.7 MB download. The optional file requires PyQt6 6.12 or newer and pins the WebEngine bindings/runtime pair. Run `python -m pip check` after installation if the environment contains other Qt packages.

Three.js 0.187.0, GLTFLoader, the viewer HTML, and the original GLB are local files. The viewer page is served on a random loopback port, and its WebEngine request interceptor blocks other network destinations.

## Frozen application packaging

The repository has no PyInstaller `.spec` file, so a packaged build has not been validated here. A production spec/build must include these application assets:

- `tools/chloe_qwebengine_poc/index.html`
- `tools/chloe_qwebengine_poc/vendor/chloe-viewer.bundle.js`
- `chloe_detroit_become_human.glb`

It must also deploy the Qt WebEngine runtime that comes with the WebEngine Qt wheel: the Qt WebEngine libraries, `QtWebEngineProcess.exe`, Chromium resource `.pak` files, ICU data, V8 snapshot, and `qtwebengine_locales`. Use the PyInstaller Qt hooks for the installed PyQt6/WebEngine versions, inspect the build output for those files, and run this same main-window smoke test from the frozen build. Qt documents these helper/runtime requirements in [Deploying Qt WebEngine Applications](https://doc.qt.io/qt-6/qtwebengine-deploying.html).

On Windows, the Qt deployment tools can also be used to inspect/copy Qt runtime components before freezing. PyInstaller collection options and hooks vary by PyInstaller version; this repository does not assume a command line that has not been validated against a real packaged build.

## Licensing

PyQt6-WebEngine is available under GPL v3 or a Riverbank commercial licence. Review that choice for the way JARVIS is distributed; see [Riverbank's PyQtWebEngine licence information](https://www.riverbankcomputing.com/software/pyqtwebengine/download).

## Main-window validation

From the repository root, run:

```powershell
.venv\Scripts\python.exe tools/chloe_qwebengine_poc/main_ui_smoke.py
```

The smoke test opens the real `ui.MainWindow`, selects Chloe with the existing HUD button, checks the actual GLB/WebGL/idle status, exercises the shared HUD/camera/video stack, resizes and minimizes/restores the window, dispatches a local chat input callback, and injects failure signals to verify the QPainter fallback. It does not start a Gemini session or capture audio.
