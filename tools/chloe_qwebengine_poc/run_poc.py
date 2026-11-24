from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
POC = Path(__file__).resolve().parent
APP_SITE_PACKAGES = ROOT / ".venv" / "Lib" / "site-packages"
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if APP_SITE_PACKAGES.is_dir() and str(APP_SITE_PACKAGES) not in sys.path:
    sys.path.append(str(APP_SITE_PACKAGES))

os.environ.setdefault("QT_LOGGING_RULES", "qt.multimedia.*=false")

from PyQt6.QtCore import QTimer, Qt, QUrl  # noqa: E402
from PyQt6.QtGui import QColor, QFont  # noqa: E402
from PyQt6.QtWebEngineCore import (  # noqa: E402
    QWebEnginePage,
    QWebEngineProfile,
    QWebEngineSettings,
    QWebEngineUrlRequestInterceptor,
)
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import (  # noqa: E402
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ui import HudCanvas  # noqa: E402


QT_MESSAGES: list[dict] = []


def _qt_message_handler(mode, context, message):
    name = getattr(mode, "name", str(mode))
    entry = {"level": name, "message": str(message)}
    QT_MESSAGES.append(entry)
    if "Warning" in name or "Critical" in name or "Fatal" in name:
        print(f"[Qt {name}] {message}", flush=True)


def _theme(widget: QWidget, background: str, foreground: str = "#69dce8") -> None:
    widget.setStyleSheet(
        f"background:{background}; color:{foreground};"
        "font-family:'Courier New'; font-size:10px;"
    )


class LocalHandler(BaseHTTPRequestHandler):
    routes = {
        "/": (POC / "index.html", "text/html; charset=utf-8"),
        "/index.html": (POC / "index.html", "text/html; charset=utf-8"),
        "/viewer.bundle.js": (POC / "vendor" / "chloe-viewer.bundle.js", "text/javascript; charset=utf-8"),
        "/chloe.glb": (ROOT / "chloe_detroit_become_human.glb", "model/gltf-binary"),
    }

    def do_GET(self):
        if self.path == "/favicon.ico":
            self.send_response(204)
            self.end_headers()
            return
        route = self.routes.get(self.path.split("?", 1)[0])
        if route is None or not route[0].is_file():
            self.send_error(404, "PoC asset not found")
            return
        file_path, content_type = route
        payload = file_path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)
        print(f"[HTTP] 200 {self.path.split('?', 1)[0]} ({len(payload):,} bytes)", flush=True)

    def log_message(self, *_args):
        return


def start_local_server() -> tuple[ThreadingHTTPServer, str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), LocalHandler)
    thread = threading.Thread(target=server.serve_forever, name="chloe-poc-http", daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}/"


class DiagnosticPage(QWebEnginePage):
    def __init__(self, profile, parent=None):
        super().__init__(profile, parent)
        self.console_messages: list[dict] = []
        self.render_termination: dict | None = None
        self.renderProcessTerminated.connect(self._on_render_terminated)

    def javaScriptConsoleMessage(self, level, message, line_number, source_id):
        level_name = getattr(level, "name", str(level))
        entry = {
            "level": level_name,
            "message": str(message),
            "line": int(line_number),
            "source": str(source_id),
        }
        self.console_messages.append(entry)
        print(f"[JS {level_name}] {source_id}:{line_number} {message}", flush=True)

    def _on_render_terminated(self, status, exit_code):
        self.render_termination = {
            "status": getattr(status, "name", str(status)),
            "exitCode": int(exit_code),
        }
        print(f"[QtWebEngine] renderer terminated: {self.render_termination}", flush=True)


class LocalOnlyInterceptor(QWebEngineUrlRequestInterceptor):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.allowed: list[str] = []
        self.blocked: list[str] = []

    def interceptRequest(self, info):
        url = info.requestUrl()
        if url.scheme() in ("data", "blob"):
            return
        if url.scheme() == "http" and url.host() == "127.0.0.1":
            self.allowed.append(url.toString())
            return
        self.blocked.append(url.toString())
        info.block(True)
        print(f"[Network] blocked non-local request: {url.toString()}", flush=True)


