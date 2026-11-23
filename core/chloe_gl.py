"""Optional, in-process GLB viewport for Chloe.

The widget is created independently from the QPainter HUD and placed in the
same page stack as camera/video. OpenGL setup is deferred until that page is
shown, so a missing driver or bad model can never block normal startup.
"""

from __future__ import annotations

import ctypes
import io
import math
import time
from pathlib import Path

import numpy as np
from PIL import Image
from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QSurfaceFormat
from PyQt6.QtOpenGLWidgets import QOpenGLWidget

try:
    from OpenGL import GL
    from pygltflib import GLTF2
except Exception as exc:  # optional renderer: the QPainter HUD remains usable
    GL = None
    GLTF2 = None
    _IMPORT_ERROR = exc
else:
    _IMPORT_ERROR = None


def _identity() -> np.ndarray:
    return np.eye(4, dtype=np.float32)


def _trs(node) -> np.ndarray:
    if node.matrix:
        return np.asarray(node.matrix, dtype=np.float32).reshape(4, 4).T.copy()
    t = np.eye(4, dtype=np.float32)
    translation = node.translation if node.translation is not None else (0.0, 0.0, 0.0)
    rotation = node.rotation if node.rotation is not None else (0.0, 0.0, 0.0, 1.0)
    scale_value = node.scale if node.scale is not None else (1.0, 1.0, 1.0)
    t[:3, 3] = translation
    q = np.asarray(rotation, dtype=np.float64)
    q /= max(float(np.linalg.norm(q)), 1e-12)
    x, y, z, w = q
    r = np.eye(4, dtype=np.float32)
    r[:3, :3] = np.array([
        [1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)],
        [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)],
        [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)],
    ], dtype=np.float32)
    s = np.diag([*scale_value, 1.0]).astype(np.float32)
    return t @ r @ s


def _quat_slerp(a, b, t: float) -> np.ndarray:
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    dot = float(np.dot(a, b))
    if dot < 0.0:
        b, dot = -b, -dot
    if dot > 0.9995:
        q = a + t * (b - a)
        return q / max(float(np.linalg.norm(q)), 1e-12)
    theta = math.acos(max(-1.0, min(1.0, dot)))
    return (math.sin((1-t)*theta)*a + math.sin(t*theta)*b) / math.sin(theta)


