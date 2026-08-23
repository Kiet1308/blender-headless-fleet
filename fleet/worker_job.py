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


def add_cylinder(name: str, location: tuple[float, float, float], radius: float, depth: float, material, rotation=(0.0, 0.0, 0.0)):
    bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=radius, depth=depth, location=location, rotation=rotation)
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    return obj


def add_cone(name: str, location: tuple[float, float, float], radius: float, depth: float, material):
    bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=radius, radius2=0.0, depth=depth, location=location)
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    return obj


def add_torus(name: str, location: tuple[float, float, float], major: float, minor: float, material):
    bpy.ops.mesh.primitive_torus_add(major_radius=major, minor_radius=minor, major_segments=48, minor_segments=12, location=location)
    obj = bpy.context.object
    obj.name = name
    assign_material(obj, material)
    return obj


def bevel(obj, width: float = 0.08) -> None:
    modifier = obj.modifiers.new("SoftEdges", "BEVEL")
    modifier.width = width
    modifier.segments = 3


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
    elif kind == "spaceship":
        body = add_cube("Fuselage", (0, 0, 1.35), (2.0, 0.62, 0.42), material)
        bevel(body, 0.16)
        add_cone("Nose", (2.25, 0, 1.35), 0.68, 1.4, accent).rotation_euler[1] = math.pi / 2
        cockpit = add_uv_sphere("Cockpit", (0.55, 0, 1.78), 0.58, accent)
        cockpit.scale = (1.25, 0.9, 0.45)
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        for side in (-1, 1):
            wing = add_cube(f"Wing_{side}", (-0.25, side * 1.25, 1.1), (1.15, 0.65, 0.08), material)
            wing.rotation_euler[0] = side * 0.08
            bevel(wing, 0.05)
            add_cylinder(f"Engine_{side}", (-1.8, side * 0.42, 1.05), 0.28, 1.05, accent, rotation=(0, math.pi / 2, 0))
            add_torus(f"EngineRing_{side}", (-1.8, side * 0.42, 1.05), 0.3, 0.06, material).rotation_euler[1] = math.pi / 2
            fin = add_cube(f"TailFin_{side}", (-1.25, side * 0.45, 1.95), (0.45, 0.08, 0.42), material)
            fin.rotation_euler[1] = side * 0.2
    elif kind == "castle":
        keep = add_cube("Keep", (0, 0, 1.45), (1.65, 1.65, 1.45), material)
        bevel(keep, 0.12)
        for index, (x, y) in enumerate(((-1.9, -1.9), (-1.9, 1.9), (1.9, -1.9), (1.9, 1.9)), start=1):
            add_cylinder(f"Turret_{index}", (x, y, 2.15), 0.62, 4.3, accent)
            add_cone(f"TurretRoof_{index}", (x, y, 4.65), 0.82, 1.45, material)
            for level in range(3):
                add_cube(f"TurretBand_{index}_{level}", (x, y - 0.64, 1.0 + level * 1.0), (0.16, 0.08, 0.14), material)
        add_cube("Gate", (0, -1.7, 0.85), (0.58, 0.12, 0.85), accent)
        for x in (-0.85, 0.85):
            for z in (1.5, 2.45):
                add_cube(f"Window_{x}_{z}", (x, -1.68, z), (0.16, 0.06, 0.28), accent)
        for x in (-1.1, 0, 1.1):
            for y in (-1.7, 1.7):
                add_cube(f"WallBattlement_{x}_{y}", (x, y, 3.0), (0.28, 0.18, 0.25), accent)
        for y in (-1.1, 0, 1.1):
            for x in (-1.7, 1.7):
                add_cube(f"SideBattlement_{x}_{y}", (x, y, 3.0), (0.18, 0.28, 0.25), accent)
    elif kind == "solar_system":
        sun_material = make_material("Sun", [1.0, 0.22, 0.03], metallic=0.0, roughness=0.2)
        sun = add_uv_sphere("Sun", (0, 0, 1.3), 0.9, sun_material)
        for index, (orbit, radius, planet_color, speed) in enumerate(((1.6, 0.22, [0.4, 0.65, 0.9], 0.6), (2.5, 0.34, [0.9, 0.45, 0.1], 0.35), (3.5, 0.48, [0.2, 0.8, 0.35], 0.2)), start=1):
            add_torus(f"Orbit_{index}", (0, 0, 1.3), orbit, 0.018, accent)
            angle = index * 0.9
            planet = add_uv_sphere(f"Planet_{index}", (math.cos(angle) * orbit, math.sin(angle) * orbit, 1.3), radius, make_material(f"PlanetMaterial_{index}", planet_color, roughness=0.55))
            if index == 3:
                add_torus("PlanetRing", (math.cos(angle) * orbit, math.sin(angle) * orbit, 1.3), 0.72, 0.04, accent).rotation_euler[0] = math.radians(68)
        add_uv_sphere("Moon", (3.9, 0.0, 1.65), 0.12, accent)
        bpy.ops.object.light_add(type="POINT", location=(0, 0, 2.0))
        bpy.context.object.data.energy = 1200
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
    started_at = utc_now()
    status("running", job_id=request.get("job_id"), pid=os.getpid(), started_at=started_at)
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
            "started_at": started_at,
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
            "started_at": started_at,
            "duration_seconds": round(time.perf_counter() - started, 3),
            "finished_at": utc_now(),
        }
        write_json(RESULT_FILE, result)
        status("failed", error=str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
