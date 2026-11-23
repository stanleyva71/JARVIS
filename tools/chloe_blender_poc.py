from __future__ import annotations

import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MODEL_PATH = PROJECT_ROOT / "chloe_detroit_become_human.glb"
OUTPUT_DIR = PROJECT_ROOT / "preview_output"
OUTPUT_PATH = OUTPUT_DIR / "chloe_bust_preview.png"
BLEND_PATH = OUTPUT_DIR / "chloe_bust_preview.blend"

KEPT_OBJECTS = {
    "Object_7",   # eyelashes
    "Object_11",  # body
    "Object_13",  # eye caruncles
    "Object_15",  # dress
    "Object_17",  # eyes
    "Object_19",  # head
    "Object_21",  # temple LED
    "Object_23",  # mouth
    "Object_25",  # brows
    "Object_27",  # hair
}


def clear_scene() -> None:
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    for datablocks in (
        bpy.data.meshes,
        bpy.data.curves,
        bpy.data.metaballs,
        bpy.data.cameras,
        bpy.data.lights,
        bpy.data.materials,
    ):
        for datablock in list(datablocks):
            if datablock.users == 0:
                datablocks.remove(datablock)


def import_model() -> list[bpy.types.Object]:
    if not MODEL_PATH.is_file():
        raise FileNotFoundError(MODEL_PATH)

    bpy.ops.import_scene.gltf(filepath=str(MODEL_PATH))

    kept: list[bpy.types.Object] = []
    for obj in list(bpy.context.scene.objects):
        if obj.type != "MESH":
            continue

        if obj.name in KEPT_OBJECTS:
            kept.append(obj)
        else:
            bpy.data.objects.remove(obj, do_unlink=True)

    for obj in kept:
        obj.visible_shadow = True
        obj.visible_glossy = True

    return kept


def make_area_light(
    name: str,
    location: tuple[float, float, float],
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> bpy.types.Object:
    light_data = bpy.data.lights.new(name=name, type="AREA")
    light_data.energy = energy
    light_data.shape = "DISK"
    light_data.size = size
    light_data.color = color

    light = bpy.data.objects.new(name=name, object_data=light_data)
    bpy.context.collection.objects.link(light)
    light.location = location
    return light


def point_at(obj: bpy.types.Object, target: Vector) -> None:
    direction = target - obj.location
    obj.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def configure_led() -> None:
    for material in bpy.data.materials:
        if "led" not in material.name.lower():
            continue

        material.use_nodes = True
        nodes = material.node_tree.nodes
        principled = next(
            (node for node in nodes if node.type == "BSDF_PRINCIPLED"),
            None,
        )
        if principled is None:
            continue

        for socket_name in ("Emission Color", "Emission"):
            if socket_name in principled.inputs:
                principled.inputs[socket_name].default_value = (0.10, 0.75, 1.0, 1.0)

        for socket_name in ("Emission Strength",):
            if socket_name in principled.inputs:
                principled.inputs[socket_name].default_value = 4.0


def combined_bounds(objects: list[bpy.types.Object]) -> tuple[Vector, Vector]:
    points: list[Vector] = []
    for obj in objects:
        for corner in obj.bound_box:
            points.append(obj.matrix_world @ Vector(corner))

    minimum = Vector((min(v.x for v in points), min(v.y for v in points),
                      min(v.z for v in points)))
    maximum = Vector((max(v.x for v in points), max(v.y for v in points),
                      max(v.z for v in points)))
    return minimum, maximum


def configure_scene(objects: list[bpy.types.Object]) -> bpy.types.Object:
    scene = bpy.context.scene
    scene.render.engine = "BLENDER_EEVEE"
    scene.render.resolution_x = 900
    scene.render.resolution_y = 900
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGBA"
    scene.render.film_transparent = False
    scene.render.filepath = str(OUTPUT_PATH)

    scene.world = bpy.data.worlds.new("ChloePreviewWorld")
    scene.world.use_nodes = True
    background = scene.world.node_tree.nodes.get("Background")
    if background is not None:
        background.inputs["Color"].default_value = (0.008, 0.018, 0.030, 1.0)
        background.inputs["Strength"].default_value = 0.15

    scene.view_settings.view_transform = "AgX"
    scene.view_settings.exposure = -1.25

    configure_led()

    minimum, maximum = combined_bounds(objects)
    center = (minimum + maximum) * 0.5
    bust_top = maximum.z
    bust_bottom = min(maximum.z - 0.65, minimum.z + 0.20)
    target = Vector((center.x, center.y, bust_bottom + (bust_top - bust_bottom) * 0.72))

    camera_data = bpy.data.cameras.new("ChloeBustCamera")
    camera = bpy.data.objects.new("ChloeBustCamera", camera_data)
    bpy.context.collection.objects.link(camera)
    camera.location = (target.x, target.y - 1.15, target.z)
    camera_data.type = "ORTHO"
    camera_data.ortho_scale = 1.18
    camera_data.lens = 55
    point_at(camera, target)
    scene.camera = camera

    key = make_area_light("SoftKey", (1.0, -1.2, target.z + 0.35), 180, 0.55,
                          (1.0, 0.88, 0.72))
    fill = make_area_light("BlueFill", (-1.0, -0.8, target.z + 0.15), 100, 0.65,
                           (0.35, 0.65, 1.0))
    rim = make_area_light("CyanRim", (0.0, 0.8, target.z + 0.50), 300, 0.45,
                          (0.20, 0.70, 1.0))
    point_at(key, target)
    point_at(fill, target)
    point_at(rim, target)

    scene.eevee.taa_render_samples = 64

    return camera


def render() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND_PATH))

    scene = bpy.context.scene
    camera = scene.camera
    target = Vector((0.0, 0.0, 2.136))
    radius = 1.15

    for index, angle in enumerate((0.0, math.pi * 0.5, math.pi, math.pi * 1.5), start=1):
        camera.location = (
            target.x + math.sin(angle) * radius,
            target.y + math.cos(angle) * radius,
            target.z,
        )
        point_at(camera, target)

        view_path = OUTPUT_DIR / f"chloe_bust_view_{index}.png"
        scene.render.filepath = str(view_path)
        bpy.ops.render.render(write_still=True)
        print(f"POC_VIEW_{index}={view_path}")

    camera.location = (target.x, target.y - radius, target.z)
    point_at(camera, target)
    scene.render.filepath = str(OUTPUT_PATH)
    bpy.ops.render.render(write_still=True)


def main() -> int:
    clear_scene()
    objects = import_model()
    configure_scene(objects)
    render()
    print(f"POC_RENDERED={OUTPUT_PATH}")
    print(f"POC_BLEND={BLEND_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