class ChloeGLWidget(QOpenGLWidget):
    ready_changed = pyqtSignal(bool, str)

    _VERTEX = """
    #version 330 core
    layout(location=0) in vec3 aPosition;
    layout(location=1) in vec3 aNormal;
    layout(location=2) in vec2 aUV;
    layout(location=3) in vec4 aJoints;
    layout(location=4) in vec4 aWeights;
    uniform mat4 uProjection;
    uniform mat4 uView;
    uniform mat4 uModel;
    uniform mat4 uNode;
    uniform mat4 uJoints[128];
    out vec3 vNormal;
    out vec2 vUV;
    out vec3 vViewPosition;
    void main() {
        mat4 skin = mat4(1.0);
        float total = dot(aWeights, vec4(1.0));
        if (total > 0.0001) {
            skin = mat4(0.0);
            for (int i=0; i<4; ++i)
                skin += uJoints[int(aJoints[i])] * (aWeights[i] / total);
        }
        vec4 viewPos = uView * uModel * uNode * skin * vec4(aPosition, 1.0);
        mat3 normalMatrix = mat3(uView * uModel * uNode * skin);
        vNormal = normalize(normalMatrix * aNormal);
        vUV = aUV;
        vViewPosition = viewPos.xyz;
        gl_Position = uProjection * viewPos;
    }
    """

    _FRAGMENT = """
    #version 330 core
    in vec3 vNormal;
    in vec2 vUV;
    in vec3 vViewPosition;
    uniform sampler2D uBaseTexture;
    uniform sampler2D uMetalRoughTexture;
    uniform sampler2D uEmissiveTexture;
    uniform vec4 uBaseColor;
    uniform vec3 uEmissive;
    uniform float uHasBaseTexture;
    uniform float uHasMetalRoughTexture;
    uniform float uHasEmissiveTexture;
    uniform float uMetallic;
    uniform float uRoughness;
    uniform float uAlphaMask;
    uniform float uAlphaCutoff;
    out vec4 fragColor;
    void main() {
        vec4 base = uBaseColor;
        if (uHasBaseTexture > 0.5) base *= texture(uBaseTexture, vUV);
        if (uAlphaMask > 0.5 && base.a < uAlphaCutoff) discard;
        vec3 n = normalize(vNormal);
        vec3 l = normalize(vec3(-0.35, 0.70, 0.85));
        vec3 v = normalize(-vViewPosition);
        vec3 h = normalize(l + v);
        float nl = max(dot(n, l), 0.0);
        float nv = max(dot(n, v), 0.02);
        float rough = clamp(uRoughness, 0.08, 1.0);
        float metal = clamp(uMetallic, 0.0, 1.0);
        if (uHasMetalRoughTexture > 0.5) {
            vec4 mr = texture(uMetalRoughTexture, vUV);
            rough *= mr.g;
            metal *= mr.b;
        }
        float specPower = mix(96.0, 5.0, rough);
        float specular = pow(max(dot(n, h), 0.0), specPower) * (0.08 + 0.35*metal);
        vec3 diffuse = base.rgb * (0.16 + 0.84*nl) * (1.0 - 0.55*metal);
        vec3 rim = vec3(0.05, 0.33, 0.46) * pow(1.0-nv, 2.5) * 0.35;
        vec3 emissive = uEmissive;
        if (uHasEmissiveTexture > 0.5) emissive *= texture(uEmissiveTexture, vUV).rgb;
        fragColor = vec4(diffuse + vec3(specular) + rim + emissive, base.a);
    }
    """

    def __init__(self, model_path: Path, parent=None):
        super().__init__(parent)
        fmt = QSurfaceFormat()
        fmt.setRenderableType(QSurfaceFormat.RenderableType.OpenGL)
        fmt.setVersion(3, 3)
        fmt.setProfile(QSurfaceFormat.OpenGLContextProfile.CoreProfile)
        fmt.setDepthBufferSize(24)
        fmt.setStencilBufferSize(8)
        self.setFormat(fmt)
        self.setMinimumSize(300, 300)
        self.setAutoFillBackground(False)
        self._model_path = Path(model_path)
        self._ready = False
        self._failed = False
        self._program = 0
        self._items: list[dict] = []
        self._textures: dict[int, int] = {}
        self._accessor_cache: dict[int, np.ndarray] = {}
        self._local: list[np.ndarray] = []
        self._globals: list[np.ndarray] = []
        self._parents: list[int] = []
        self._joint_nodes: list[int] = []
        self._inverse_bind: list[np.ndarray] = []
        self._clip = None
        self._clip_duration = 0.0
        self._start = time.monotonic()
        self._model = _identity()
        self._joint_palette = [_identity()]
        self._failure = ""
        self._frame_timer = QTimer(self)
        self._frame_timer.setInterval(33)
        self._frame_timer.timeout.connect(self._tick)
        self._init_timer = QTimer(self)
        self._init_timer.setSingleShot(True)
        self._init_timer.setInterval(8000)
        self._init_timer.timeout.connect(self._check_init_timeout)

    @property
    def failure(self) -> str:
        return self._failure

    def initializeGL(self) -> None:
        if self._failed:
            return
        try:
            if GL is None or GLTF2 is None:
                raise RuntimeError(f"Dependência gráfica indisponível: {_IMPORT_ERROR}")
            if not self._model_path.is_file():
                raise FileNotFoundError(f"Modelo GLB não encontrado: {self._model_path}")
            context = self.context()
            if context is None or not context.isValid():
                raise RuntimeError("O driver não criou um contexto OpenGL válido")
            GL.glEnable(GL.GL_DEPTH_TEST)
            GL.glEnable(GL.GL_CULL_FACE)
            GL.glCullFace(GL.GL_BACK)
            GL.glClearColor(0.0, 0.0235, 0.0392, 1.0)
            self._load_gltf()
            self._compile_program()
            self._load_textures()
            self._upload_meshes()
            self._ready = True
            self._init_timer.stop()
            self._frame_timer.start()
            self.ready_changed.emit(True, "")
        except Exception as exc:
            self._fail(f"Falha ao iniciar Chloe 3D: {exc}")

    def _fail(self, message: str) -> None:
        if self._failed:
            return
        self._failed = True
        self._ready = False
        self._failure = message
        self._frame_timer.stop()
        print(f"[Chloe] {message}", flush=True)
        QTimer.singleShot(0, lambda message=message: self.ready_changed.emit(False, message))

    def _check_init_timeout(self) -> None:
        if not self._ready and not self._failed:
            self._fail("O viewport OpenGL não inicializou em 8 segundos")

    def _accessor(self, index: int) -> np.ndarray:
        cached = self._accessor_cache.get(index)
        if cached is not None:
            return cached
        acc = self._gltf.accessors[index]
        if acc.bufferView is None:
            raise ValueError(f"Accessor {index} sem bufferView")
        view = self._gltf.bufferViews[acc.bufferView]
        dtype = {5120: np.int8, 5121: np.uint8, 5122: np.int16,
                 5123: np.uint16, 5125: np.uint32, 5126: np.float32}.get(acc.componentType)
        width = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4, "MAT4": 16}.get(acc.type)
        if dtype is None or width is None or acc.sparse is not None:
            raise ValueError(f"Accessor GLB não suportado: índice {index}")
        item = np.dtype(dtype).itemsize
        stride = view.byteStride or width * item
        offset = (view.byteOffset or 0) + (acc.byteOffset or 0)
        raw = memoryview(self._binary)
        arr = np.ndarray((acc.count, width), dtype=dtype, buffer=raw,
                         offset=offset, strides=(stride, item)).copy()
        if acc.normalized:
            source_dtype = arr.dtype
            if np.issubdtype(source_dtype, np.unsignedinteger):
                arr = arr.astype(np.float32) / np.iinfo(source_dtype).max
            elif np.issubdtype(source_dtype, np.signedinteger):
                arr = np.maximum(arr.astype(np.float32) / np.iinfo(source_dtype).max, -1.0)
        self._accessor_cache[index] = arr
        return arr

    def _load_gltf(self) -> None:
        self._gltf = GLTF2().load(str(self._model_path))
        self._binary = self._gltf.binary_blob()
        if not self._binary:
            raise ValueError("O GLB não contém buffer binário")
        nodes = self._gltf.nodes or []
        self._local = [_trs(n) for n in nodes]
        self._parents = [-1] * len(nodes)
        for parent, node in enumerate(nodes):
            for child in node.children or []:
                self._parents[child] = parent
        self._rebuild_globals()

        skin = (self._gltf.skins or [None])[0]
        if skin:
            self._joint_nodes = list(skin.joints or [])
            if len(self._joint_nodes) > 128:
                raise ValueError(f"Skin com {len(self._joint_nodes)} juntas; limite seguro: 128")
            self._inverse_bind = (
                [m.reshape(4, 4).T.copy() for m in self._accessor(skin.inverseBindMatrices)]
                if skin.inverseBindMatrices is not None else [_identity() for _ in self._joint_nodes]
            )
            if len(self._inverse_bind) != len(self._joint_nodes):
                raise ValueError("A quantidade de inverse bind matrices não corresponde ao skin")
            # The first hierarchy pass above is needed for the scene transform;
            # rebuild the palette now that the skin and inverse-bind matrices exist.
            self._rebuild_globals()
        self._clip = next((a for a in self._gltf.animations or []
                           if (a.name or "").strip().lower() == "idle"),
                          (self._gltf.animations or [None])[0])
        if self._clip:
            self._clip_duration = max((float(self._accessor(s.input)[-1, 0])
                                       for s in self._clip.samplers), default=0.0)

        # The mesh vertices are stored in the armature's Y-up local frame.
        # The bind-pose skin matrices cancel the Sketchfab root transform, so
        # center and scale without applying a second axis rotation.
        bounds = []
        for ni, node in enumerate(nodes):
            if node.mesh is None:
                continue
            for prim in self._gltf.meshes[node.mesh].primitives:
                pos = self._accessor(prim.attributes.POSITION).astype(np.float32)
                if node.skin is not None and prim.attributes.JOINTS_0 is not None:
                    ji = self._accessor(prim.attributes.JOINTS_0).astype(np.int32)
                    wt = self._accessor(prim.attributes.WEIGHTS_0).astype(np.float32)
                    for row in range(0, len(pos), max(1, len(pos)//5000)):
                        p = np.r_[pos[row], 1.0]
                        deformed = np.zeros(4, dtype=np.float64)
                        for k in range(4):
                            j = int(ji[row, k])
                            if wt[row, k] and j < len(self._joint_nodes):
                                deformed += wt[row,k] * (
                                    self._globals[self._joint_nodes[j]]
                                    @ self._inverse_bind[j] @ p
                                )
                        if not np.any(deformed):
                            deformed = self._globals[ni] @ p
                        bounds.append(deformed[:3])
                else:
                    stride = max(1, len(pos)//5000)
                    mat = self._globals[ni]
                    bounds.extend((mat @ np.c_[pos[::stride], np.ones(len(pos[::stride]))].T).T[:, :3])
        if not bounds:
            raise ValueError("A cena GLB não contém geometria renderizável")
        points = np.asarray(bounds, dtype=np.float32)
        lo, hi = points.min(axis=0), points.max(axis=0)
        span = float(np.max(hi - lo))
        if not math.isfinite(span) or span <= 1e-6:
            raise ValueError("A geometria do GLB tem dimensões inválidas")
        center = (lo + hi) * 0.5
        self._model = np.diag([1.55/span, 1.55/span, 1.55/span, 1.0]).astype(np.float32) @ np.array([
            [1,0,0,-center[0]], [0,1,0,-center[1]], [0,0,1,-center[2]], [0,0,0,1]
        ], dtype=np.float32)

    def _rebuild_globals(self) -> None:
        result = [None] * len(self._local)
        visiting = set()
        def visit(i):
            if result[i] is not None:
                return result[i]
            if i in visiting:
                raise ValueError("Hierarquia GLB contém um ciclo")
            visiting.add(i)
            parent = self._parents[i]
            result[i] = (visit(parent) @ self._local[i]) if parent >= 0 else self._local[i]
            visiting.remove(i)
            return result[i]
        for i in range(len(result)):
            visit(i)
        self._globals = result
        self._joint_palette = [self._globals[node] @ ibm for node, ibm in
                               zip(self._joint_nodes, self._inverse_bind)] or [_identity()]

    def _animate(self) -> None:
        trs = [{"translation": np.asarray(n.translation or (0,0,0), dtype=np.float32),
                "rotation": np.asarray(n.rotation or (0,0,0,1), dtype=np.float32),
                "scale": np.asarray(n.scale or (1,1,1), dtype=np.float32),
                "matrix": bool(n.matrix)} for n in self._gltf.nodes]
        if self._clip and self._clip_duration > 0:
            t = (time.monotonic() - self._start) % self._clip_duration
            for channel in self._clip.channels:
                sampler = self._clip.samplers[channel.sampler]
                times = self._accessor(sampler.input)[:, 0]
                values = self._accessor(sampler.output)
                if not len(times):
                    continue
                right = int(np.searchsorted(times, t, side="right"))
                left = max(0, min(len(times)-1, right-1))
                right = min(right, len(times)-1)
                if left == right or sampler.interpolation == "STEP":
                    value = values[left]
                else:
                    alpha = float((t-times[left]) / max(times[right]-times[left], 1e-9))
                    if sampler.interpolation == "CUBICSPLINE":
                        # glTF cubic output is [in tangent, value, out tangent] per key.
                        p0, m0 = values[left*3+1], values[left*3+2]
                        p1, m1 = values[right*3+1], values[right*3]
                        dt = float(times[right]-times[left])
                        a2, a3 = alpha*alpha, alpha*alpha*alpha
                        value = ((2*a3-3*a2+1)*p0 + (a3-2*a2+alpha)*dt*m0
                                 + (-2*a3+3*a2)*p1 + (a3-a2)*dt*m1)
                        if channel.target.path == "rotation":
                            value = value / max(float(np.linalg.norm(value)), 1e-12)
                    elif channel.target.path == "rotation":
                        value = _quat_slerp(values[left], values[right], alpha)
                    else:
                        value = values[left] * (1-alpha) + values[right] * alpha
                ni = channel.target.node
                state = trs[ni]
                if state["matrix"]:
                    continue
                prop = channel.target.path
                if prop in state:
                    state[prop] = np.asarray(value, dtype=np.float32)
        self._local = [_trs(type("NodeTRS", (), {**state, "matrix": None})())
                       for state in trs]
        self._rebuild_globals()

    def _compile_program(self) -> None:
        program = GL.glCreateProgram()
        shaders = []
        for kind, source in ((GL.GL_VERTEX_SHADER, self._VERTEX),
                             (GL.GL_FRAGMENT_SHADER, self._FRAGMENT)):
            shader = GL.glCreateShader(kind)
            GL.glShaderSource(shader, source)
            GL.glCompileShader(shader)
            if not GL.glGetShaderiv(shader, GL.GL_COMPILE_STATUS):
                raise RuntimeError(GL.glGetShaderInfoLog(shader).decode("utf-8", "replace"))
            GL.glAttachShader(program, shader)
            shaders.append(shader)
        GL.glLinkProgram(program)
        if not GL.glGetProgramiv(program, GL.GL_LINK_STATUS):
            raise RuntimeError(GL.glGetProgramInfoLog(program).decode("utf-8", "replace"))
        for shader in shaders:
            GL.glDeleteShader(shader)
        self._program = program

    def _load_textures(self) -> None:
        for i, texture in enumerate(self._gltf.textures or []):
            if texture.source is None:
                continue
            image = self._gltf.images[texture.source]
            if image.bufferView is not None:
                view = self._gltf.bufferViews[image.bufferView]
                data = bytes(self._binary[view.byteOffset or 0:(view.byteOffset or 0)+view.byteLength])
            elif image.uri and image.uri.startswith("data:"):
                import base64
                data = base64.b64decode(image.uri.split(",", 1)[1])
            elif image.uri:
                data = (self._model_path.parent / image.uri).read_bytes()
            else:
                continue
            im = Image.open(io.BytesIO(data)).convert("RGBA").transpose(Image.Transpose.FLIP_TOP_BOTTOM)
            tex = GL.glGenTextures(1)
            GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_S, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_WRAP_T, GL.GL_REPEAT)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MIN_FILTER, GL.GL_LINEAR_MIPMAP_LINEAR)
            GL.glTexParameteri(GL.GL_TEXTURE_2D, GL.GL_TEXTURE_MAG_FILTER, GL.GL_LINEAR)
            GL.glPixelStorei(GL.GL_UNPACK_ALIGNMENT, 1)
            GL.glTexImage2D(GL.GL_TEXTURE_2D, 0, GL.GL_SRGB8_ALPHA8, im.width, im.height,
                            0, GL.GL_RGBA, GL.GL_UNSIGNED_BYTE, im.tobytes())
            GL.glGenerateMipmap(GL.GL_TEXTURE_2D)
            self._textures[i] = tex

    def _load_material(self, material_index) -> dict:
        if material_index is None:
            return {"base": [1,1,1,1], "texture": None, "mr": None,
                    "emissive_tex": None, "emissive": [0,0,0], "metal": 0,
                    "rough": 0.8, "mask": 0, "cutoff": 0.5,
                    "blend": False, "double": False}
        mat = self._gltf.materials[material_index]
        pbr = mat.pbrMetallicRoughness
        return {"base": pbr.baseColorFactor or [1,1,1,1],
                "texture": pbr.baseColorTexture.index if pbr.baseColorTexture else None,
                "mr": pbr.metallicRoughnessTexture.index if pbr.metallicRoughnessTexture else None,
                "emissive_tex": mat.emissiveTexture.index if mat.emissiveTexture else None,
                "emissive": mat.emissiveFactor or [0,0,0],
                "metal": pbr.metallicFactor if pbr.metallicFactor is not None else 1.0,
                "rough": pbr.roughnessFactor if pbr.roughnessFactor is not None else 1.0,
                "mask": float(mat.alphaMode == "MASK"),
                "cutoff": mat.alphaCutoff if mat.alphaCutoff is not None else 0.5,
                "blend": mat.alphaMode == "BLEND",
                "double": bool(mat.doubleSided)}

    def _upload_meshes(self) -> None:
        for ni, node in enumerate(self._gltf.nodes or []):
            if node.mesh is None:
                continue
            for prim in self._gltf.meshes[node.mesh].primitives:
                pos = self._accessor(prim.attributes.POSITION).astype(np.float32)
                norm = (self._accessor(prim.attributes.NORMAL).astype(np.float32)
                        if prim.attributes.NORMAL is not None else np.zeros_like(pos))
                uv = (self._accessor(prim.attributes.TEXCOORD_0).astype(np.float32)
                      if prim.attributes.TEXCOORD_0 is not None else np.zeros((len(pos),2), np.float32))
                joints = (self._accessor(prim.attributes.JOINTS_0).astype(np.float32)
                          if prim.attributes.JOINTS_0 is not None else np.zeros((len(pos),4), np.float32))
                weights = (self._accessor(prim.attributes.WEIGHTS_0).astype(np.float32)
                           if prim.attributes.WEIGHTS_0 is not None else np.zeros((len(pos),4), np.float32))
                data = np.concatenate((pos,norm,uv,joints,weights), axis=1).astype(np.float32)
                vao, vbo = GL.glGenVertexArrays(1), GL.glGenBuffers(1)
                GL.glBindVertexArray(vao)
                GL.glBindBuffer(GL.GL_ARRAY_BUFFER, vbo)
                GL.glBufferData(GL.GL_ARRAY_BUFFER, data.nbytes, data, GL.GL_STATIC_DRAW)
                stride = 64
                for loc, size, offset in ((0,3,0),(1,3,12),(2,2,24),(3,4,32),(4,4,48)):
                    GL.glEnableVertexAttribArray(loc)
                    GL.glVertexAttribPointer(loc, size, GL.GL_FLOAT, GL.GL_FALSE,
                                             stride, ctypes.c_void_p(offset))
                indices = (self._accessor(prim.indices).reshape(-1) if prim.indices is not None
                           else np.arange(len(pos), dtype=np.uint32))
                indices = indices.astype(np.uint32, copy=False)
                ebo = GL.glGenBuffers(1)
                GL.glBindBuffer(GL.GL_ELEMENT_ARRAY_BUFFER, ebo)
                GL.glBufferData(GL.GL_ELEMENT_ARRAY_BUFFER, indices.nbytes, indices, GL.GL_STATIC_DRAW)
                mode = {0: GL.GL_POINTS, 1: GL.GL_LINES, 2: GL.GL_LINE_LOOP,
                        3: GL.GL_LINE_STRIP, 4: GL.GL_TRIANGLES,
                        5: GL.GL_TRIANGLE_STRIP, 6: GL.GL_TRIANGLE_FAN}.get(prim.mode or 4)
                if mode is None:
                    raise ValueError(f"Modo de primitiva GLB não suportado: {prim.mode}")
                self._items.append({"vao": vao, "count": len(indices), "node": ni,
                                    "skin": node.skin, "material": self._load_material(prim.material),
                                    "mode": mode})
        GL.glBindVertexArray(0)
        if not self._items:
            raise ValueError("Não foram encontradas primitivas de malha")

    @staticmethod
    def _uniform_mat(location, mat) -> None:
        payload = np.asarray(mat, dtype=np.float32).T.copy().tobytes()
        GL.glUniformMatrix4fv(location, 1, GL.GL_FALSE, payload)

    def resizeGL(self, width: int, height: int) -> None:
        ratio = self.devicePixelRatioF()
        GL.glViewport(0, 0, int(width*ratio), int(height*ratio))

    def paintGL(self) -> None:
        GL.glClear(GL.GL_COLOR_BUFFER_BIT | GL.GL_DEPTH_BUFFER_BIT)
        if not self._ready:
            return
        try:
            self._draw()
        except Exception as exc:
            self._fail(f"Renderização da Chloe interrompida: {exc}")

    def _draw(self) -> None:
        w, h = max(1, self.width()), max(1, self.height())
        aspect = w / h
        f = 1.0 / math.tan(math.radians(36.0) / 2.0)
        projection = np.zeros((4,4), dtype=np.float32)
        projection[0,0], projection[1,1] = f/aspect, f
        projection[2,2], projection[2,3] = -(100.0+0.1)/(100.0-0.1), -(2.0*100.0*0.1)/(100.0-0.1)
        projection[3,2] = -1.0
        eye = np.array([0.0, 0.08, 3.45], dtype=np.float32)
        view = np.eye(4, dtype=np.float32)
        view[:3,3] = -eye
        self._animate()
        GL.glUseProgram(self._program)
        self._uniform_mat(GL.glGetUniformLocation(self._program, "uProjection"), projection)
        self._uniform_mat(GL.glGetUniformLocation(self._program, "uView"), view)
        self._uniform_mat(GL.glGetUniformLocation(self._program, "uModel"), self._model)
        joint_loc = GL.glGetUniformLocation(self._program, "uJoints[0]")
        palette = self._joint_palette[:128]
        mats = np.ascontiguousarray([matrix.T for matrix in palette], dtype=np.float32)
        GL.glUniformMatrix4fv(joint_loc, len(mats), GL.GL_FALSE, mats.tobytes())
        for item in self._items:
            m = item["material"]
            GL.glBindVertexArray(item["vao"])
            # For a skinned glTF primitive, the joint palette already places
            # vertices in scene space (jointGlobal * inverseBind). Applying the
            # mesh node transform again here would double-transform the rig.
            node_matrix = (_identity() if item["skin"] is not None
                           else self._globals[item["node"]])
            GL.glUniformMatrix4fv(GL.glGetUniformLocation(self._program, "uNode"), 1,
                                  GL.GL_FALSE, np.asarray(node_matrix, dtype=np.float32).T.copy().tobytes())
            if item["skin"] is not None and self._joint_nodes:
                item_palette = [self._globals[joint_node] @ ibm
                                for joint_node, ibm in zip(self._joint_nodes,
                                                           self._inverse_bind)]
                if len(item_palette) > 128:
                    raise RuntimeError("Skin excede o limite de juntas do renderer")
                item_matrices = np.ascontiguousarray(
                    [matrix.T for matrix in item_palette], dtype=np.float32
                )
                GL.glUniformMatrix4fv(joint_loc, len(item_matrices), GL.GL_FALSE,
                                      item_matrices.tobytes())
            GL.glUniform4f(GL.glGetUniformLocation(self._program, "uBaseColor"), *m["base"])
            GL.glUniform3f(GL.glGetUniformLocation(self._program, "uEmissive"), *m["emissive"])
            GL.glUniform1f(GL.glGetUniformLocation(self._program, "uMetallic"), m["metal"])
            GL.glUniform1f(GL.glGetUniformLocation(self._program, "uRoughness"), m["rough"])
            GL.glUniform1f(GL.glGetUniformLocation(self._program, "uAlphaMask"), m["mask"])
            GL.glUniform1f(GL.glGetUniformLocation(self._program, "uAlphaCutoff"), m["cutoff"])
            for unit, name, key in ((0,"uBaseTexture","texture"),
                                    (1,"uMetalRoughTexture","mr"),
                                    (2,"uEmissiveTexture","emissive_tex")):
                tex = self._textures.get(m[key], 0) if m[key] is not None else 0
                GL.glActiveTexture(GL.GL_TEXTURE0+unit)
                GL.glBindTexture(GL.GL_TEXTURE_2D, tex)
                GL.glUniform1i(GL.glGetUniformLocation(self._program, name), unit)
                GL.glUniform1f(GL.glGetUniformLocation(self._program,
                    {"texture":"uHasBaseTexture","mr":"uHasMetalRoughTexture",
                     "emissive_tex":"uHasEmissiveTexture"}[key]), float(bool(tex)))
            GL.glCullFace(GL.GL_BACK)
            if m["double"]: GL.glDisable(GL.GL_CULL_FACE)
            else: GL.glEnable(GL.GL_CULL_FACE)
            if m["blend"]:
                GL.glEnable(GL.GL_BLEND)
                GL.glBlendFunc(GL.GL_SRC_ALPHA, GL.GL_ONE_MINUS_SRC_ALPHA)
                GL.glDepthMask(GL.GL_FALSE)
            else:
                GL.glDisable(GL.GL_BLEND)
                GL.glDepthMask(GL.GL_TRUE)
            GL.glDrawElements(item["mode"], item["count"], GL.GL_UNSIGNED_INT, ctypes.c_void_p(0))
        GL.glUniformMatrix4fv(joint_loc, len(mats), GL.GL_FALSE, mats.tobytes())
        GL.glDepthMask(GL.GL_TRUE)
        GL.glBindVertexArray(0)

    def _tick(self) -> None:
        if self.isVisible() and self._ready:
            self.update()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._failed:
            if not self._ready:
                self._init_timer.start()
            QTimer.singleShot(0, self.update)

    def closeEvent(self, event) -> None:
        self._frame_timer.stop()
        self._init_timer.stop()
        super().closeEvent(event)