class ChloeTestWindow(QMainWindow):
    def __init__(self, mode: str, self_test: bool):
        super().__init__()
        self.mode = mode
        self.self_test = self_test
        self.report: dict = {
            "mode": mode,
            "python": sys.version,
            "poc": str(POC),
            "localAssetsOnly": True,
            "tests": {},
            "failures": [],
        }
        self._heartbeat_interval = 20.0
        self._heartbeat_samples: list[float] = []
        self._heartbeat_last = time.perf_counter()
        self._test_step = "wait-load"

        self.setWindowTitle(
            "JARVIS HUD slot · Chloe QWebEngine PoC" if mode == "layout"
            else "Chloe GLB · PyQt6 QWebEngineView PoC"
        )
        self.setMinimumSize(960, 640) if mode == "layout" else self.setMinimumSize(640, 480)
        self.resize(1180, 760) if mode == "layout" else self.resize(1080, 760)
        self._load_page()
        self._build_ui()

        self._heartbeat = QTimer(self)
        self._heartbeat.setInterval(20)
        self._heartbeat.timeout.connect(self._record_heartbeat)
        self._heartbeat.start()

        self._test_timeout = QTimer(self)
        self._test_timeout.setSingleShot(True)
        self._test_timeout.timeout.connect(self._test_timed_out)
        if self_test:
            self._test_timeout.start(60_000)
            QTimer.singleShot(200, self._poll_loaded)

    def _build_ui(self):
        central = QWidget(self)
        _theme(central, "#00060a")
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        header = QWidget(central)
        header.setFixedHeight(54 if self.mode == "layout" else 48)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(14, 4, 14, 4)
        _theme(header, "#010d14")
        title = QLabel(
            "J.A.R.V.I.S · HUD SLOT TEST · WEBENGINE / QPAINTER" if self.mode == "layout"
            else "CHLOE · WEBGL RENDERER TEST"
        )
        title.setStyleSheet("color:#69dce8; font:bold 11px 'Courier New'; background:transparent;")
        header_layout.addWidget(title)
        header_layout.addStretch(1)
        self.toggle_button = QPushButton("Alternar QPainter / Chloe 3D")
        self.toggle_button.setMinimumHeight(30)
        self.toggle_button.setVisible(self.mode == "layout")
        if self.mode == "layout":
            self.toggle_button.setText("Mostrar holograma QPainter")
        self.toggle_button.clicked.connect(self._toggle_hud_page)
        header_layout.addWidget(self.toggle_button)
        root_layout.addWidget(header)

        body = QWidget(central)
        body_layout = QHBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(0)
        if self.mode == "layout":
            left = self._side_panel("◈  MONITOR DO SISTEMA", 176)
            right = self._side_panel("◈  LOG DE ATIVIDADE", 320)
            body_layout.addWidget(left)
            center = self._build_hud_center()
            body_layout.addWidget(center, 1)
            body_layout.addWidget(right)
        else:
            body_layout.addWidget(self.web_view, 1)
        root_layout.addWidget(body, 1)

        footer = QLabel(
            "JARVIS HUD area · same 1180×760 default, 960×640 minimum, 176px left / 320px right" if self.mode == "layout"
            else "Standalone viewport · local GLB, local Three.js bundle"
        )
        footer.setFixedHeight(26)
        footer.setContentsMargins(10, 2, 10, 2)
        footer.setStyleSheet("color:#52cbd7;background:#010d14;border-top:1px solid #103744;font:10px 'Courier New';")
        root_layout.addWidget(footer)
        self.setCentralWidget(central)

    def _side_panel(self, heading: str, width: int) -> QWidget:
        panel = QFrame()
        panel.setFixedWidth(width)
        _theme(panel, "#010d14", "#56c7d2")
        panel.setStyleSheet(panel.styleSheet() + "border-right:1px solid #103744;")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 12, 12)
        label = QLabel(heading)
        label.setWordWrap(True)
        label.setStyleSheet("color:#56dce7;font:bold 10px 'Courier New';")
        layout.addWidget(label)
        for text in ("CPU   ━━━━━━━━━", "MEM   ━━━━━━━━━", "REDE  ━━━━━━━━━", "GPU   ━━━━━━━━━"):
            item = QLabel(text)
            item.setStyleSheet("color:#32c3d0;border:1px solid #10404b;border-radius:6px;padding:8px 5px;")
            layout.addWidget(item)
        layout.addStretch(1)
        return panel

    def _build_hud_center(self) -> QWidget:
        center = QWidget()
        _theme(center, "#00060a")
        layout = QVBoxLayout(center)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.hud_stack = QStackedWidget(center)
        self.hud_stack.setObjectName("jarvisHudStackPoC")
        self.hud_stack.setStyleSheet("background:#00060a;border:1px solid #103744;")
        self.hud = HudCanvas(str(ROOT / "face.png"), "J.A.R.V.I.S", self.hud_stack)
        # Use the current QPainter Chloe illustration when present; otherwise
        # keep the original animated face as the software-only HUD fallback.
        self.hud.hud_style = "chloe" if getattr(self.hud, "_chloe", None) is not None else "face"
        self.web_view.setParent(self.hud_stack)
        self.hud_stack.addWidget(self.hud)
        self.hud_stack.addWidget(self.web_view)
        self.hud_stack.setCurrentWidget(self.web_view)

        self.content_mock = QTextEdit(center)
        self.content_mock.setReadOnly(True)
        self.content_mock.setPlainText(
            "CONSOLE / CONTEÚDO DO JARVIS\n"
            "Área abaixo do HUD preservada no teste.\n"
            "O QWebEngineView deve permanecer restrito ao slot do holograma."
        )
        self.content_mock.setMinimumHeight(100)
        self.content_mock.setMaximumHeight(190)
        self.content_mock.setStyleSheet("background:#010d14;color:#4fcbd7;border:1px solid #103744;font:11px 'Courier New';")
        splitter = QSplitter(Qt.Orientation.Vertical, center)
        splitter.addWidget(self.hud_stack)
        splitter.addWidget(self.content_mock)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([470, 170])
        layout.addWidget(splitter, 1)
        self.hud_splitter = splitter
        return center

    def _load_page(self):
        self.web_view = QWebEngineView(self)
        self.web_profile = QWebEngineProfile(self)
        self.request_interceptor = LocalOnlyInterceptor(self.web_profile)
        self.web_profile.setUrlRequestInterceptor(self.request_interceptor)
        self.web_page = DiagnosticPage(self.web_profile, self.web_view)
        self.web_view.setPage(self.web_page)
        settings = self.web_page.settings()
        settings.setAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled, True)
        settings.setAttribute(QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, False)
        self.web_page.loadStarted.connect(lambda: print("[QtWebEngine] loadStarted", flush=True))
        self.web_page.loadProgress.connect(lambda value: print(f"[QtWebEngine] loadProgress={value}", flush=True))
        self.web_page.loadFinished.connect(self._on_load_finished)
        self.report["webengineSettings"] = {
            "WebGLEnabled": settings.testAttribute(QWebEngineSettings.WebAttribute.WebGLEnabled),
            "LocalContentCanAccessRemoteUrls": settings.testAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls
            ),
        }
        self.web_view.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def _load_page_url(self):
        suffix = "?hud=1" if self.mode == "layout" else ""
        self.web_view.setUrl(QUrl(self.page_url + suffix))

    def _toggle_hud_page(self):
        if self.mode != "layout":
            return
        next_index = 1 - self.hud_stack.currentIndex()
        self.hud_stack.setCurrentIndex(next_index)
        self._update_toggle_label()
        page_name = "webengine" if next_index == 1 else "qpainter"
        print(f"[Layout] stack current page={page_name}; slot={self.hud_stack.width()}x{self.hud_stack.height()}", flush=True)

    def _update_toggle_label(self):
        if self.mode != "layout":
            return
        on_webengine = self.hud_stack.currentWidget() is self.web_view
        self.toggle_button.setText("Mostrar holograma QPainter" if on_webengine else "Mostrar Chloe 3D")

    def _on_load_finished(self, ok: bool):
        self.report["loadFinished"] = bool(ok)
        print(f"[QtWebEngine] loadFinished={ok}", flush=True)
        if not ok:
            self.report["failures"].append("QWebEngineView loadFinished(false)")

    def _record_heartbeat(self):
        now = time.perf_counter()
        elapsed_ms = (now - self._heartbeat_last) * 1000.0
        self._heartbeat_samples.append(elapsed_ms)
        self._heartbeat_last = now

    def _poll_loaded(self, attempts: int = 0):
        if not self.self_test:
            return
        if attempts > 120:
            self.report["failures"].append("Timed out waiting for the GLB/WebGL page")
            self._finish_test()
            return
        self.web_page.runJavaScript(
            "JSON.stringify(window.__chloeStatus || null)",
            lambda value: self._on_status_polled(value, attempts),
        )

    def _on_status_polled(self, value, attempts: int):
        try:
            status = json.loads(value) if isinstance(value, str) else value
        except Exception:
            status = None
        if not isinstance(status, dict) or not status.get("loaded"):
            QTimer.singleShot(200, lambda: self._poll_loaded(attempts + 1))
            return
        if self._test_step == "wait-load":
            self._test_step = "settle"
            self.report["initialModelStatus"] = status
            # Measure UI responsiveness after network/GLB initialization.
            self._heartbeat_samples.clear()
            self._heartbeat_last = time.perf_counter()
            if self.mode == "layout":
                initial_slot = self.hud_stack.size()
                self.report["layoutArchitecture"] = {
                    "defaultWindow": [self.width(), self.height()],
                    "leftPanelWidth": 176,
                    "rightPanelWidth": 320,
                    "defaultHudSlot": [initial_slot.width(), initial_slot.height()],
                    "stackPages": ["HudCanvas/QPainter", "QWebEngineView/Three.js"],
                    "initialPage": "webengine" if self.hud_stack.currentWidget() is self.web_view else "qpainter",
                }
                print(
                    f"[Layout] initial page={'webengine' if self.hud_stack.currentWidget() is self.web_view else 'qpainter'}; "
                    f"webVisible={self.web_view.isVisible()} stackIndex={self.hud_stack.currentIndex()}",
                    flush=True,
                )
            print(f"[PoC] GLB ready: {status}", flush=True)
            self._check_model_status(status)
            QTimer.singleShot(2200, self._begin_interactions)
        elif self._test_step == "settle":
            self._test_step = "resize"
            self._test_resize()
        elif self._test_step == "after-restore":
            self._after_restore(status)

    def _begin_interactions(self):
        self._poll_loaded()

    def _check_model_status(self, status):
        if not str(status.get("webgl", {}).get("version", "")).lower().startswith("webgl"):
            self.report["failures"].append("No active WebGL context reported by Three.js")
        if status.get("webglContext") != "active":
            self.report["failures"].append("WebGL context is not active")
        for key, expected in (("meshes", 11), ("skinnedMeshes", 11), ("bones", 66), ("materials", 11), ("textures", 13)):
            if status.get(key) != expected:
                self.report["failures"].append(f"Unexpected {key}: {status.get(key)} (expected {expected})")
        if not any(clip.get("name") == "idle" for clip in status.get("clips", [])):
            self.report["failures"].append("idle animation clip was not found")

    def _test_resize(self):
        self.resize(1320, 820) if self.mode == "layout" else self.resize(1240, 820)
        QApplication.processEvents()
        if self.mode == "layout":
            slot = self.hud_stack.size()
            self.report["tests"]["resizedHudSlot"] = [slot.width(), slot.height()]
            self.report["tests"]["slotResized"] = slot.width() > 500 and slot.height() > 300
            self.report["tests"]["painterWidgetMinimum"] = [self.hud.minimumWidth(), self.hud.minimumHeight()]
            print(f"[Layout] resized slot={slot.width()}x{slot.height()} QPainter={self.hud.width()}x{self.hud.height()}", flush=True)
            self.hud_stack.setCurrentWidget(self.hud)
            self._update_toggle_label()
            print(f"[Layout] selected QPainter explicitly; index={self.hud_stack.currentIndex()}", flush=True)
            self.report["tests"]["qpainterPageVisible"] = self.hud_stack.currentWidget() is self.hud
            self.report["tests"]["webengineNotOverlappingPainter"] = self.hud_stack.currentWidget() is self.hud and not self.web_view.isVisible()
            QTimer.singleShot(350, self._return_to_webengine)
        else:
            self.report["tests"]["standaloneResized"] = self.web_view.width() >= 640 and self.web_view.height() >= 480
            self._minimize()

    def _return_to_webengine(self):
        self.hud_stack.setCurrentWidget(self.web_view)
        self._update_toggle_label()
        print(f"[Layout] selected WebEngine explicitly; index={self.hud_stack.currentIndex()} visible={self.web_view.isVisible()}", flush=True)
        self.report["tests"]["webenginePageVisible"] = self.hud_stack.currentWidget() is self.web_view
        view_geometry = self.web_view.geometry()
        stack_geometry = self.hud_stack.rect()
        self.report["tests"]["webengineGeometry"] = [view_geometry.x(), view_geometry.y(), view_geometry.width(), view_geometry.height()]
        self.report["tests"]["hudStackRect"] = [stack_geometry.x(), stack_geometry.y(), stack_geometry.width(), stack_geometry.height()]
        self.report["tests"]["webengineVisibleInHudSlot"] = (
            self.web_view.isVisible()
            and view_geometry.width() >= stack_geometry.width() - 4
            and view_geometry.height() >= stack_geometry.height() - 4
        )
        self._minimize()

    def _minimize(self):
        self.web_page.runJavaScript("JSON.stringify(window.__chloeStatus || null)", self._before_minimize)

    def _before_minimize(self, value):
        try:
            status = json.loads(value) if isinstance(value, str) else {}
        except Exception:
            status = {}
        self.report["tests"]["framesBeforeMinimize"] = status.get("frames", 0)
        self.showMinimized()
        QTimer.singleShot(700, self._after_minimize)

    def _after_minimize(self):
        self.report["tests"]["windowMinimized"] = self.isMinimized()
        self.showNormal()
        self.raise_()
        self.activateWindow()
        self._test_step = "after-restore"
        QTimer.singleShot(2200, self._poll_loaded)

    def _after_restore(self, status):
        self.report["tests"]["framesAfterRestore"] = status.get("frames", 0)
        self.report["tests"]["restoredWindowVisible"] = self.isVisible() and not self.isMinimized()
        self.report["tests"]["webglRecoveredAfterRestore"] = status.get("webglContext") == "active"
        if self.mode == "layout":
            page_is_web = self.hud_stack.currentWidget() is self.web_view
            self.report["tests"]["visiblePageAfterRestore"] = "webengine" if page_is_web else "qpainter"
            self.report["tests"]["webengineVisibleAfterRestore"] = page_is_web and self.web_view.isVisible()
            if not self.report["tests"]["webengineVisibleAfterRestore"]:
                self.report["failures"].append("QWebEngineView was not the visible HUD page after restore")
        self.report["finalModelStatus"] = status
        before = self.report["tests"].get("framesBeforeMinimize", 0)
        self.report["tests"]["animationFramesResumeAfterRestore"] = status.get("frames", 0) > before
        self.report["tests"]["renderFps"] = status.get("fps", 0)
        self.report["tests"]["smoothRenderFps"] = status.get("fps", 0) >= 24
        self.report["tests"]["noWebglErrors"] = not status.get("webglErrors", [])
        self.report["tests"]["noRemoteRequests"] = not self.request_interceptor.blocked
        self.report["network"] = {
            "localRequests": self.request_interceptor.allowed,
            "blockedRemoteRequests": self.request_interceptor.blocked,
        }
        QTimer.singleShot(250, self._finish_test)

    def _write_final_artifacts(self):
        if self.mode == "layout":
            slot = self.hud_stack.geometry()
            self.report["layoutArchitecture"] = {
                "window": [self.width(), self.height()],
                "leftPanelWidth": 176,
                "rightPanelWidth": 320,
                "hudSlot": [slot.width(), slot.height()],
                "stackPages": ["HudCanvas/QPainter", "QWebEngineView/Three.js"],
                "currentPage": "webengine" if self.hud_stack.currentWidget() is self.web_view else "qpainter",
            }
        if self._heartbeat_samples:
            samples = sorted(self._heartbeat_samples)
            self.report["uiHeartbeatMs"] = {
                "mean": round(sum(samples) / len(samples), 2),
                "p95": round(samples[min(int(len(samples) * 0.95), len(samples) - 1)], 2),
                "max": round(samples[-1], 2),
                "samples": len(samples),
            }
        self.report["consoleMessages"] = self.web_page.console_messages
        self.report["qtMessages"] = QT_MESSAGES
        self.report["javascriptErrors"] = self.report.get("finalModelStatus", {}).get("jsErrors", [])
        self.report["webEngineRendererTermination"] = self.web_page.render_termination
        self.report["tests"]["noJsConsoleErrors"] = not any(
            message.get("level") == "ErrorMessageLevel" for message in self.web_page.console_messages
        )
        screenshot_name = "qwebengine-layout.png" if self.mode == "layout" else "qwebengine-window.png"
        screenshot_path = POC / screenshot_name
        self.grab().save(str(screenshot_path))
        self.report["screenshot"] = screenshot_name
        report_path = POC / f"{self.mode}-report.json"
        report_path.write_text(json.dumps(self.report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"[PoC] screenshot={screenshot_path}", flush=True)
        print(f"[PoC] report={report_path}", flush=True)

    def _test_timed_out(self):
        self.report["failures"].append("Self-test exceeded 60 seconds")
        self._finish_test()

    def _finish_test(self):
        if self._test_timeout.isActive():
            self._test_timeout.stop()
        if not self.self_test:
            return
        self._write_final_artifacts()
        tests = self.report["tests"]
        success = (
            not self.report["failures"]
            and tests.get("windowMinimized")
            and tests.get("restoredWindowVisible")
            and tests.get("webglRecoveredAfterRestore")
            and tests.get("animationFramesResumeAfterRestore")
            and tests.get("smoothRenderFps")
            and tests.get("noWebglErrors")
            and tests.get("noRemoteRequests")
            and tests.get("noJsConsoleErrors")
            and (self.mode == "window" or (
                tests.get("slotResized")
                and tests.get("qpainterPageVisible")
                and tests.get("webengineNotOverlappingPainter")
                and tests.get("webenginePageVisible")
                and tests.get("webengineVisibleInHudSlot")
                and tests.get("webengineVisibleAfterRestore")
            ))
        )
        print(f"POC_RESULT={'PASS' if success else 'FAIL'}", flush=True)
        self.close()
        self.report["tests"]["closeEventReceived"] = True
        (POC / f"{self.mode}-report.json").write_text(
            json.dumps(self.report, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(json.dumps(self.report, indent=2, ensure_ascii=False), flush=True)
        self.web_page.deleteLater()
        self.web_profile.deleteLater()
        QTimer.singleShot(100, QApplication.instance().quit)

    def closeEvent(self, event):
        print("[Qt] window closeEvent", flush=True)
        self.report["tests"]["closeEventReceived"] = True
        super().closeEvent(event)

    def launch(self, page_url: str):
        self.page_url = page_url
        self._load_page_url()
        self.show()


def main():
    parser = argparse.ArgumentParser(description="Isolated Chloe PyQt6/QWebEngine PoC")
    parser.add_argument("--mode", choices=("window", "layout"), default="window")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if not (POC / "vendor" / "chloe-viewer.bundle.js").is_file():
        raise SystemExit("Local Three.js bundle missing. Run npm install and npm run build in this PoC folder.")
    if not (ROOT / "chloe_detroit_become_human.glb").is_file():
        raise SystemExit("Original root GLB is missing.")

    server, page_url = start_local_server()
    app = QApplication(sys.argv[:1])
    app.setApplicationName("Chloe QWebEngine PoC")
    from PyQt6.QtCore import qInstallMessageHandler
    qInstallMessageHandler(_qt_message_handler)
    window = ChloeTestWindow(args.mode, args.self_test)
    window.launch(page_url)
    app.aboutToQuit.connect(server.shutdown)
    exit_code = app.exec()
    server.server_close()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
