"""CPU-side checks for Chloe's GLB transforms, rig and animation data."""

from __future__ import annotations

import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np
from PyQt6.QtWidgets import QApplication

from core.chloe_gl import ChloeGLWidget, _quat_slerp, _trs
from memory.config_manager import HUD_STYLES
from ui import ChloePage, HudCanvas, MainWindow


ROOT = Path(__file__).resolve().parents[1]


class ChloeGLBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_trs_uses_glb_translation_rotation_and_scale(self):
        node = SimpleNamespace(matrix=None, translation=[2.0, 3.0, 4.0],
                               rotation=[0.0, 0.0, 0.0, 1.0], scale=[2.0, 3.0, 4.0])
        matrix = _trs(node)
        np.testing.assert_allclose(matrix[:3, 3], [2.0, 3.0, 4.0])
        np.testing.assert_allclose(np.diag(matrix)[:3], [2.0, 3.0, 4.0])

    def test_quaternion_interpolation_stays_normalized(self):
        q = _quat_slerp([0, 0, 0, 1], [0, 0.7071068, 0, 0.7071068], 0.5)
        self.assertAlmostEqual(float(np.linalg.norm(q)), 1.0, places=6)

    def test_project_glb_loads_rig_pose_and_idle_clip(self):
        model = ROOT / "chloe_detroit_become_human.glb"
        self.assertTrue(model.is_file())
        widget = ChloeGLWidget(model)
        widget._load_gltf()
        widget._animate()

        self.assertEqual(len(widget._joint_nodes), 66)
        self.assertEqual(len(widget._joint_palette), 66)
        self.assertEqual(len(widget._items), 0)  # GPU upload is deferred to initializeGL.
        self.assertGreater(widget._clip_duration, 1.0)
        self.assertEqual(len(widget._local), 104)
        self.assertTrue(np.isfinite(widget._model).all())
        self.assertGreater(abs(float(np.linalg.det(widget._model[:3, :3]))), 1e-6)

        joints = widget._accessor(45)
        self.assertIs(joints, widget._accessor(45), "accessors should be cached for animation frames")
        self.assertLess(int(joints.max()), len(widget._joint_nodes))

    def test_bind_skinning_preserves_the_model_bounds(self):
        widget = ChloeGLWidget(ROOT / "chloe_detroit_become_human.glb")
        widget._load_gltf()
        scene_points = []
        for node_index, node in enumerate(widget._gltf.nodes):
            if node.mesh is None:
                continue
            for primitive in widget._gltf.meshes[node.mesh].primitives:
                pos = widget._accessor(primitive.attributes.POSITION).astype(np.float32)
                joints = widget._accessor(primitive.attributes.JOINTS_0).astype(np.int32)
                weights = widget._accessor(primitive.attributes.WEIGHTS_0).astype(np.float32)
                homogeneous = np.column_stack((pos, np.ones(len(pos), dtype=np.float32)))
                skinned = np.zeros_like(homogeneous)
                for slot in range(4):
                    joint_mats = np.asarray([
                        widget._globals[joint_node] @ widget._inverse_bind[joint_i]
                        for joint_i, joint_node in enumerate(widget._joint_nodes)
                    ], dtype=np.float32)
                    skinned += weights[:, slot, None] * np.einsum(
                        "nij,nj->ni", joint_mats[joints[:, slot]], homogeneous
                    )
                scene_points.append(skinned[:, :3])
        points = np.concatenate(scene_points)
        self.assertTrue(np.isfinite(points).all())
        self.assertLess(float(np.max(points.max(0) - points.min(0))), 4.0)

    def test_chloe_page_is_separate_from_qpainter_hud(self):
        window = MainWindow("face.png")
        self.assertIn("chloe", HUD_STYLES)
        self.assertIsInstance(window.hud, HudCanvas)
        self.assertTrue(window._ensure_chloe_page())
        self.assertIsInstance(window._chloe_page, ChloePage)
        self.assertIsInstance(window._chloe_page.viewport, ChloeGLWidget)
        self.assertIs(window._hud_cam_stack.widget(0), window.hud)
        self.assertNotEqual(window._hud_cam_stack.indexOf(window._chloe_page), 0)
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_renderer_error_restores_the_software_hud(self):
        window = MainWindow("face.png")
        self.assertTrue(window._ensure_chloe_page())
        window._hud_cam_stack.setCurrentWidget(window._chloe_page)
        with patch("memory.config_manager.save_hud_style"), \
                patch.object(window, "_refresh_hud_btn"), \
                patch.object(window._log, "append_log"):
            window._on_chloe_ready(False, "simulated OpenGL failure")
        self.assertEqual(window.hud.hud_style, "face")
        self.assertIs(window._hud_cam_stack.currentWidget(), window.hud)
        window.close()
        window.deleteLater()
        self.app.processEvents()

    def test_hud_cycle_does_not_replace_an_active_camera_page(self):
        window = MainWindow("face.png")
        with patch("memory.config_manager.get_hud_style", return_value="face"), \
                patch("memory.config_manager.save_hud_style"):
            window._toggle_hud_style()
        self.assertEqual(window.hud.hud_style, "core")
        with patch("memory.config_manager.get_hud_style", return_value="core"), \
                patch("memory.config_manager.save_hud_style"):
            window._toggle_hud_style()
        self.assertEqual(window.hud.hud_style, "chloe")
        self.assertIs(window._hud_cam_stack.currentWidget(), window._chloe_page)
        window._hud_cam_stack.setCurrentIndex(1)
        with patch("memory.config_manager.get_hud_style", return_value="chloe"), \
                patch("memory.config_manager.save_hud_style"):
            window._toggle_hud_style()
        self.assertIs(window._hud_cam_stack.currentWidget(), window._hud_cam_stack.widget(1))
        window._on_cam_stream(False)
        self.assertIs(window._hud_cam_stack.currentWidget(), window.hud)
        window.close()
        window.deleteLater()
        self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
