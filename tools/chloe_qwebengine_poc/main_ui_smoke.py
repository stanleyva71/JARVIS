"""Exercise the real JARVIS MainWindow without starting Gemini or audio capture."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

import memory.config_manager as config_manager
import ui

REPORT_PATH = Path(__file__).resolve().parent / "main-ui-report.json"
SCREENSHOT_PATH = Path(__file__).resolve().parent / "jarvis-main-chloe.png"


def main() -> int:
    # Keep this UI-only smoke test from changing the user's saved HUD choice.
    config_manager.save_hud_style = lambda _style: None
    app = QApplication(sys.argv[:1])
    app.setApplicationName("JARVIS Chloe main UI integration smoke test")
    window = ui.MainWindow(str(ROOT / "face.png"))
    window.show()
    if window._overlay is not None:
        window._overlay.hide()

    report = {
        "window": "ui.MainWindow",
        "tests": {},
        "failures": [],
    }
    exit_code = 1
    chat_received = threading.Event()
    test_video_path = None

    def check(name: str, passed: bool, detail=None) -> None:
        report["tests"][name] = {"passed": bool(passed), "detail": detail}
        if not passed:
            report["failures"].append(name)

    def status(callback):
        page = window._chloe_page
        if page is None or page._page is None:
            callback({})
            return
        page._page.runJavaScript(
            "JSON.stringify(window.__chloeStatus || {})",
            lambda value: callback(json.loads(value) if isinstance(value, str) and value else {}),
        )

    def finish(success: bool) -> None:
        nonlocal exit_code, test_video_path
        exit_code = 0 if success and not report["failures"] else 1
        report["screenshot"] = str(SCREENSHOT_PATH)
        page = window._chloe_page
        window.stop_camera_stream()
        window._on_video_close()
        window.close()
        report["tests"]["normal_window_close_stops_viewer"] = {
            "passed": page is None or (page._closed and page._server is None),
            "detail": None if page is None else {"closed": page._closed, "server": page._server},
        }
        if not report["tests"]["normal_window_close_stops_viewer"]["passed"]:
            report["failures"].append("normal_window_close_stops_viewer")
            exit_code = 1
        if test_video_path is not None:
            try:
                test_video_path.unlink(missing_ok=True)
            except OSError:
                pass
        REPORT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(report, indent=2, ensure_ascii=False), flush=True)
        QTimer.singleShot(250, app.quit)

    def test_fallback_then_start() -> None:
        check(
            "starts_on_qpainter_without_webengine_page",
            window._hud_cam_stack.currentWidget() is window.hud and window._chloe_page is None,
        )
        actual = ui.HAVE_WEBENGINE
        ui.HAVE_WEBENGINE = False
        window.hud.hud_style = "chloe"
        fallback_result = window._show_chloe_page()
        ui.HAVE_WEBENGINE = actual
        check(
            "missing_webengine_falls_back_to_qpainter",
            not fallback_result and window._hud_cam_stack.currentWidget() is window.hud
            and window.hud.hud_style == "face",
        )

        # Exercise the same two clicks a user makes from the HUD cycle button:
        # face -> reactor core -> Chloe 3D.
        window._hud_btn.click()
        window._hud_btn.click()
        check("manual_hud_button_selects_chloe", window.hud.hud_style == "chloe")
        poll_until_ready(0)

    def poll_until_ready(attempt: int) -> None:
        page = window._chloe_page
        if page is not None and page.failure:
            report["failures"].append("viewer: " + page.failure)
            finish(False)
            return
        if page is not None and page._ready_emitted:
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            count_before = window._hud_cam_stack.count()
            same_page = window._ensure_chloe_page() and window._chloe_page is page
            check("webengine_view_added_to_existing_hud_stack", page in [
                window._hud_cam_stack.widget(i) for i in range(window._hud_cam_stack.count())
            ])
            check("chloe_viewport_is_qwebengineview", isinstance(page.viewport, QWebEngineView))
            check("webengine_page_is_reused", same_page and window._hud_cam_stack.count() == count_before)
            check("local_html_load_finished", page.html_loaded)
            check("viewer_assets_stayed_local", bool(page._request_filter.local_requests)
                  and not page._request_filter.blocked_requests,
                  page._request_filter.local_requests)
            status(check_model_loaded)
            return
        if attempt >= 180:
            report["failures"].append("timed out waiting for Three.js model and WebGL")
            finish(False)
            return
        QTimer.singleShot(250, lambda: poll_until_ready(attempt + 1))

    def check_model_loaded(model_status: dict) -> None:
        check("webgl2_active", str(model_status.get("webgl", {}).get("version", "")).startswith("WebGL"), model_status.get("webgl"))
        check("model_meshes_and_skinning", model_status.get("meshes") == 11 and model_status.get("skinnedMeshes") == 11)
        check("skeleton_and_idle_clip", model_status.get("bones") == 66 and any(c.get("name") == "idle" for c in model_status.get("clips", [])))
        check("materials_and_textures", model_status.get("materials") == 11 and model_status.get("textures") == 13)
        first_frames = int(model_status.get("frames", 0))
        first_time = float(model_status.get("animationTime", 0))
        QTimer.singleShot(1000, lambda: status(lambda next_status: check_animation_advanced(
            first_frames, first_time, next_status
        )))

    def check_animation_advanced(first_frames: int, first_time: float, model_status: dict) -> None:
        check(
            "idle_animation_advances",
            int(model_status.get("frames", 0)) > first_frames
            and float(model_status.get("animationTime", 0)) > first_time,
            {"framesBefore": first_frames, "framesAfter": model_status.get("frames"),
             "animationTimeBefore": first_time, "animationTimeAfter": model_status.get("animationTime")},
        )
        test_stacks_and_resize()

    def test_stacks_and_resize() -> None:
        page = window._chloe_page
        window._hud_cam_stack.setCurrentWidget(window.hud)
        check("can_switch_to_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        window._show_chloe_page()
        check("can_switch_back_to_chloe", window._hud_cam_stack.currentWidget() is page)

        window._on_cam_stream(True)
        camera_selected = window._hud_cam_stack.currentWidget() is window._hud_cam_stack.widget(1)
        window._on_cam_stream(False)
        check("camera_page_routing_and_avatar_restore", camera_selected and window._hud_cam_stack.currentWidget() is page)

        window._hud_cam_stack.setCurrentWidget(window._video_cont)
        video_selected = window._hud_cam_stack.currentWidget() is window._video_cont
        window._restore_hud_page()
        check("video_page_routing_and_avatar_restore", video_selected and window._hud_cam_stack.currentWidget() is page)

        window.resize(1320, 820)
        QApplication.processEvents()
        check("resizable_hud_viewport", page.viewport.width() > 600 and page.viewport.height() > 400,
              [page.viewport.width(), page.viewport.height()])
        check("chat_and_voice_controls_present",
              hasattr(window, "_input") and hasattr(window, "_ptt_btn") and hasattr(window, "_mute_btn"))
        window.on_text_command = lambda _text: chat_received.set()
        window._input.setText("integration smoke test")
        window._send()
        check("chat_input_dispatches", chat_received.wait(1.0))

        play_local_video_smoke()

    def play_local_video_smoke() -> None:
        nonlocal test_video_path
        if not ui.HAVE_VIDEO or window._video_player is None:
            report["tests"]["local_video_playback"] = {"passed": None, "detail": "Qt Multimedia unavailable"}
            start_camera_smoke()
            return
        import cv2
        import numpy as np
        test_video_path = Path(tempfile.gettempdir()) / f"jarvis-chloe-smoke-{os.getpid()}.avi"
        writer = cv2.VideoWriter(
            str(test_video_path), cv2.VideoWriter_fourcc(*"MJPG"), 10.0, (320, 240)
        )
        if not writer.isOpened():
            writer.release()
            check("local_video_playback", False, "OpenCV could not create the temporary test clip")
            start_camera_smoke()
            return
        for frame_index in range(30):
            frame = np.zeros((240, 320, 3), dtype=np.uint8)
            frame[:, :, (frame_index // 10) % 3] = 180
            cv2.putText(frame, "JARVIS VIDEO TEST", (20, 120), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, (255, 255, 255), 2)
            writer.write(frame)
        writer.release()
        window._on_video_open(str(test_video_path), "Local integration smoke", True)
        check("video_widget_selected_by_open_path", window._video_on
              and window._hud_cam_stack.currentWidget() is window._video_cont)
        QTimer.singleShot(1200, finish_local_video_smoke)

    def finish_local_video_smoke() -> None:
        player = window._video_player
        progressed = player.position() > 0
        check("local_video_playback", progressed,
              {"positionMs": player.position(), "error": player.errorString()})
        window._on_video_close()
        check("video_close_restores_selected_chloe",
              window._hud_cam_stack.currentWidget() is window._chloe_page)
        start_camera_smoke()

    def start_camera_smoke() -> None:
        window.start_camera_stream()
        QTimer.singleShot(2200, finish_camera_smoke)

    def finish_camera_smoke() -> None:
        label_pixmap = window._cam_live_lbl.pixmap()
        received_frame = label_pixmap is not None and not label_pixmap.isNull()
        window.stop_camera_stream()
        if received_frame:
            check("camera_live_frame_displayed", True)
        else:
            report["tests"]["camera_live_frame_displayed"] = {
                "passed": None,
                "detail": "No camera frame arrived; stack routing was tested, hardware capture unavailable.",
            }
        QTimer.singleShot(350, finish_camera_stop)

    def finish_camera_stop() -> None:
        check("camera_stop_restores_selected_chloe",
              window._hud_cam_stack.currentWidget() is window._chloe_page)
        status(lambda before: begin_minimize(int(before.get("frames", 0))))

    def begin_minimize(frames_before: int) -> None:
        report["tests"]["frames_before_minimize"] = frames_before
        window.showMinimized()
        QTimer.singleShot(700, lambda: restore_window(frames_before))

    def restore_window(frames_before: int) -> None:
        window.showNormal()
        window.raise_()
        window.activateWindow()
        QTimer.singleShot(1800, lambda: status(lambda after: after_restore(frames_before, after)))

    def after_restore(frames_before: int, model_status: dict) -> None:
        check("minimize_restore_keeps_webgl_and_animation",
              window.isVisible() and not window.isMinimized()
              and model_status.get("webglContext") in ("active", "restored")
              and int(model_status.get("frames", 0)) > frames_before,
              {"before": frames_before, "after": model_status.get("frames"),
               "context": model_status.get("webglContext")})
        window._hud_cam_stack.setCurrentWidget(window._chloe_page)
        window._log.clear()
        QApplication.processEvents()
        saved = window.grab().save(str(SCREENSHOT_PATH))
        check("real_main_window_screenshot_saved", saved, str(SCREENSHOT_PATH))

        # Exercise each failure path against the live page and verify that the
        # main window returns to its working software HUD.
        page = window._chloe_page

        def reset_page_for_failure():
            page.failure = ""
            window.hud.hud_style = "chloe"
            window._hud_cam_stack.setCurrentWidget(page)

        reset_page_for_failure()
        page._on_load_finished(False)
        check("html_failure_restores_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        reset_page_for_failure()
        page._handle_model_status({"loaded": False, "error": "simulated missing GLB"})
        check("glb_failure_restores_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        reset_page_for_failure()
        page._on_javascript_console("ErrorMessageLevel", "simulated JavaScript error")
        check("javascript_failure_restores_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        reset_page_for_failure()
        page._handle_model_status({"loaded": True, "webgl": {"version": "unavailable"}})
        check("webgl_failure_restores_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        reset_page_for_failure()
        page._on_renderer_terminated("Crashed", 9)
        check("chromium_termination_restores_qpainter", window._hud_cam_stack.currentWidget() is window.hud)
        finish(True)

    QTimer.singleShot(350, test_fallback_then_start)
    app.exec()
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
