"""
Offline PyQt6/OpenGL renderer for the optional Chloe GLB avatar.

The file is deliberately private: model discovery supports
assets/private/chloe.glb and the existing
assets/private/chloe_-_detroit_become_human.glb name, but neither
name is copied, uploaded or tracked by the application.
"""

from __future__ import annotations

import io
import math
import time
import base64
import ctypes
import traceback
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image
from PyQt6.QtCore import pyqtSignal, Qt
from PyQt6.QtOpenGLWidgets import QOpenGLWidget
from PyQt6.QtGui import QSurfaceFormat

try:
    from OpenGL import GL
    from pygltflib import GLTF2
except Exception as exc:  # pragma: no cover - reported by HudCanvas
    GL = None
    GLTF2 = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def find_chloe_model(base_dir: Path) -> Optional[Path]:
    private = base_dir / "assets" / "private"
    for name in ("chloe.glb", "chloe_-_detroit_become_human.glb"):
        path = private / name
        if path.is_file() and path.stat().st_size > 0:
            return path
    return None


def _mat_identity() -> np.ndarray:
    return np.eye(4, dtype=np.float32)


def _mat_translation(v):
    m = _mat_identity()
    m[:3, 3] = v
    return m


def _mat_scale(v):
    m = _mat_identity()
    m[0, 0], m[1, 1], m[2, 2] = v
    return m


def _mat_y_rotation(angle):
    c, s = math.cos(angle), math.sin(angle)
    return np.array([
        [c, 0, -s, 0],
        [0, 1, 0, 0],
        [s, 0, c, 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)


def _mat_quaternion(q):
    x, y, z, w = (float(a) for a in q)
    n = math.sqrt(x*x + y*y + z*z + w*w)
    if n == 0:
        return _mat_identity()
    x, y, z, w = x/n, y/n, z/n, w/n
    m = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w), 0],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w), 0],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y), 0],
        [0, 0, 0, 1],
    ], dtype=np.float32)
    return m


def _perspective(fovy, aspect, near, far):
    f = 1.0 / math.tan(fovy * math.pi / 360.0)
    return np.array([
        [f/aspect, 0, 0, 0],
        [0, f, 0, 0],
        [0, 0, (far+near)/(near-far), (2*far*near)/(near-far)],
        [0, 0, -1, 0],
    ], dtype=np.float32)


def _look_at(eye, target, up):
    eye = np.asarray(eye, dtype=np.float32)
    target = np.asarray(target, dtype=np.float32)
    up = np.asarray(up, dtype=np.float32)
    z = eye - target
    z /= np.linalg.norm(z)
    x = np.cross(up, z)
    x /= np.linalg.norm(x)
    y = np.cross(z, x)
    return np.array([
        [x[0], x[1], x[2], -np.dot(x, eye)],
        [y[0], y[1], y[2], -np.dot(y, eye)],
        [z[0], z[1], z[2], -np.dot(z, eye)],
        [0, 0, 0, 1],
    ], dtype=np.float32)


