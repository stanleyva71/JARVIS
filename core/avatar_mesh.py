"""
Human head mesh for the HUD avatar.

The face is **real measured human geometry** — MediaPipe's canonical face model
(`core/face_model.obj`, Apache-2.0, 468 vertices / 898 triangles), which carries
actual eyelids, nostrils, lips and cheekbones. Everything a formula cannot give
you comes from there.

Earlier revisions of this file generated the whole head procedurally from an
ellipsoid pushed around by gaussians. It could be tuned endlessly and still read
as an egg with a face drawn on it, because there was no human anatomy in it —
only smooth blobs. Real topology fixed in one step what parameter tweaking could
not fix at all.

What is still generated here, around that face:
  * the cranium — the model is an open mask, so its 36-vertex border is swept
    back and up over a skull-shaped ellipsoid and closed at the occiput;
  * a tapering neck stub that fades out instead of needing shoulders;
  * vertex normals, jaw-rig weights, a thinned wireframe, and the landmark
    index rings (eyes, brows, lips) the renderer animates.

Coordinate system after normalisation (head-local, right-handed):
    +x → viewer's right      +y → up      +z → out of the face
    y = +1.0 crown,  y = -1.0 chin,  eyes land on y ≈ 0.
"""

from __future__ import annotations

import collections
import math
from pathlib import Path

import numpy as np

_OBJ = Path(__file__).resolve().parent / "face_model.obj"

# Cranium shape, in the model's own units (chin ≈ -9.4, forehead ≈ +8.3).
# Tuned for Leon Kennedy's slightly broader parietal width and balanced crown
# height so the hair sits with natural volume rather than an elongated egg dome.
_SKULL_C = (0.0, 1.8, -1.1)      # centre of the cranial ellipsoid
_SKULL_R = (8.3, 11.1, 8.2)      # its radii
_SKULL_POLE = (0.0, 0.42, -1.0)  # direction of the occiput, where the sweep closes
_SKULL_RINGS = 6
_SKULL_BLEND = 1.7               # how fast the sweep leaves the face border
_SKULL_BULGE = 1.04

_NECK_RINGS, _NECK_SEGS = 9, 14
_NECK_Z = -1.6                   # the neck tube's axis, in model units
_WIRE_STRIDE = 3                 # keep every n-th edge; the surface carries the form

# MediaPipe landmark rings. Verified against the geometry at build time — see
# `_check_landmarks` — so a wrong index can never silently animate the cheek.
LANDMARKS: dict[str, list[int]] = {
    "eye_l":  [33, 7, 163, 144, 145, 153, 154, 155, 133, 173, 157, 158, 159,
               160, 161, 246],
    "eye_r":  [263, 249, 390, 373, 374, 380, 381, 382, 362, 398, 384, 385, 386,
               387, 388, 466],
    "brow_l": [70, 63, 105, 66, 107],
    "brow_r": [300, 293, 334, 296, 336],
    "lips_out": [61, 146, 91, 181, 84, 17, 314, 405, 321, 375, 291, 409, 270,
                 269, 267, 0, 37, 39, 40, 185],
    "lips_in": [78, 95, 88, 178, 87, 14, 317, 402, 318, 324, 308, 415, 310,
                311, 312, 13, 82, 81, 80, 191],
}

# Jaw rig, in normalised units. The pivot sits between the ears, which is where
# a real mandible hinges.
JAW_PIVOT = (0.0, 0.06, -0.34)
JAW_MAX = 0.115                  # radians of drop at full amplitude (~6.6°)
#   Speech barely moves a real jaw, and a talking head is watched at HUD size
#   where a small, precise mouth reads better than a large one. The lip rig
#   (spread / round) now carries most of the articulation, so the jaw does not
#   have to swing to show that something is being said.


def _load_obj(path: Path):
    verts, faces = [], []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("v "):
            verts.append([float(x) for x in line.split()[1:4]])
        elif line.startswith("f "):
            faces.append([int(t.split("/")[0]) - 1 for t in line.split()[1:4]])
    return np.array(verts, dtype=np.float64), np.array(faces, dtype=np.int64)


def _boundary_loop(faces: np.ndarray) -> np.ndarray:
    """Ordered ring of vertices along the open border of a triangle mesh."""
    seen = collections.Counter()
    for a, b, c in faces:
        for e in ((a, b), (b, c), (c, a)):
            seen[(min(e), max(e))] += 1
    border = [e for e, n in seen.items() if n == 1]

    adj = collections.defaultdict(list)
    for a, b in border:
        adj[a].append(b)
        adj[b].append(a)

    start = border[0][0]
    loop, prev, cur = [start], None, start
    while True:
        nxt = [v for v in adj[cur] if v != prev]
        if not nxt or nxt[0] == start:
            break
        prev, cur = cur, nxt[0]
        loop.append(cur)
    return np.array(loop)


def _slerp(a: np.ndarray, b: np.ndarray, t):
    dot = np.clip((a * b).sum(-1, keepdims=True), -1.0, 1.0)
    om = np.arccos(dot)
    so = np.sin(om)
    safe = np.where(so < 1e-6, 1.0, so)
    out = np.where(so < 1e-6, a * (1 - t) + b * t,
                   (np.sin((1 - t) * om) / safe) * a + (np.sin(t * om) / safe) * b)
    return out / np.maximum(np.linalg.norm(out, axis=-1, keepdims=True), 1e-9)


