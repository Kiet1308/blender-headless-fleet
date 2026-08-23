"""Run one isolated Blender modeling job in background mode.

The dispatcher starts a fresh Blender process per job and points it at a
job-local JSON request.  Nothing in this file relies on the UI or on a TCP
port, so several jobs can run independently at the same time.
"""

from __future__ import annotations

import json
import math
import os
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

import bpy
from mathutils import Vector


JOB_FILE = Path(os.environ["BLENDER_FLEET_JOB"])
JOB_DIR = JOB_FILE.parent
STATUS_FILE = JOB_DIR / "status.json"
RESULT_FILE = JOB_DIR / "result.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def write_json(path: Path, payload: dict) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    temp.replace(path)


def status(state: str, **extra: object) -> None:
    payload = {"state": state, "updated_at": utc_now(), **extra}
    write_json(STATUS_FILE, payload)


def make_material(name: str, color: list[float], metallic: float = 0.0, roughness: float = 0.45):
    material = bpy.data.materials.new(name)
    material.diffuse_color = (*color, 1.0)
    material.use_nodes = True
    principled = material.node_tree.nodes.get("Principled BSDF")
    if principled:
        principled.inputs["Base Color"].default_value = (*color, 1.0)
        principled.inputs["Metallic"].default_value = metallic
        principled.inputs["Roughness"].default_value = roughness
    return material


def assign_material(obj, material) -> None:
    if obj.data and hasattr(obj.data, "materials"):
        obj.data.materials.append(material)


def add_cube(name: str, location: tuple[float, float, float], scale: tuple[float, float, float], material):
    bpy.ops.mesh.primitive_cube_add(location=location)
    obj = bpy.context.object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(obj, material)
    return obj


def add_uv_sphere(name: str, location: tuple[float, float, float], radius: float, material):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=radius, location=location)
    obj = bpy.context.object
    obj.name = name
    bpy.ops.object.shade_smooth()
    assign_material(obj, material)
    return obj


def create_model(job: dict) -> None:
    kind = str(job.get("kind", "cube")).lower()
    color = job.get("color", [0.15, 0.45, 0.95])
    if not isinstance(color, list) or len(color) != 3:
        color = [0.15, 0.45, 0.95]
    color = [max(0.0, min(1.0, float(value))) for value in color]
    material = make_material("Primary", color, metallic=0.15 if kind in {"robot", "tower"} else 0.0)
    accent = make_material("Accent", [min(1.0, color[0] + 0.35), min(1.0, color[1] + 0.35), min(1.0, color[2] + 0.35)], metallic=0.3)

    if kind == "cube":
        add_cube("MainCube", (0, 0, 1), (1.0, 1.0, 1.0), material)
    elif kind == "sphere":
        add_uv_sphere("MainSphere", (0, 0, 1), 1.0, material)
    elif kind == "monkey":
        bpy.ops.mesh.primitive_monkey_add(location=(0, 0, 1))
        obj = bpy.context.object
        obj.name = "Suzanne"
        obj.scale = (1.35, 1.35, 1.35)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        bpy.ops.object.modifier_add(type="SUBSURF")
        obj.modifiers[-1].levels = 2
        bpy.ops.object.shade_smooth()
        assign_material(obj, material)
    elif kind == "tower":
        for index in range(4):
            width = 1.25 - index * 0.18
            add_cube(f"Tower_{index + 1}", (0, 0, 0.65 + index * 1.3), (width, width, 0.6), material if index % 2 else accent)
        for index in range(4):
            add_cube(f"TowerAccent_{index + 1}", (0, -1.27 + index * 0.01, 0.65 + index * 1.3), (0.32, 0.04, 0.18), accent)
    elif kind == "robot":
        add_cube("Body", (0, 0, 1.55), (0.72, 0.5, 0.85), material)
        add_cube("Head", (0, 0, 2.75), (0.58, 0.48, 0.45), accent)
        add_cube("LeftArm", (-0.95, 0, 1.55), (0.2, 0.28, 0.65), material)
        add_cube("RightArm", (0.95, 0, 1.55), (0.2, 0.28, 0.65), material)
        add_cube("LeftLeg", (-0.35, 0, 0.25), (0.25, 0.3, 0.55), material)
        add_cube("RightLeg", (0.35, 0, 0.25), (0.25, 0.3, 0.55), material)
        add_uv_sphere("EyeLeft", (-0.22, -0.46, 2.82), 0.1, accent)
        add_uv_sphere("EyeRight", (0.22, -0.46, 2.82), 0.1, accent)
    else:
        raise ValueError(f"Unsupported model kind: {kind}")

    bpy.ops.mesh.primitive_plane_add(size=20, location=(0, 0, -0.02))
    floor = bpy.context.object
    floor.name = "Ground"
    assign_material(floor, make_material("GroundMaterial", [0.035, 0.045, 0.06], roughness=0.8))