class ChloeGLWidget(QOpenGLWidget):
    ready_changed = pyqtSignal(bool, str)

    def __init__(self, base_dir: Path, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setAlphaBufferSize(8)
        fmt.setDepthBufferSize(24)
        fmt.setSamples(4)
        self.setFormat(fmt)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAutoFillBackground(True)
        from PyQt6.QtGui import QPalette, QColor
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#00060a"))
        self.setPalette(palette)
        self._base_dir = base_dir
        self._model_path = find_chloe_model(base_dir)
        self._ready = False
        self._error = ""
        self._active = True
        self._gltf = None
        self._binary = None
        self._primitives = []
        self._textures = {}
        self._program = None
        self._start_time = time.monotonic()
        self._duration = 0.0
        self._animation = None
        self._node_matrices = []
        self._inverse_bind = []
        self._joints = []
        self._joint_palette = np.repeat(_mat_identity()[None, :, :], 64, axis=0)
        self._model_matrix = _mat_identity()
        self._model_base = _mat_identity()
        self._center = np.zeros(3, dtype=np.float32)
        self._scale = 1.0

    @property
    def ready(self) -> bool:
        return self._ready

    def set_active(self, active: bool) -> None:
        if active != self._active:
            self._active = active
            if active:
                self._start_time = time.monotonic()
        self.setUpdatesEnabled(active)
        if active:
            self.update()

    def resizeGL(self, width: int, height: int):
        if GL is None:
            return
        GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
        ratio = getattr(self, "devicePixelRatioF", lambda: 1.0)()
        GL.glViewport(0, 0, int(width * ratio), int(height * ratio))

    def initializeGL(self):
        if GL is None or GLTF2 is None:
            self._fail(f"3D unavailable: {_IMPORT_ERROR}")
            return
        if self._model_path is None:
            self._fail("GLB not found in assets/private")
            return
        try:
            context = self.context()
            if context is None or not context.isValid():
                raise RuntimeError("Qt OpenGL context is not valid")
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
            GL.glClearColor(0.0, 0.023529, 0.039216, 1.0)
            GL.glViewport(0, 0, self.width(), self.height())
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_BLEND)
            GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
            self._load_model()
            self._compile_shader()
            self._upload_textures()
            self._upload_primitives()
            self._ready = True
            self.ready_changed.emit(True, "")
        except Exception as exc:
            self._fail(f"Could not render Chloe: {exc}")

    def _fail(self, message: str):
        self._error = message
        self._ready = False
        print(f"[Chloe] {message}", flush=True)
        traceback.print_exc()
        self.ready_changed.emit(False, message)

    def paintGL(self):
        if GL is None:
            return
        try:
            context = self.context()
            if context is None or not context.isValid():
                raise RuntimeError("Qt OpenGL context was lost")
            GL.glBindFramebuffer(GL.GL_FRAMEBUFFER, self.defaultFramebufferObject())
            ratio = getattr(self, "devicePixelRatioF", lambda: 1.0)()
            GL.glViewport(0, 0, int(self.width() * ratio), int(self.height() * ratio))
            if not self._ready or not self._active:
                GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
                return
            GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
            self._animate()
            self._draw()
        except Exception as exc:
            self._fail(f"Chloe render stopped: {exc}")

    def _load_model(self):
        self._gltf = GLTF2().load(str(self._model_path))
        self._binary = self._gltf.binary_blob()
        if not isinstance(self._binary, (bytes, bytearray, memoryview)):
            raise RuntimeError("GLB binary buffer is unavailable")

        nodes = self._gltf.nodes or []
        self._node_matrices = [self._node_local(i) for i in range(len(nodes))]
        self._inverse_bind = []
        self._joints = []
        if self._gltf.skins:
            skin = self._gltf.skins[0]
            self._joints = list(skin.joints)
            if skin.inverseBindMatrices is not None:
                ibm = self._accessor(skin.inverseBindMatrices)
                self._inverse_bind = [
                    ibm[i].reshape(4, 4).T.copy() for i in range(len(ibm))
                ]
        if self._gltf.animations:
            self._animation = self._gltf.animations[0]
            # Prefer the existing idle clip, but keep the first clip as fallback.
            for clip in self._gltf.animations:
                if (clip.name or "").strip().lower() == "idle":
                    self._animation = clip
                    break
            durations = []
            for sampler in self._animation.samplers:
                inp = self._accessor(sampler.input)
                if len(inp):
                    durations.append(float(inp[-1, 0]))
            self._duration = max(durations) if durations else 0.0

        bounds = self._bind_bounds()
        lo, hi = bounds
        self._center = (lo + hi) * 0.5
        span = hi - lo
        max_span = float(np.max(span))
        self._scale = (1.6 / max_span) if max_span > 0 else 1.0
        self._model_matrix = _mat_translation(-self._center)
        _display_scale = self._scale * 1.35
        self._model_matrix = _mat_scale((_display_scale, _display_scale, _display_scale)) @ self._model_matrix
        self._model_base = self._model_matrix.copy()

    def _node_local(self, i):
        node = (self._gltf.nodes or [])[i]
        if node.matrix:
            return np.array(node.matrix, dtype=np.float32).reshape(4, 4).T
        m = _mat_identity()
        if node.scale:
            m = _mat_scale(node.scale) @ m
        if node.rotation:
            m = _mat_quaternion(node.rotation) @ m
        if node.translation:
            m = _mat_translation(node.translation) @ m
        return m

    def _node_global_matrices(self):
        nodes = self._gltf.nodes or []
        result = [_mat_identity() for _ in nodes]
        for i, node in enumerate(nodes):
            parent = None
            for p, pn in enumerate(nodes):
                if i in (pn.children or []):
                    parent = p
                    break
            local = self._node_matrices[i]
            result[i] = (result[parent] @ local) if parent is not None else local
        return result

    def _accessor(self, index):
        acc = self._gltf.accessors[index]
        view = self._gltf.bufferViews[acc.bufferView]
        dtype_map = {
            5120: np.int8,
            5121: np.uint8,
            5122: np.int16,
            5123: np.uint16,
            5125: np.uint32,
            5126: np.float32,
        }
        dtype = dtype_map.get(acc.componentType)
        if dtype is None:
            raise RuntimeError(f"Unsupported accessor component type {acc.componentType}")
        count_map = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}
        width = count_map.get(acc.type)
        if width is None:
            raise RuntimeError(f"Unsupported accessor type {acc.type}")
        start = (view.byteOffset or 0) + (acc.byteOffset or 0)
        byte_count = acc.count * width * np.dtype(dtype).itemsize
        raw = np.frombuffer(self._binary, dtype=dtype, count=acc.count * width,
                            offset=start)
        return raw.reshape(acc.count, width).copy()

    def _bind_bounds(self):
        lo = np.array([np.inf, np.inf, np.inf], dtype=np.float32)
        hi = -lo
        for node_index, node in enumerate(self._gltf.nodes or []):
            if node.mesh is None:
                continue
            mesh = self._gltf.meshes[node.mesh]
            for prim in mesh.primitives:
                pos = self._accessor(prim.attributes.POSITION)
                lo = np.minimum(lo, pos.min(axis=0))
                hi = np.maximum(hi, pos.max(axis=0))
        if not np.isfinite(lo).all():
            lo = np.array([-1, -1, -1], dtype=np.float32)
            hi = np.array([1, 1, 1], dtype=np.float32)
        return lo, hi

    def _animate(self):
        # The GLB idle clip has not been enabled safely for skinning yet. Keep
        # the character in its authored bind pose instead of applying channels
        # whose matrix convention may corrupt the geometry.
        t = time.monotonic() - self._start_time
        idle_turn = math.radians(1.5) * math.sin(t * 0.75)
        idle_breathe = 1.0 + 0.0025 * math.sin(t * 1.25)
        yaw = _mat_y_rotation(idle_turn)
        breathe = _mat_scale((idle_breathe, 1.0, idle_breathe))
        self._model_matrix = yaw @ breathe @ self._model_base

    @staticmethod
    def _slerp(a, b, t):
        a = np.asarray(a, dtype=np.float64)
        b = np.asarray(b, dtype=np.float64)
        dot = float(np.dot(a, b))
        if dot < 0:
            b = -b
            dot = -dot
        dot = max(-1.0, min(1.0, dot))
        theta = math.acos(dot)
        if abs(theta) < 1e-5:
            return a * (1-t) + b * t
        sin_theta = math.sin(theta)
        return (np.sin((1-t)*theta)/sin_theta)*a + (np.sin(t*theta)/sin_theta)*b

    def _compile_shader(self):
        vertex = """
        #version 330 core
        layout(location=0) in vec3 aPosition;
        layout(location=1) in vec3 aNormal;
        layout(location=2) in vec2 aUV;
        layout(location=3) in vec4 aJoints;
        layout(location=4) in vec4 aWeights;
        uniform mat4 uProjection;
        uniform mat4 uView;
        uniform mat4 uModel;
        uniform mat4 uJoints[64];
        out vec3 vNormal;
        out vec2 vUV;
        out vec3 vWorld;
        void main() {
            mat4 skin = mat4(1.0);
            vec4 world = uModel * skin * vec4(aPosition, 1.0);
            mat3 skinNormal = mat3(skin);
            vWorld = world.xyz;
            vNormal = normalize(mat3(uModel) * skinNormal * aNormal);
            vUV = aUV;
            gl_Position = uProjection * uView * world;
        }
        """
        fragment = """
        #version 330 core
        in vec3 vNormal;
        in vec2 vUV;
        in vec3 vWorld;
        uniform sampler2D uTexture;
        uniform vec4 uBaseColor;
        uniform float uHasTexture;
        out vec4 fragColor;
        void main() {
            vec3 base = uBaseColor.rgb;
            if (uHasTexture > 0.5) {
                base *= texture(uTexture, vUV).rgb;
            }
            vec3 n = normalize(vNormal);
            vec3 keyDir = normalize(vec3(-0.35, 0.65, 1.0));
            vec3 fillDir = normalize(vec3(0.60, 0.25, 0.75));
            vec3 rimDir = normalize(vec3(0.0, 0.55, -1.0));
            float key = max(dot(n, keyDir), 0.0);
            float fill = max(dot(n, fillDir), 0.0);
            float rim = pow(1.0 - max(dot(n, normalize(vec3(0.0, 0.15, 1.0))), 0.0), 3.0);
            float backRim = max(dot(n, rimDir), 0.0);
            float spec = pow(max(dot(reflect(-keyDir, n), normalize(-vWorld)), 0.0), 32.0);
            vec3 color = base * (0.38 + 0.48 * key + 0.16 * fill)
                       + base * rim * 0.24
                       + base * backRim * 0.10
                       + vec3(1.0) * spec * 0.14;
            fragColor = vec4(color, uBaseColor.a);
        }
        """
        self._program = GL.glCreateProgram()
        vs = self._compile_shader_stage(GL.GL_VERTEX_SHADER, vertex)
        fs = self._compile_shader_stage(GL.GL_FRAGMENT_SHADER, fragment)
        GL.glAttachShader(self._program, vs)
        GL.glAttachShader(self._program, fs)
        GL.glLinkProgram(self._program)
        if GL.glGetProgramiv(self._program, GL.GL_LINK_STATUS) != GL.GL_TRUE:
            raise RuntimeError(GL.glGetProgramInfoLog(self._program).decode("utf-8", "replace"))
        GL.glDeleteShader(vs)
        GL.glDeleteShader(fs)
        GL.glUseProgram(self._program)

    def _compile_shader_stage(self, kind, source):
        shader = GL.glCreateShader(kind)
        GL.glShaderSource(shader, source)
        GL.glCompileShader(shader)
        if GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS) != GL.GL_TRUE:
            raise RuntimeError(GL.glGetShaderInfoLog(shader).decode("utf-8", "replace"))
        return shader

    def _upload_textures(self):
        for i, texture in enumerate(self._gltf.textures or []):
            if texture.source is None:
                continue
            image = (self._gltf.images or [])[texture.source]
            data = None
            if getattr(image, "bufferView", None) is not None:
                view = self._gltf.bufferViews[image.bufferView]
                start = view.byteOffset or 0
                length = view.byteLength
                data = bytes(self._binary[start:start+length])
            elif image.uri:
                if image.uri.lower().startswith(("http://", "https://", "//")):
                    print("[Chloe] External texture URI rejected; using offline embedded data.", flush=True)
                    continue
                if image.uri.startswith("data:image"):
                    try:
                        data = base64.b64decode(image.uri.split(",", 1)[1])
                    except Exception:
                        data = None
            if not data:
                continue
            pil = Image.open(io.BytesIO(data)).convert("RGBA")
            pil = pil.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            pixels = pil.tobytes()
            tex = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_CLAMP_TO_EDGE)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_RGBA, pil.width, pil.height, 0,
                            GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, pixels)
            GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            self._textures[i] = tex

    def _upload_primitives(self):
        for node_index, node in enumerate(self._gltf.nodes or []):
            if node.mesh is None:
                continue
            mesh = self._gltf.meshes[node.mesh]
            for prim in mesh.primitives:
                pos = self._accessor(prim.attributes.POSITION)
                norm = self._accessor(prim.attributes.NORMAL) if prim.attributes.NORMAL is not None else np.zeros_like(pos)
                uv = self._accessor(prim.attributes.TEXCOORD_0) if prim.attributes.TEXCOORD_0 is not None else np.zeros((len(pos),2), np.float32)
                joints = self._accessor(prim.attributes.JOINTS_0) if prim.attributes.JOINTS_0 is not None else np.zeros((len(pos),4), np.uint16)
                weights = self._accessor(prim.attributes.WEIGHTS_0) if prim.attributes.WEIGHTS_0 is not None else np.array([[1,0,0,0]], np.float32).repeat(len(pos), axis=0)
                data = np.concatenate([pos, norm, uv, joints, weights], axis=1).astype(np.float32)
                vao = GL.glGenVertexArrays(1)
                vbo = GL.glGenBuffers(1)
                GL.glBindVertexArray(vao)
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data.tobytes(), GL.GL_STATIC_DRAW)
                attrs = ((0,3,0),(1,3,12),(2,2,24),(3,4,32),(4,4,48))
                for loc, size, offset in attrs:
                    GL.glEnableVertexAttribArray(loc)
                    GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, GL.GL_FALSE, 64, ctypes.c_void_p(offset))
                if prim.indices is not None:
                    idx = self._accessor(prim.indices)
                    idx_dtype = self._gltf.accessors[prim.indices].componentType
                    gl_type = GL.GL_UNSIGNED_SHORT if idx_dtype == 5123 else GL.GL_UNSIGNED_INT
                    ebo = GL.glGenBuffers(1)
                    GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
                    index_bytes = idx.reshape(-1).astype(np.uint16 if gl_type == GL.GL_UNSIGNED_SHORT else np.uint32)
                    GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, index_bytes.nbytes, index_bytes.tobytes(), GL.GL_STATIC_DRAW)
                    count = len(index_bytes)
                    mode = "elements"
                else:
                    count = len(pos)
                    gl_type = 0
                    mode = "arrays"

                tex_index = None
                base = np.array([1,1,1,1], dtype=np.float32)
                if prim.material is not None:
                    material = self._gltf.materials[prim.material]
                    pbr = getattr(material, "pbrMetallicRoughness", None)
                    base_factor = getattr(pbr, "baseColorFactor", None) if pbr else None
                    if base_factor:
                        base = np.array(base_factor, dtype=np.float32)
                    tex_info = getattr(pbr, "baseColorTexture", None) if pbr else None
                    if tex_info:
                        tex_index = tex_info.index
                self._primitives.append({
                    "vao": vao, "count": count, "mode": mode, "gl_type": gl_type,
                    "texture": tex_index, "base": base,
                })
                GL.glBindVertexArray(0)

    def _draw(self):
        w, h = max(1, self.width()), max(1, self.height())
        aspect = w / h
        projection = _perspective(24.0, aspect, 0.1, 300.0)
        eye = np.array([0.0, 0.95, 3.8], dtype=np.float32)
        target = np.array([0.0, 0.95, 0.0], dtype=np.float32)
        view = _look_at(eye, target, (0.0, 1.0, 0.0))

        GL.glUseProgram(self._program)
        loc = GL.glGetUniformLocation(self._program, "uJoints")
        GL.glUniformMatrix4fv(loc, len(self._joint_palette), GL.GL_FALSE,
                              self._joint_palette.transpose(0, 2, 1)
                              .astype(np.float32).tobytes())
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program, "uProjection"),
                              1, GL.GL_FALSE, projection.T.astype(np.float32).tobytes())
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program, "uView"),
                              1, GL.GL_FALSE, view.T.astype(np.float32).tobytes())
        GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program, "uModel"),
                              1, GL.GL_FALSE, self._model_matrix.T.astype(np.float32).tobytes())

        for prim in self._primitives:
            GL.glBindVertexArray(prim["vao"])
            tex = prim["texture"]
            tex_id = self._textures.get(tex, 0) if tex is not None else 0
            GL.glActiveTexture(GL.GL_TEXTURE0)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex_id)
            GL.glUniform1i(GL.glGetUniformLocation(self._program, "uTexture"), 0)
            GL.glUniform1f(GL.glGetUniformLocation(self._program, "uHasTexture"),
                           1.0 if tex_id else 0.0)
            loc = GL.glGetUniformLocation(self._program, "uBaseColor")
            GL.glUniform4fv(loc, 1, prim["base"])
            if prim["mode"] == "elements":
                GL.glDrawElements(GL.GL_TRIANGLES, prim["count"], prim["gl_type"],
                                  ctypes.c_void_p(0))
            else:
                GL.glDrawArrays(GL.GL_TRIANGLES, 0, prim["count"])
        GL.glBindVertexArray(0)