def _add_cranium(verts: np.ndarray, faces: np.ndarray):
    """Sweep the mask's open border back over a skull and close it at the occiput."""
    loop = _boundary_loop(faces)

    # Orient the loop so the generated triangles wind the same way as the face's.
    centre2d = verts[loop, :2].mean(0)
    ang = np.arctan2(verts[loop, 1] - centre2d[1], verts[loop, 0] - centre2d[0])
    if np.diff(np.unwrap(ang)).sum() < 0:
        loop = loop[::-1]

    n = len(loop)
    C = np.array(_SKULL_C)
    R = np.array(_SKULL_R)
    pole = np.array(_SKULL_POLE)
    pole = pole / np.linalg.norm(pole)
    chin_y = verts[:, 1].min()

    rim = verts[loop] - C
    rim_r = np.linalg.norm(rim, axis=1, keepdims=True)
    rim_d = rim / rim_r

    def ell_r(d):
        return 1.0 / np.sqrt(((d / R) ** 2).sum(-1, keepdims=True))

    out_v = [verts]
    out_f = list(faces)
    prev_idx = loop
    ts = np.linspace(0.0, 1.0, _SKULL_RINGS + 1)[1:]

    for t in ts:
        d = _slerp(pole, rim_d, 1.0 - t)
        w = (1.0 - t) ** _SKULL_BLEND          # meets the rim exactly at t = 0
        # A skull is fuller than the border it springs from; peak it mid-sweep.
        r = ell_r(d) * (1.0 + (_SKULL_BULGE - 1.0) * np.sin(np.pi * t) ** 0.8)
        ring = C + d * (w * rim_r + (1.0 - w) * r)
        # Never dip below the chin: the sweep passing under the jaw would
        # otherwise hang a lip of geometry below the face. Vertices that hit
        # the clamp are also drawn in towards the neck axis, so the underside
        # closes as a small floor instead of a flat skirt sticking out.
        below = ring[:, 1] < chin_y
        if below.any():
            ring[below, 1] = chin_y
            ring[below, 0] *= 0.55
            ring[below, 2] = _NECK_Z + (ring[below, 2] - _NECK_Z) * 0.55
        if t == ts[-1]:
            ring = np.repeat((C + pole * ell_r(pole[None])[0])[None], n, axis=0)

        base = sum(len(a) for a in out_v)
        out_v.append(ring)
        idx = np.arange(base, base + n)
        for i in range(n):
            a0, b0 = prev_idx[i], prev_idx[(i + 1) % n]
            a1, b1 = idx[i], idx[(i + 1) % n]
            out_f.append([a0, a1, b1])
            out_f.append([a0, b1, b0])
        prev_idx = idx

    return np.vstack(out_v), np.array(out_f, dtype=np.int64)


def _add_neck(verts: np.ndarray, faces: np.ndarray):
    """A tapering tube dropped from inside the jaw; it fades out, so no shoulders."""
    ph = np.linspace(0.0, 2.0 * np.pi, _NECK_SEGS, endpoint=False)
    # Short, and flaring hard at the bottom: a straight vertical tube reads as
    # a pedestal, whereas a neck that widens into the top of the shoulders
    # reads as a bust — and the shorter it is, the larger the head can be drawn
    # in the same HUD band.
    ys = np.linspace(-5.5, -13.0, _NECK_RINGS)
    d = (ys + 5.5) / -7.5

    rx = 4.6 * (1.0 + 0.52 * d ** 1.9)
    rz = 4.1 * (1.0 + 0.38 * d ** 1.9)
    nx = rx[:, None] * np.cos(ph)[None, :]
    nz = _NECK_Z + rz[:, None] * np.sin(ph)[None, :]
    ny = ys[:, None] * np.ones_like(ph)[None, :]

    nv = np.stack([nx.ravel(), ny.ravel(), nz.ravel()], axis=1)
    base = len(verts)
    idx = base + np.arange(_NECK_RINGS * _NECK_SEGS).reshape(_NECK_RINGS, _NECK_SEGS)

    nf = []
    for i in range(_NECK_RINGS - 1):
        for j in range(_NECK_SEGS):
            a, b = idx[i, j], idx[i, (j + 1) % _NECK_SEGS]
            c, e = idx[i + 1, (j + 1) % _NECK_SEGS], idx[i + 1, j]
            nf.append([a, b, c])
            nf.append([a, c, e])

    # Enough rings that the fade steps stay small. Each quad splits into one
    # triangle with two top vertices and one with two bottom vertices, so a
    # steep per-vertex fade gradient makes the pair land on visibly different
    # brightnesses and the neck grows a sawtooth edge.
    fade = np.ones(base)
    nd = np.repeat(d, _NECK_SEGS)
    fade = np.concatenate([fade, 1.0 - 0.72 * np.clip(nd, 0.0, 1.0) ** 1.5])
    return np.vstack([verts, nv]), np.vstack([faces, np.array(nf)]), fade


