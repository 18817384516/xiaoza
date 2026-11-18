"""Small CPU-only orthographic views of the actual export mesh for visual review.

These are shaded geometry previews, not photorealistic renders. No display,
graphics driver or extra Blender permissions are needed.
"""
from __future__ import annotations

import base64
from io import BytesIO

import numpy as np
from PIL import Image, ImageDraw


def model_views(mesh, path=None, cancelled=lambda: False):
    size = 512
    sheet = Image.new("RGB", (size * 3, size + 42), "#f1f2f5")
    vertices = np.asarray(mesh.vertices) - mesh.bounds.mean(axis=0)
    faces = np.asarray(mesh.faces)
    normals = np.asarray(mesh.face_normals)
    radius = max(float(np.linalg.norm(vertices, axis=1).max()), 1)
    scale = (size - 48) / (radius * 2)
    light = np.array([-.45, -.65, .8])
    light /= np.linalg.norm(light)
    for i, (label, direction) in enumerate([
        ("FRONT (-Y)", [0, -1, 0]),
        ("RIGHT (+X)", [1, 0, 0]),
        ("THREE-QUARTER", [1, -1.4, .8]),
    ]):
        if cancelled():
            return None
        toward = np.array(direction, dtype=float)
        toward /= np.linalg.norm(toward)
        right = np.cross([0, 0, 1], toward)
        right /= np.linalg.norm(right)
        up = np.cross(toward, right)
        screen = np.column_stack((vertices @ right, -(vertices @ up))) * scale + size / 2
        depth = (vertices @ toward)[faces].mean(axis=1)
        visible = np.flatnonzero(normals @ toward > 0)
        order = visible[np.argsort(depth[visible])]
        shade = np.clip(.40 + .50 * np.maximum(normals @ light, 0) + .10 * np.maximum(normals @ toward, 0), .3, 1)
        colors = np.clip(shade[:, None] * np.array([183, 166, 211]), 0, 255).astype(np.uint8)
        panel = Image.new("RGB", (size, size), "#f1f2f5")
        draw = ImageDraw.Draw(panel)
        triangles = screen[faces]
        for count, index in enumerate(order):
            if count % 12000 == 0 and cancelled():
                return None
            draw.polygon([tuple(p) for p in triangles[index]], fill=tuple(int(v) for v in colors[index]))
        sheet.paste(panel, (size * i, 32))
        ImageDraw.Draw(sheet).text((size * i + 18, 12), label, fill="#343449")
    if path is not None:
        sheet.save(path, "PNG")
    output = BytesIO()
    sheet.save(output, "PNG")
    return "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
