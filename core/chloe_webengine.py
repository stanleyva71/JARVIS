"""Optional Three.js Chloe page backed by a local-only Qt WebEngine profile."""

from __future__ import annotations

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from PyQt6.QtCore import QTimer, QUrl, pyqtSignal
from PyQt6.QtWidgets import QVBoxLayout, QSizePolicy, QWidget

try:
    from PyQt6.QtWebEngineCore import (
        QWebEnginePage,
        QWebEngineProfile,
        QWebEngineSettings,
        QWebEngineUrlRequestInterceptor,
    )
    from PyQt6.QtWebEngineWidgets import QWebEngineView
    HAVE_WEBENGINE = True
    WEBENGINE_IMPORT_ERROR = ""
except Exception as exc:  # pragma: no cover - exercised in an environment without WebEngine
    QWebEnginePage = QWebEngineProfile = QWebEngineSettings = None
    QWebEngineUrlRequestInterceptor = QWebEngineView = None
    HAVE_WEBENGINE = False
    WEBENGINE_IMPORT_ERROR = str(exc)


class ChloePage(QWidget):
    """A lazy 3D page designed to be added to JARVIS's existing HUD stack."""

    status_changed = pyqtSignal(bool, str)

    def __init__(self, model_path: Path, base_dir: Path, parent=None):
        super().__init__(parent)
        self.failure = ""
        self.available = False
        self._started = False
        self._closed = False
        self._ready_emitted = False
        self.html_loaded = False
        self._last_frame_count: int | None = None
        self._stalled_polls = 0
        self._server: ThreadingHTTPServer | None = None
        self._server_thread: threading.Thread | None = None
        self._profile = None
        self._page = None
        self._asset_paths = self._resolve_assets(model_path, base_dir)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(300)
        self._poll_timer.timeout.connect(self._poll_model)
        self._load_timeout = QTimer(self)
        self._load_timeout.setSingleShot(True)
        self._load_timeout.timeout.connect(
            lambda: self._fail("Tempo limite ao carregar a Chloe 3D no WebEngine.")
        )

        if not HAVE_WEBENGINE:
            self.failure = (
                "PyQt6-WebEngine indisponível: "
                f"{WEBENGINE_IMPORT_ERROR or 'módulo ausente'}"
            )
            return

        missing = [str(path) for path in self._asset_paths.values() if not path.is_file()]
        if missing:
            self.failure = "Arquivos locais da Chloe ausentes: " + ", ".join(missing)
            return

        try:
            self._start_asset_server()
            self.viewport = QWebEngineView(self)
            self.viewport.setObjectName("chloeThreeJsView")
            self.viewport.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
            )
            # A private profile isolates this local viewer from browser state and
            # gives its request interceptor a strict loopback-only allowlist.
            self._profile = QWebEngineProfile(self)
            self._request_filter = _LocalRequestFilter(
                self._profile, self._server.server_port
            )
            self._profile.setUrlRequestInterceptor(self._request_filter)
            self._page = _DiagnosticPage(self._profile, self)
            self._page.loadFinished.connect(self._on_load_finished)
            self._page.renderProcessTerminated.connect(self._on_renderer_terminated)
            self.viewport.setPage(self._page)
            settings = self._page.settings()
            settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False
            )
            layout.addWidget(self.viewport, stretch=1)
            self.available = True
        except Exception as exc:  # A rendering feature must not stop the main window.
            self.failure = f"Falha ao inicializar QWebEngineView: {exc}"
            self.shutdown()

    @staticmethod
    def _resolve_assets(model_path: Path, base_dir: Path) -> dict[str, Path]:
        roots = [base_dir]
        extracted = getattr(sys, "_MEIPASS", None)
        if extracted:
            roots.append(Path(extracted))
        for root in roots:
            viewer = root / "tools" / "chloe_qwebengine_poc"
            candidate = {
                "index": viewer / "index.html",
                "bundle": viewer / "vendor" / "chloe-viewer.bundle.js",
                "model": root / model_path.name,
            }
            if all(path.is_file() for path in candidate.values()):
                return candidate
        return {
            "index": base_dir / "tools" / "chloe_qwebengine_poc" / "index.html",
            "bundle": base_dir / "tools" / "chloe_qwebengine_poc" / "vendor" / "chloe-viewer.bundle.js",
            "model": model_path,
        }

    def _start_asset_server(self) -> None:
        assets = self._asset_paths

        class ChloeAssetHandler(BaseHTTPRequestHandler):
            routes = {
                "/": (assets["index"], "text/html; charset=utf-8"),
                "/index.html": (assets["index"], "text/html; charset=utf-8"),
                "/viewer.bundle.js": (assets["bundle"], "text/javascript; charset=utf-8"),
                "/chloe.glb": (assets["model"], "model/gltf-binary"),
            }

            def do_GET(self):
                route_path = urlsplit(self.path).path
                if route_path == "/favicon.ico":
                    self.send_response(204)
                    self.end_headers()
                    return
                route = self.routes.get(route_path)
                if route is None:
                    self.send_error(404, "Asset not found")
                    return
                path, content_type = route
                try:
                    payload = path.read_bytes()
                except OSError:
                    self.send_error(404, "Asset not found")
                    return
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                try:
                    self.wfile.write(payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *_args):
                return

        self._server = ThreadingHTTPServer(("127.0.0.1", 0), ChloeAssetHandler)
        self._server.daemon_threads = True
        self._server_thread = threading.Thread(
            target=self._server.serve_forever,
            name="jarvis-chloe-assets",
            daemon=True,
        )
        self._server_thread.start()

    def start(self) -> None:
        if not self.available or self._started:
            return
        self._started = True
        self._load_timeout.start(45_000)
        self._poll_timer.start()
        self.viewport.setUrl(QUrl(f"http://127.0.0.1:{self._server.server_port}/?hud=1"))

    def _on_load_finished(self, ok: bool) -> None:
        self.html_loaded = bool(ok)
        if not ok:
            self._fail("O HTML local do viewer não carregou no QWebEngineView.")

    def _on_javascript_console(self, level, message: str) -> None:
        if "Error" in getattr(level, "name", str(level)):
            self._fail(f"Erro JavaScript/WebGL: {message}")

    def _on_renderer_terminated(self, status, exit_code: int) -> None:
        status_name = getattr(status, "name", str(status))
        self._fail(
            f"Processo de renderização Chromium encerrado ({status_name}, código {exit_code})."
        )

    def _poll_model(self) -> None:
        if self._closed or self.failure or self._page is None:
            return
        script = """(() => {
          const s = window.__chloeStatus;
          if (!s) return JSON.stringify({present:false, jsErrors:window.__chloeJsErrors||[]});
          return JSON.stringify({present:true, ...s});
        })()"""
        self._page.runJavaScript(script, self._handle_model_status)

    def _handle_model_status(self, value) -> None:
        if self._closed or self.failure:
            return
        try:
            status = json.loads(value) if isinstance(value, str) else value
        except (TypeError, ValueError):
            return
        if not isinstance(status, dict):
            return
        js_errors = status.get("jsErrors") or []
        if js_errors:
            self._fail("JavaScript da Chloe reportou erro: " + str(js_errors[0]))
            return
        if status.get("loaded") is False:
            self._fail(
                "Falha ao carregar o GLB: "
                + str(status.get("error") or "erro não especificado")
            )
            return
        if not status.get("loaded"):
            return

        webgl_version = str((status.get("webgl") or {}).get("version", ""))
        if not webgl_version.lower().startswith("webgl"):
            self._fail("WebGL não está disponível neste QWebEngineView.")
            return
        if status.get("webglContext") == "lost":
            self._fail("O contexto WebGL da Chloe foi perdido.")
            return
        gl_errors = status.get("webglErrors") or []
        if gl_errors:
            self._fail("Erro WebGL ao renderizar a Chloe: " + str(gl_errors[0]))
            return
        clips = status.get("clips") or []
        if not any(str(clip.get("name", "")).lower() == "idle" for clip in clips):
            self._fail("O GLB carregou sem a animação idle esperada.")
            return

        frames = int(status.get("frames", 0) or 0)
        if frames <= 0:
            return
        window = self.window()
        page_visible = self.isVisible() and not window.isMinimized()
        if self._last_frame_count is not None and page_visible:
            self._stalled_polls = self._stalled_polls + 1 if frames <= self._last_frame_count else 0
            if self._stalled_polls >= 10:
                self._fail("A animação da Chloe parou enquanto o viewport estava visível.")
                return
        self._last_frame_count = frames
        if not self._ready_emitted:
            self._ready_emitted = True
            self._load_timeout.stop()
            self.status_changed.emit(True, "")

    def _fail(self, error: str) -> None:
        if self._closed or self.failure:
            return
        self.failure = error
        self._poll_timer.stop()
        self._load_timeout.stop()
        self.status_changed.emit(False, error)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._poll_timer.stop()
        self._load_timeout.stop()
        viewport = getattr(self, "viewport", None)
        if viewport is not None:
            viewport.stop()
            viewport.setUrl(QUrl("about:blank"))
        if self._server is not None:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception:
                pass
            self._server = None

    def closeEvent(self, event):
        self.shutdown()
        super().closeEvent(event)


if HAVE_WEBENGINE:
    class _DiagnosticPage(QWebEnginePage):
        def __init__(self, profile, owner):
            super().__init__(profile, owner)
            self._owner = owner

        def javaScriptConsoleMessage(self, level, message, line_number, source_id):
            self._owner._on_javascript_console(level, str(message))


    class _LocalRequestFilter(QWebEngineUrlRequestInterceptor):
        def __init__(self, parent, port: int):
            super().__init__(parent)
            self._port = int(port)
            self.local_requests: list[str] = []
            self.blocked_requests: list[str] = []

        def interceptRequest(self, info):
            url = info.requestUrl()
            if url.scheme() in ("data", "blob"):
                return
            if (url.scheme() == "http" and url.host() == "127.0.0.1"
                    and url.port() == self._port):
                self.local_requests.append(url.toString())
                return
            self.blocked_requests.append(url.toString())
            info.block(True)
else:  # Keep importing the app possible when WebEngine is not installed.
    _DiagnosticPage = _LocalRequestFilter = None