def point_camera(camera, target: tuple[float, float, float]) -> None:
    direction = Vector(target) - camera.location
    camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()


def setup_scene(job: dict) -> None:
    scene = bpy.context.scene
    bpy.ops.object.camera_add(location=(6.8, -8.0, 5.7))
    camera = bpy.context.object
    camera.name = "Camera"
    point_camera(camera, (0, 0, 1.2))
    scene.camera = camera

    bpy.ops.object.light_add(type="AREA", location=(3.5, -4.0, 7.0))
    key = bpy.context.object
    key.name = "KeyLight"
    key.data.energy = 950
    key.data.shape = "DISK"
    key.data.size = 5.0
    point_camera(key, (0, 0, 1.0))

    bpy.ops.object.light_add(type="AREA", location=(-4.0, -1.0, 3.5))
    fill = bpy.context.object
    fill.name = "FillLight"
    fill.data.energy = 450
    fill.data.size = 4.0
    point_camera(fill, (0, 0, 1.0))

    # Blender 4.x commonly exposes BLENDER_EEVEE_NEXT; this Blender 5.2 build
    # exposes BLENDER_EEVEE. Pick the first engine supported by the process.
    for engine in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE", "CYCLES"):
        try:
            scene.render.engine = engine
            break
        except TypeError:
            continue
    scene.render.resolution_x = int(job.get("resolution", 384))
    scene.render.resolution_y = int(job.get("resolution", 384))
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.film_transparent = False
    if scene.world is None:
        scene.world = bpy.data.worlds.new("World")
    scene.world.color = (0.015, 0.02, 0.035)


def main() -> int:
    started = time.perf_counter()
    request = json.loads(JOB_FILE.read_text(encoding="utf-8"))
    status("running", job_id=request.get("job_id"), pid=os.getpid())
    try:
        bpy.ops.wm.read_factory_settings(use_empty=True)
        create_model(request)
        setup_scene(request)
        blend_path = JOB_DIR / "scene.blend"
        render_path = JOB_DIR / "preview.png"
        bpy.context.scene.render.filepath = str(render_path)
        bpy.ops.wm.save_as_mainfile(filepath=str(blend_path))
        bpy.ops.render.render(write_still=True)
        result = {
            "state": "succeeded",
            "job_id": request.get("job_id"),
            "kind": request.get("kind"),
            "blend_file": str(blend_path),
            "preview_file": str(render_path),
            "objects": len(bpy.data.objects),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "finished_at": utc_now(),
        }
        write_json(RESULT_FILE, result)
        status("succeeded", **{k: v for k, v in result.items() if k != "state"})
        return 0
    except Exception as exc:
        result = {
            "state": "failed",
            "job_id": request.get("job_id"),
            "error": str(exc),
            "traceback": traceback.format_exc(),
            "duration_seconds": round(time.perf_counter() - started, 3),
            "finished_at": utc_now(),
        }
        write_json(RESULT_FILE, result)
        status("failed", error=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