def _vertex_normals(verts: np.ndarray, faces: np.ndarray,
                    outward: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals, flipped to agree with `outward`.

    `outward` must be a per-vertex direction that genuinely points out of the
    surface. A single "away from the mesh centroid" rule is NOT good enough:
    down at the base of the neck that vector points almost straight down while
    the real normal is horizontal, so the dot product hovers around zero and
    the sign flips at random — which tears the neck into an asymmetric slab of
    half-culled, half-lit triangles.
    """
    a, b, c = verts[faces[:, 0]], verts[faces[:, 1]], verts[faces[:, 2]]
    fn = np.cross(b - a, c - a)          # length carries the area — the weighting

    n = np.zeros_like(verts)
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    flip = (n * outward).sum(1) < 0
    n[flip] *= -1.0
    return n


def _unique_edges(faces: np.ndarray) -> np.ndarray:
    e = np.vstack([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e = np.sort(e, axis=1)
    return np.unique(e, axis=0)


def _sculpt_leon_face(verts: np.ndarray) -> np.ndarray:
    """Reshape MediaPipe's generic canonical mask toward Leon S. Kennedy's
    craniofacial structure: sharper mandibular jaw angles, squared chin with
    mentolabial fold, sculpted cheekbones with lean buccal hollows, lower
    straighter brow ridge, narrower focused eyes, refined nose bridge, and
    firm closed resting lips.
    Operates in raw OBJ units before cranium/neck sweep so borders stay seamless.
    """
    v = verts.copy()
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    ax = np.abs(x)

    # 1. Crisp posterior gonial angle tapering into a sleek masculine V-jawline
    # Accentuate the jaw corner near y ~ -5.2..-6.2, z ~ -1.5..+1.5
    w_gonial = (
        np.exp(-((y + 5.6) / 1.15) ** 2)
        * np.clip((ax - 3.6) / 2.2, 0.0, 1.0)
        * np.clip((2.2 - z) / 2.5, 0.0, 1.0)
    )
    v[:, 0] += np.sign(x) * w_gonial * 0.24
    v[:, 1] -= w_gonial * 0.14
    v[:, 2] += w_gonial * 0.22

    # Taper the lower jaw border (y ~ -7.2..-8.8) cleanly inward for Leon's V-line
    w_jaw_taper = (
        np.exp(-((y + 7.9) / 1.15) ** 2)
        * np.clip((ax - 1.8) / 2.2, 0.0, 1.0)
    )
    v[:, 0] -= np.sign(x) * w_jaw_taper * 0.22
    v[:, 2] += w_jaw_taper * 0.12

    # 2. Defined, slightly squared chin + mentolabial crease beneath lower lip
    w_chin = np.exp(-((y + 9.0) / 1.10) ** 2) * np.exp(-(ax / 1.9) ** 2)
    w_chin_sq = np.exp(-((y + 9.0) / 0.95) ** 2) * np.exp(-((ax - 0.95) / 0.75) ** 2)
    v[:, 2] += w_chin * 0.34 + w_chin_sq * 0.14
    v[:, 0] += np.sign(x) * w_chin_sq * 0.06
    v[:, 1] -= w_chin * 0.10

    # Subtle mentolabial fold right below the lower lip (y ~ -6.0)
    w_fold = np.exp(-((y + 6.0) / 0.70) ** 2) * np.exp(-(ax / 1.9) ** 2)
    v[:, 2] -= w_fold * 0.24

    # 3. Prominent zygomatic cheekbones & lean buccal hollows
    w_cheekbone = (
        np.exp(-((y - 0.50) / 1.25) ** 2)
        * np.exp(-((ax - 5.1) / 1.45) ** 2)
        * np.clip((z - 0.5) / 2.0, 0.0, 1.0)
    )
    v[:, 0] += np.sign(x) * w_cheekbone * 0.26
    v[:, 2] += w_cheekbone * 0.42

    w_hollow = (
        np.exp(-((y + 2.65) / 1.35) ** 2)
        * np.exp(-((ax - 4.3) / 1.30) ** 2)
        * np.clip(z / 2.5, 0.0, 1.0)
    )
    v[:, 0] -= np.sign(x) * w_hollow * 0.26
    v[:, 2] -= w_hollow * 0.46

    # 4. Lower, straighter, projecting brow ridge (focused/intense expression)
    w_brow_zone = (
        np.exp(-((y - 4.75) / 1.10) ** 2)
        * np.exp(-(ax / 5.4) ** 2)
        * np.clip((z - 1.5) / 2.5, 0.0, 1.0)
    )
    w_inner_brow = (
        np.exp(-((y - 4.65) / 0.95) ** 2)
        * np.exp(-(ax / 2.4) ** 2)
        * np.clip((z - 2.0) / 2.5, 0.0, 1.0)
    )
    v[:, 1] -= w_brow_zone * 0.34 + w_inner_brow * 0.22
    v[:, 2] += w_brow_zone * 0.32 + w_inner_brow * 0.28

    # 5. Narrower, slightly hooded intense eyes
    for eye_key in ("eye_l", "eye_r"):
        ring = LANDMARKS[eye_key]
        # Indices 0..8 are corner-to-corner lower lid; 9..15 are upper lid
        upper = ring[9:]
        lower = ring[1:8]
        v[upper, 1] -= 0.14
        v[upper, 2] += 0.08
        v[lower, 1] += 0.05

    # 6. Refined straight nasal bridge
    w_nose_bridge = (
        np.exp(-((y - 1.5) / 2.1) ** 2)
        * np.exp(-(ax / 1.25) ** 2)
        * np.clip((z - 4.2) / 2.0, 0.0, 1.0)
    )
    v[:, 0] -= x * w_nose_bridge * 0.10
    v[:, 2] += np.exp(-((y - 1.8) / 1.1) ** 2) * np.exp(-(ax / 0.85) ** 2) * 0.22

    # 7. Firm closed resting lips & defined Cupid's bow
    li = LANDMARKS["lips_in"]
    # Bring lower inner lip (1..9) up and upper inner lip (11..19) down so they meet
    mid_y = 0.5 * (v[li[5], 1] + v[li[15], 1])
    for k in range(1, 10):
        t = math.sin(math.pi * k / 10.0) ** 0.7
        v[li[k], 1] = v[li[k], 1] * (1.0 - 0.82 * t) + (mid_y - 0.015) * (0.82 * t)
    for k in range(11, 20):
        t = math.sin(math.pi * (k - 10) / 10.0) ** 0.7
        v[li[k], 1] = v[li[k], 1] * (1.0 - 0.82 * t) + (mid_y + 0.015) * (0.82 * t)
    # Slightly bring outer lips closer to match the closed inner seam
    lo = LANDMARKS["lips_out"]
    for k in range(1, 10):
        t = math.sin(math.pi * k / 10.0) ** 0.8
        v[lo[k], 1] += 0.14 * t
    for k in range(11, 20):
        t = math.sin(math.pi * (k - 10) / 10.0) ** 0.8
        v[lo[k], 1] -= 0.12 * t
    # Slight firm downturn at the mouth corners
    v[lo[0], 1] -= 0.06
    v[lo[10], 1] -= 0.06
    v[li[0], 1] -= 0.06
    v[li[10], 1] -= 0.06

    return v


def _catmull_rom(pts: np.ndarray, n_samples: int) -> np.ndarray:
    """Evaluate a smooth Catmull-Rom spline through 3D control points."""
    p = np.asarray(pts, dtype=np.float64)
    # Duplicate endpoints for tangent continuity
    ext = np.vstack([2.0 * p[0] - p[1], p, 2.0 * p[-1] - p[-2]])
    segs = len(p) - 1
    ts = np.linspace(0.0, segs, n_samples, endpoint=True)
    out = np.empty((n_samples, 3), dtype=np.float64)
    for k, u in enumerate(ts):
        i = min(int(u), segs - 1)
        t = u - i
        t2, t3 = t * t, t * t * t
        p0, p1, p2, p3 = ext[i], ext[i + 1], ext[i + 2], ext[i + 3]
        out[k] = 0.5 * (
            (2.0 * p1)
            + (-p0 + p2) * t
            + (2.0 * p0 - 5.0 * p1 + 4.0 * p2 - p3) * t2
            + (-p0 + 3.0 * p1 - 3.0 * p2 + p3) * t3
        )
    return out


def _build_leon_hair(head_verts: np.ndarray):
    """Build Leon S. Kennedy's layered 3D curtain hair in raw OBJ coordinates.

    Consists of:
      1. A sculpted hair cap over the crown/sides/back with an off-center right part.
      2. Swept 3D triangular-prism locks (left/right edge + raised center spine)
         forming the signature asymmetrical bangs over the viewer's left eye,
         swept right curtain, temple/cheek framing layers, and nape strands.
      3. Longitudinal strand polylines following every lock for silky HUD lines.
    """
    verts_list: list[np.ndarray] = []
    faces_list: list[list[int]] = []
    outward_list: list[np.ndarray] = []
    t_list: list[np.ndarray] = []       # 0 = root, 1 = feathered tip
    layer_list: list[int] = []          # per-triangle layer priority for clean sorting
    strand_list: list[np.ndarray] = []  # index chains for longitudinal strand lines

    skull_c = np.array([0.0, 2.5, -1.2], dtype=np.float64)

    def add_lock(ctrl_pts, w_max: float, thickness: float, n_seg: int = 10,
                 w_root_frac: float = 0.72, tip_taper: float = 0.85,
                 twist_bias: np.ndarray | None = None, layer: int = 1):
        pts = _catmull_rom(ctrl_pts, n_seg + 1)
        tang = np.gradient(pts, axis=0)
        tang /= np.maximum(np.linalg.norm(tang, axis=1, keepdims=True), 1e-9)

        # Outward normal points radially away from the skull center, orthogonalized
        # against the strand tangent (biased slightly forward for front bangs).
        rad = pts - skull_c
        if twist_bias is not None:
            rad = rad + twist_bias[None, :]
        rad /= np.maximum(np.linalg.norm(rad, axis=1, keepdims=True), 1e-9)
        nrm = rad - (rad * tang).sum(1, keepdims=True) * tang
        nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-9)
        side = np.cross(tang, nrm)
        side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)

        u = np.linspace(0.0, 1.0, n_seg + 1)
        # Smooth bell-to-pointed-tip width profile
        cos_tail = np.maximum(0.0, np.cos(((u - 0.58) / 0.42) * (np.pi * 0.5)))
        taper_tail = np.where(u < 0.58, 1.0, cos_tail ** tip_taper)
        w = w_max * (w_root_frac + (1.0 - w_root_frac) * np.sin(np.pi * np.minimum(u / 0.7, 1.0)) ** 0.6) * taper_tail
        th = thickness * (0.55 + 0.45 * np.sin(np.pi * np.minimum(u / 0.75, 1.0))) * taper_tail

        base = sum(len(a) for a in verts_list)
        # 3 vertices per station (left, raised spine, right) except final tip vertex
        ring_verts = []
        ring_out = []
        ring_t = []
        spine_idx = []
        left_idx = []
        right_idx = []

        for k in range(n_seg):
            p_c = pts[k]
            s_v = side[k] * (w[k] * 0.5)
            n_v = nrm[k] * th[k]
            vL = p_c - s_v
            vM = p_c + n_v
            vR = p_c + s_v
            idx0 = base + len(ring_verts)
            ring_verts.extend([vL, vM, vR])
            ring_out.extend([nrm[k] - side[k] * 0.25, nrm[k], nrm[k] + side[k] * 0.25])
            ring_t.extend([u[k], u[k], u[k]])
            left_idx.append(idx0)
            spine_idx.append(idx0 + 1)
            right_idx.append(idx0 + 2)

        # Sharp feathered tip point
        tip_idx = base + len(ring_verts)
        ring_verts.append(pts[-1])
        ring_out.append(nrm[-1])
        ring_t.append(1.0)
        left_idx.append(tip_idx)
        spine_idx.append(tip_idx)
        right_idx.append(tip_idx)

        for k in range(n_seg - 1):
            l0, m0, r0 = left_idx[k], spine_idx[k], right_idx[k]
            l1, m1, r1 = left_idx[k + 1], spine_idx[k + 1], right_idx[k + 1]
            faces_list.append([l0, l1, m1])
            faces_list.append([l0, m1, m0])
            faces_list.append([m0, m1, r1])
            faces_list.append([m0, r1, r0])
            layer_list.extend([layer, layer, layer, layer])
        # Tip cap triangles
        l0, m0, r0 = left_idx[-2], spine_idx[-2], right_idx[-2]
        faces_list.append([l0, tip_idx, m0])
        faces_list.append([m0, tip_idx, r0])
        layer_list.extend([layer, layer])

        verts_list.append(np.array(ring_verts, dtype=np.float64))
        outward_list.append(np.array(ring_out, dtype=np.float64))
        t_list.append(np.array(ring_t, dtype=np.float64))
        strand_list.append(np.array(spine_idx, dtype=np.int32))
        if w_max >= 1.8:
            strand_list.append(np.array(left_idx, dtype=np.int32))

    # ── 1. Base sculpted hair cap (crown & occiput volume, keeps forehead open)
    n_u, n_v = 11, 20
    cap_v = np.empty((n_u, n_v, 3), dtype=np.float64)
    cap_o = np.empty((n_u, n_v, 3), dtype=np.float64)
    cap_t = np.empty((n_u, n_v), dtype=np.float64)
    phis = np.linspace(-0.92 * np.pi, 0.92 * np.pi, n_v)   # -pi back-left -> 0 front -> +pi back-right
    thetas = np.linspace(0.06, 1.0, n_u)
    part_phi = 0.24

    for iu, th in enumerate(thetas):
        for iv, ph in enumerate(phis):
            # Stay high above the forehead in front (front_w ~ 1), sweep low at sides/back
            front_w = np.exp(-(ph / 0.85) ** 2)
            part_dip = np.exp(-((ph - part_phi) / 0.26) ** 2) * front_w
            ang_max = 0.72 + 1.28 * (1.0 - front_w) - 0.12 * part_dip
            ang_y = max(0.05, min(2.05, th * ang_max))
            sx = np.sin(ang_y) * np.sin(ph)
            sy = np.cos(ang_y)
            sz = np.sin(ang_y) * np.cos(ph)
            d = np.array([sx, sy, sz], dtype=np.float64)

            rx, ry, rz = 8.35, 10.0, 8.45
            side_bulge = 1.0 + 0.03 * (np.sin(ang_y) ** 1.3) * (1.0 - 0.3 * front_w)
            top_lift = 1.0 + 0.07 * (1.0 - th) - 0.05 * part_dip * (1.0 - th)
            pos = np.array([0.0, 2.2, -1.2]) + d * np.array([rx * side_bulge, ry * top_lift, rz])
            if pos[1] < -2.0 and pos[2] < -1.0:
                pos[0] *= 0.88
            cap_v[iu, iv] = pos
            cap_o[iu, iv] = d
            cap_t[iu, iv] = 0.12 + 0.45 * th

    cap_base = sum(len(a) for a in verts_list)
    verts_list.append(cap_v.reshape(-1, 3))
    outward_list.append(cap_o.reshape(-1, 3))
    t_list.append(cap_t.reshape(-1))
    for iu in range(n_u - 1):
        for iv in range(n_v - 1):
            a = cap_base + iu * n_v + iv
            b = a + 1
            c = a + n_v
            d_i = c + 1
            faces_list.append([a, c, d_i])
            faces_list.append([a, d_i, b])
            layer_list.extend([0, 0])

    # ── 2. Viewer's LEFT Curtain & Iconic Eye-Framing Bangs (x < 0) ─────────
    front_bias = np.array([0.0, 0.15, 2.8], dtype=np.float64)
    # L0 (layer 3): sweeps diagonally from part across inner-left brow
    add_lock([
        [1.8, 9.8, 5.55],
        [-0.2, 7.9, 6.55],
        [-1.9, 5.5, 6.10],
        [-2.8, 3.6, 5.40],
        [-3.0, 2.0, 4.95],
    ], w_max=1.35, thickness=0.40, n_seg=14, twist_bias=front_bias, layer=3)

    # L1 (layer 2): signature feather lock grazing outer-upper left eye
    add_lock([
        [1.7, 10.2, 5.15],
        [-0.7, 8.2, 6.25],
        [-2.8, 5.4, 5.70],
        [-3.8, 3.0, 4.95],
        [-3.9, 1.1, 4.45],
    ], w_max=1.85, thickness=0.46, n_seg=14, twist_bias=front_bias, layer=2)

    # L2 (layer 1): main heavy curtain framing outer left eye & upper cheek
    add_lock([
        [1.5, 10.6, 4.65],
        [-1.5, 8.7, 5.90],
        [-4.0, 5.5, 5.25],
        [-4.8, 2.7, 4.40],
        [-4.5, 0.5, 3.90],
    ], w_max=2.35, thickness=0.56, n_seg=14, twist_bias=front_bias, layer=1)

    # L3 (layer 1): temple drape along left cheekbone
    add_lock([
        [1.1, 11.1, 4.00],
        [-2.5, 9.2, 5.25],
        [-5.2, 5.6, 4.35],
        [-5.8, 2.3, 3.45],
        [-5.2, -0.3, 2.85],
    ], w_max=2.75, thickness=0.60, n_seg=13, twist_bias=np.array([-1.0, 0.1, 1.8]), layer=1)

    # L4 (layer 1): outer parietal hugging temple & cheek smoothly (zero gap)
    add_lock([
        [0.4, 11.4, 3.15],
        [-3.4, 9.4, 4.25],
        [-6.0, 5.2, 3.30],
        [-6.4, 1.5, 2.35],
        [-5.7, -1.3, 1.75],
    ], w_max=2.95, thickness=0.58, n_seg=13, twist_bias=np.array([-1.2, 0.0, 1.6]), layer=1)

    # L5 (layer 0): temple/ear framing tucked seamlessly behind L4
    add_lock([
        [-0.7, 11.4, 1.95],
        [-4.3, 9.0, 2.85],
        [-6.5, 4.8, 1.75],
        [-6.5, 0.6, 0.95],
        [-5.8, -1.9, 0.45],
    ], w_max=3.10, thickness=0.52, n_seg=12, layer=0)

    # Fine foreground highlight wisp over L1/L2 ridge
    add_lock([
        [1.5, 10.0, 5.50],
        [-0.9, 7.9, 6.65],
        [-3.0, 5.1, 6.05],
        [-4.0, 2.6, 5.20],
        [-4.1, 0.9, 4.70],
    ], w_max=0.92, thickness=0.32, n_seg=13, twist_bias=front_bias, layer=4)

    # ── 3. Viewer's RIGHT Curtain (x > 0, sweeping smoothly from part) ──────
    add_lock([
        [1.9, 9.8, 5.30],
        [3.6, 8.1, 5.75],
        [4.8, 5.5, 5.05],
        [5.0, 2.9, 4.30],
        [4.5, 1.1, 3.85],
    ], w_max=2.05, thickness=0.48, n_seg=13, twist_bias=front_bias, layer=2)

    add_lock([
        [1.8, 10.4, 4.85],
        [4.2, 8.7, 5.20],
        [5.7, 5.5, 4.25],
        [5.9, 2.3, 3.40],
        [5.3, 0.0, 2.85],
    ], w_max=2.70, thickness=0.58, n_seg=13, twist_bias=np.array([1.0, 0.1, 1.8]), layer=1)

    add_lock([
        [1.5, 11.0, 4.10],
        [4.5, 9.1, 4.30],
        [6.2, 5.2, 3.30],
        [6.4, 1.5, 2.30],
        [5.7, -1.3, 1.75],
    ], w_max=2.95, thickness=0.58, n_seg=13, twist_bias=np.array([1.2, 0.0, 1.6]), layer=1)

    add_lock([
        [0.9, 11.4, 2.95],
        [4.6, 9.0, 3.00],
        [6.6, 4.8, 1.75],
        [6.5, 0.6, 0.95],
        [5.8, -1.9, 0.45],
    ], w_max=3.10, thickness=0.52, n_seg=12, layer=0)

    add_lock([
        [2.0, 10.1, 5.55],
        [4.1, 8.2, 5.85],
        [5.3, 5.3, 4.80],
        [5.4, 2.5, 3.90],
        [4.8, 0.7, 3.40],
    ], w_max=0.95, thickness=0.33, n_seg=13, twist_bias=front_bias, layer=3)

    # ── 4. Crown Peak & Side-Back Nape Layers (closed cleanly at the part) ──
    add_lock([
        [2.1, 10.4, 4.35],
        [-0.2, 11.7, 2.10],
        [-3.5, 10.5, -0.50],
        [-6.5, 5.8, -1.80],
        [-6.6, -0.4, -2.00],
        [-5.8, -4.0, -2.10],
    ], w_max=3.2, thickness=0.64, n_seg=12, layer=0)

    add_lock([
        [1.7, 10.5, 4.25],
        [3.6, 11.4, 1.90],
        [5.9, 9.3, -0.40],
        [6.8, 4.8, -1.70],
        [6.7, -0.6, -2.00],
        [5.8, -4.0, -2.10],
    ], w_max=3.2, thickness=0.64, n_seg=12, layer=0)

    # Rear side/nape locks behind the ears
    for sgn in (-1.0, 1.0):
        add_lock([
            [sgn * 2.2, 10.5, -1.0],
            [sgn * 5.8, 7.8, -3.5],
            [sgn * 7.2, 2.6, -4.4],
            [sgn * 6.5, -2.6, -4.0],
            [sgn * 5.3, -5.8, -3.5],
        ], w_max=3.1, thickness=0.65, n_seg=10, layer=0)

        add_lock([
            [sgn * 0.6, 9.6, -4.8],
            [sgn * 2.4, 5.8, -7.2],
            [sgn * 3.5, 0.2, -7.5],
            [sgn * 3.4, -4.5, -6.2],
            [sgn * 2.8, -7.0, -5.0],
        ], w_max=3.4, thickness=0.60, n_seg=10, layer=0)

    hv = np.vstack(verts_list)
    hf = np.array(faces_list, dtype=np.int32)
    ho = np.vstack(outward_list)
    ht = np.concatenate(t_list)
    h_layer = np.array(layer_list, dtype=np.float32)
    hn = _vertex_normals(hv, hf, ho)
    return hv, hf, hn, ht, h_layer, strand_list


def _build_leon_collar():
    """Compact upturned aviator/bomber collar hugging the base of the neck,
    fading out cleanly at the bottom edge like the neck stub."""
    verts_list: list[np.ndarray] = []
    faces_list: list[list[int]] = []
    outward_list: list[np.ndarray] = []
    fade_list: list[np.ndarray] = []

    # Open horseshoe collar wrapping from front-left around the back to front-right
    n_u, n_v = 5, 19
    phis = np.linspace(-0.84 * np.pi, 0.84 * np.pi, n_v)  # 0 = back (-z), +-pi = front (+z)
    # Build in raw coords: y from -8.0 (top collar rim) down to -12.9 (faded base)
    us = np.linspace(0.0, 1.0, n_u)
    cv = np.empty((n_u, n_v, 3), dtype=np.float64)
    co = np.empty((n_u, n_v, 3), dtype=np.float64)
    cf = np.empty((n_u, n_v), dtype=np.float64)

    for iu, u in enumerate(us):
        # Collar opens softly at the front throat, sits lower like Leon's open bomber collar
        for iv, ph in enumerate(phis):
            backness = 0.5 * (1.0 + np.cos(ph))  # 1 at back, 0 at front throat
            y_top = -10.2 + 0.7 * backness - 1.4 * (1.0 - backness) ** 1.8
            y_bot = -13.1
            y = y_top * (1.0 - u) + y_bot * u
            # Open gently outward like shearling lapels
            rim_flare = 1.0 + 0.24 * (1.0 - u) ** 1.3
            rx = (6.5 + 2.4 * (u ** 1.3)) * rim_flare
            rz = (5.4 + 1.8 * (u ** 1.3)) * rim_flare
            x = rx * np.sin(ph)
            z = _NECK_Z - rz * np.cos(ph)
            cv[iu, iv] = [x, y, z]
            co[iu, iv] = [np.sin(ph), 0.22 * (1.0 - u), -np.cos(ph)]
            cf[iu, iv] = (0.58 - 0.48 * (u ** 1.3)) * (0.55 + 0.45 * backness)

    verts_list.append(cv.reshape(-1, 3))
    outward_list.append(co.reshape(-1, 3))
    fade_list.append(cf.reshape(-1))
    for iu in range(n_u - 1):
        for iv in range(n_v - 1):
            a = iu * n_v + iv
            b = a + 1
            c = a + n_v
            d = c + 1
            faces_list.append([a, b, d])
            faces_list.append([a, d, c])

    v = np.vstack(verts_list)
    f = np.array(faces_list, dtype=np.int32)
    o = np.vstack(outward_list)
    n = _vertex_normals(v, f, o)
    # Top rim polyline for crisp subtle lapel edge
    rim = np.arange(n_v, dtype=np.int32)
    return v, f, n, fade_list[0], rim


def _check_landmarks(verts: np.ndarray) -> None:
    """Fail loudly at build time if a landmark ring is not where it should be."""
    for left, right in (("eye_l", "eye_r"), ("brow_l", "brow_r")):
        cl = verts[LANDMARKS[left]].mean(0)
        cr = verts[LANDMARKS[right]].mean(0)
        assert cl[0] < 0 < cr[0], f"{left}/{right} are not on opposite sides"
        assert abs(cl[1] - cr[1]) < 0.5, f"{left}/{right} are at different heights"
    eye_y = verts[LANDMARKS["eye_l"]].mean(0)[1]
    brow_y = verts[LANDMARKS["brow_l"]].mean(0)[1]
    lips = verts[LANDMARKS["lips_out"]].mean(0)
    assert brow_y > eye_y, "brow is not above the eye"
    assert lips[1] < eye_y, "lips are not below the eyes"
    assert abs(lips[0]) < 0.5, "lips are not centred"


def build_head() -> dict:
    """Assemble the full head. Called once; `get_head_mesh()` caches the result."""
    verts, faces = _load_obj(_OBJ)
    verts = _sculpt_leon_face(verts)
    _check_landmarks(verts)

    n_face = len(verts)
    verts, faces = _add_cranium(verts, faces)
    n_head = len(verts)

    # Build Leon's 3D hair and compact collar in the same raw OBJ coordinate space
    hair_v, hair_f, hair_n, hair_t, hair_layer, hair_strands = _build_leon_hair(verts[:n_head])
    col_v, col_f, col_n, col_fade, col_rim = _build_leon_collar()

    verts, faces, fade = _add_neck(verts, faces)

    # ── normalise: top of hair/crown → +1, chin → -1, eyes land on y ≈ 0 ─────
    head_y = verts[:n_head, 1]
    crown = max(float(head_y.max()), float(hair_v[:, 1].max()))
    chin = float(head_y.min())
    scale = 2.0 / (crown - chin)
    centre = np.array([0.0, (crown + chin) * 0.5, 0.0])
    verts = (verts - centre) * scale
    hair_v = (hair_v - centre) * scale
    col_v = (col_v - centre) * scale

    # Outward reference, per part: the head is star-shaped about its own centre,
    # while the neck is a tube whose outward direction is radial in x/z only.
    outward = verts - np.array([0.0, verts[:n_head, 1].mean(), 0.0])
    outward[n_head:] = verts[n_head:] - np.array([0.0, 0.0, _NECK_Z * scale])
    outward[n_head:, 1] = 0.0
    normals = _vertex_normals(verts, faces, outward)

    # ── jaw rig ─────────────────────────────────────────────────────────────
    # Everything below the mouth swings on the mandible, tapering to nothing at
    # the ears and around the back so the nape and the neck stay put.
    mouth_y = verts[LANDMARKS["lips_out"], 1].mean()
    chin_y = verts[:n_head, 1].min()
    jaw = np.clip((mouth_y - verts[:, 1]) / (mouth_y - chin_y), 0.0, 1.0) ** 0.8
    jaw *= np.clip(0.30 + 0.85 * (verts[:, 2] / 0.55), 0.0, 1.0)
    jaw[n_head:] = 0.0                                  # the neck never moves
    jaw[LANDMARKS["lips_in"][:10]] = 1.0                # lower inner lip leads
    jaw[LANDMARKS["lips_out"][:10]] = 0.95

    # ── brow rig ────────────────────────────────────────────────────────────
    # Raising the brows displaces the actual surface rather than sliding a drawn
    # line over it, so the brow ridge relights as it lifts.
    brow_y = verts[LANDMARKS["brow_l"] + LANDMARKS["brow_r"], 1].mean()
    brow = np.exp(-((verts[:, 1] - brow_y) / 0.115) ** 2)
    brow *= np.clip(verts[:, 2] / 0.35, 0.0, 1.0)       # front of the face only
    brow *= np.exp(-(verts[:, 0] / 0.42) ** 2)          # fades out past the temples
    brow[n_head:] = 0.0

    # ── lip rig ─────────────────────────────────────────────────────────────
    # Vowels are not just "how far open" — /i/ spreads the lips wide, /u/ purses
    # them forward. This weight lets the renderer widen or round the mouth
    # region as a whole, so the surrounding skin follows instead of tearing away
    # from the landmark rings.
    lip_c = verts[LANDMARKS["lips_out"]].mean(axis=0)
    lips = np.exp(-((verts[:, 1] - lip_c[1]) / 0.155) ** 2)
    lips *= np.exp(-(verts[:, 0] / 0.30) ** 2)
    lips *= np.clip(verts[:, 2] / 0.40, 0.0, 1.0)
    lips[n_head:] = 0.0

    edges = _unique_edges(faces)[::_WIRE_STRIDE]

    # Neck and head interpenetrate, and a painter's-algorithm sort by triangle
    # depth interleaves them into a torn edge. Grouping fixes it: the neck is
    # always behind the head where they overlap, so draw every neck facet first.
    face_group = (faces >= n_head).all(axis=1).astype(np.int32)   # 1 = neck

    span_min = min(float(verts[:, 1].min()), float(col_v[:, 1].min()))

    return {
        "face_group": np.ascontiguousarray(1 - face_group, dtype=np.float32),
        "brow": np.ascontiguousarray(brow, dtype=np.float32),
        "lips": np.ascontiguousarray(lips, dtype=np.float32),
        "lip_centre": np.ascontiguousarray(lip_c, dtype=np.float32),
        "verts": np.ascontiguousarray(verts, dtype=np.float32),
        "normals": np.ascontiguousarray(normals, dtype=np.float32),
        "faces": np.ascontiguousarray(faces, dtype=np.int32),
        "edges": np.ascontiguousarray(edges, dtype=np.int32),
        "jaw": np.ascontiguousarray(jaw, dtype=np.float32),
        "fade": np.ascontiguousarray(fade, dtype=np.float32),
        "landmarks": {k: np.array(v, dtype=np.int32) for k, v in LANDMARKS.items()},
        "n_face": n_face,
        "n_head": n_head,
        "span": (1.0, span_min),                        # top of hair, bottom of neck/collar
        "hair_verts": np.ascontiguousarray(hair_v, dtype=np.float32),
        "hair_normals": np.ascontiguousarray(hair_n, dtype=np.float32),
        "hair_faces": np.ascontiguousarray(hair_f, dtype=np.int32),
        "hair_t": np.ascontiguousarray(hair_t, dtype=np.float32),
        "hair_layer": np.ascontiguousarray(hair_layer, dtype=np.float32),
        "hair_strands": hair_strands,
        "collar_verts": np.ascontiguousarray(col_v, dtype=np.float32),
        "collar_normals": np.ascontiguousarray(col_n, dtype=np.float32),
        "collar_faces": np.ascontiguousarray(col_f, dtype=np.int32),
        "collar_fade": np.ascontiguousarray(col_fade, dtype=np.float32),
        "collar_rim": col_rim,
    }


_CACHE: dict | None = None


def get_head_mesh() -> dict:
    """Process-wide cached mesh — every HudCanvas shares the same arrays."""
    global _CACHE
    if _CACHE is None:
        _CACHE = build_head()
    return _CACHE
