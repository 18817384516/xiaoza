"""Trusted Blender entrypoint; run with --background --factory-startup."""
from __future__ import annotations

import builtins
import json
import math
from pathlib import Path
import random
import sys
import traceback

import bpy
import bmesh
import mathutils
from mathutils import Vector

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from server.blender_policy import ALLOWED_MODULES, validate_script


def restricted_import(name, globals=None, locals=None, fromlist=(), level=0):
    if level or name not in ALLOWED_MODULES or any(item.startswith("_") for item in (fromlist or ())):
        raise ImportError("Only modeling modules are available")
    return {"bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils, "random": random}[name]


def run(request, output):
    code = request["code"]
    tree = validate_script(code)
    safe_names = ("abs", "all", "any", "bool", "dict", "enumerate", "filter", "float", "int", "isinstance",
                  "len", "list", "map", "max", "min", "pow", "print", "range", "reversed", "round", "set",
                  "slice", "sorted", "str", "sum", "tuple", "zip", "Exception", "ValueError", "RuntimeError")
    safe = {key: getattr(builtins, key) for key in safe_names}
    safe["__import__"] = restricted_import
    namespace = {"__builtins__": safe, "bpy": bpy, "bmesh": bmesh, "math": math, "mathutils": mathutils, "random": random}
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 0.001
    bpy.context.scene.unit_settings.length_unit = "MILLIMETERS"
    exec(compile(tree, "<AI modeling program>", "exec"), namespace)
    objects = namespace["create_model"]()
    if not isinstance(objects, (tuple, list)) or not 1 <= len(objects) <= 200:
        raise ValueError("create_model() must return a list of 1–200 Blender objects")
    if any(not isinstance(obj, bpy.types.Object) or obj.name not in bpy.context.scene.objects for obj in objects):
        raise ValueError("Returned objects must exist in the current scene")
    bpy.context.view_layer.update()
    points = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    if not points:
        raise ValueError("No model geometry was returned")
    zmin = min(point.z for point in points)
    center = Vector(((min(p.x for p in points) + max(p.x for p in points)) / 2,
                     (min(p.y for p in points) + max(p.y for p in points)) / 2, zmin))
    for obj in objects:
        obj.location -= center
    bpy.context.view_layer.update()
    if request.get("height") is not None:
        original = max(point.z for point in points) - zmin
        target = float(request["height"])
        if original <= 0 or not 1.2 <= target <= 250:
            raise ValueError("Requested uniform height must be 1.2–250 mm")
        factor = target / original
        for obj in objects:
            obj.location *= factor
            obj.scale *= factor
        bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    vertices, faces = [], []
    for obj in objects:
        if obj.type not in ("MESH", "CURVE", "SURFACE", "META", "FONT"):
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        if mesh is None:
            continue
        try:
            mesh.calc_loop_triangles()
            offset = len(vertices)
            for vertex in mesh.vertices:
                point = evaluated.matrix_world @ vertex.co
                vertices.append([point.x, point.y, point.z])
            faces.extend([[offset + index for index in triangle.vertices] for triangle in mesh.loop_triangles])
            if len(vertices) > 250_000 or len(faces) > 500_000:
                raise ValueError("Geometry exceeds 250000 vertices / 500000 triangles; reduce subdivisions or voxel resolution")
        finally:
            evaluated.to_mesh_clear()
    if len(vertices) < 4 or len(faces) < 4 or any(not math.isfinite(v) for vertex in vertices for v in vertex):
        raise ValueError("Blender did not produce valid mesh geometry")
    # Keep the construction objects and modifiers in the editable .blend file.
    text = bpy.data.texts.new("建模步骤.py")
    text.write(code)
    if request.get("summary"):
        description = bpy.data.texts.new("设计说明.txt")
        description.write(request["summary"])
    bpy.context.scene["xiaozao_prompt"] = request.get("prompt", "")
    bpy.context.scene["xiaozao_generator"] = "LLM + local Blender"
    bpy.ops.object.select_all(action="DESELECT")
    for obj in objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = objects[0]
    # Frame the model when the user opens the project in Blender.
    bounds = [obj.matrix_world @ Vector(corner) for obj in objects for corner in obj.bound_box]
    extent = max(max(p[i] for p in bounds) - min(p[i] for p in bounds) for i in range(3))
    target = Vector((0, 0, (max(p.z for p in bounds) + min(p.z for p in bounds)) / 2))
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == "VIEW_3D":
                area.spaces.active.region_3d.view_location = target
                area.spaces.active.region_3d.view_distance = max(10, extent * 2)
                area.spaces.active.clip_end = 10000
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "model.blend"), check_existing=False)
    (output / "mesh.json").write_text(json.dumps({"vertices": vertices, "faces": faces}), "utf-8")
    return {"vertices": len(vertices), "triangles": len(faces), "blender_version": bpy.app.version_string}


def main():
    arguments = sys.argv[sys.argv.index("--") + 1:]
    request_file, output_dir = map(Path, arguments[:2])
    output_dir.mkdir(parents=True, exist_ok=True)
    try:
        request = json.loads(request_file.read_text("utf-8"))
        result = run(request, output_dir)
        (output_dir / "result.json").write_text(json.dumps({"ok": True, **result}), "utf-8")
    except Exception:
        error = traceback.format_exc()
        print(error, flush=True)
        (output_dir / "result.json").write_text(json.dumps({"ok": False, "error": error[-7000:]}), "utf-8")
        raise


if __name__ == "__main__":
    main()
