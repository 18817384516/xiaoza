"""Smooth implicit figurines. Surface extraction runs locally, without an AI service."""
from __future__ import annotations

import manifold3d as m
import numpy as np
import trimesh
from skimage.measure import marching_cubes


def animal(kind, params):
    step = .7
    origin = np.array([-45, -45, -3], dtype=np.float32)
    x, y, z = np.ogrid[-45:45.01:step, -45:45.01:step, -3:100.01:step]
    x, y, z = x.astype(np.float32), y.astype(np.float32), z.astype(np.float32)
    shape = (len(x), y.shape[1], z.shape[2])
    field = np.full(shape, 999, dtype=np.float32)
    cuts = []
    head, belly, ear = (params.get(k, 1) for k in ('head_scale', 'belly_scale', 'ear_scale'))

    def blend(a, b, k):
        if k <= 0:
            return np.minimum(a, b)
        h = np.maximum(k - np.abs(a - b), 0) / k
        return np.minimum(a, b) - h * h * k * .25

    def ellipsoid(center, radii):
        xx, yy, zz = ((axis - c) / r for axis, c, r in zip((x, y, z), center, radii))
        k0 = np.sqrt(xx * xx + yy * yy + zz * zz)
        k1 = np.sqrt((xx / radii[0])**2 + (yy / radii[1])**2 + (zz / radii[2])**2)
        return k0 * (k0 - 1) / np.maximum(k1, .00001)

    def add(center, radii, k=2.1):
        nonlocal field
        field = blend(field, ellipsoid(center, radii), k)

    def cut(center, radii):
        cuts.append((center, radii))

    if kind == 'turtle':
        add((0, 3, 17), (21, 25, 15))
        add((0, -19, 14), (10, 12, 10))
        for side in (-1, 1):
            for yy in (-12, 17):
                add((side * 17, yy, 7), (8, 9, 6))
        add((0, 26, 9), (4, 9, 4))
    else:
        add((0, 0, 23), (15 * belly, 12 * belly, 19))
        add((0, -1.8, 45), (16 * head, 13 * head, 14 * head), 3)
        for side in (-1, 1):
            add((side * 9, -6, 6), (8, 10, 6))
            add((side * 12 * belly, -1, 24), (5, 6, 11), 2.8)
        if kind == 'bunny':
            for side in (-1, 1):
                add((side * 8.7, -.5, 61 + 3 * ear), (5.2, 5, 16 * ear), 1.6)
            add((-3.8, -13, 40), (5, 3.6, 4), 1)
            add((3.8, -13, 40), (5, 3.6, 4), 1)
            add((0, 12, 15), (6.5, 6.5, 6.5))
        elif kind in ('cat', 'fox'):
            for side in (-1, 1):
                # Pointed ears: a smoothly joined tapered diamond, thick enough to print.
                cx = side * 10
                zz = (z - 51) / (17 * ear)
                width = np.maximum(.2, (1 - zz) * 7 * ear)
                cone = np.maximum(np.maximum(np.abs(x - cx - side * zz * 2.5) - width, np.abs(y + .5) - width * .65), np.maximum(51 - z, z - (51 + 17 * ear)))
                field = blend(field, cone, 1.3)
            if kind == 'fox':
                add((17, 8, 18), (10, 8, 16))
                add((0, -14, 41), (9, 6.8, 5))
            else:
                for pt in [(13,7,13),(19,8,16),(22,8,22),(22,8,29)]:
                    add(pt, (4.8,4.8,6))
                add((0,-13,41),(8,3.5,4))
        elif kind in ('bear','pig','dog'):
            for side in (-1,1):
                add((side*12,-1,56),(6*ear,4.5,(10 if kind=='dog' else 6)*ear))
            add((0,-13,41),((7 if kind=='pig' else 8),4.8,6))
        elif kind in ('duck','penguin'):
            add((0,-14,41),((9 if kind=='duck' else 5),7,3),1)
            add((0,-8.7,23),(10,4.2,14))
        elif kind=='frog':
            for side in (-1,1):
                add((side*10,-5,55),(7,6,7))
                add((side*16,-2,10),(10,8,10))

    if kind=='bunny':
        for side in (-1,1):
            cut((side*8.7,-4.8,64+3*ear),(2.3,2.4,9*ear))
    if kind=='pig':
        for side in (-1,1):
            cut((side*2.7,-17.7,41),(1.5,1.8,1.5))
    eye_z=55 if kind=='frog' else 17 if kind=='turtle' else 46
    eye_y=-10.3 if kind=='frog' else -28.6 if kind=='turtle' else -13.7*head
    eye_x=9.8 if kind=='frog' else 4.8 if kind=='turtle' else 6.1*head
    for side in (-1,1):
        cut((side*eye_x,eye_y,eye_z),(1.8,2.5,2.1))
    if kind not in ('duck','penguin','frog','turtle','pig'):
        cut((0,-20.2 if kind=='fox' else -16.1,43),(2.3,1.8,1.5))
    field=np.maximum(field,1.5-z)
    vertices, faces, _, _=marching_cubes(field,level=0,spacing=(step,step,step),allow_degenerate=False)
    vertices+=origin
    mesh=trimesh.Trimesh(vertices=vertices,faces=faces,process=True)
    mesh.fix_normals(multibody=False)
    raw=m.Mesh(vert_properties=np.asarray(mesh.vertices,dtype=np.float32),tri_verts=np.asarray(mesh.faces,dtype=np.uint32))
    solid=m.Manifold(raw).simplify(.035).translate((0,0,-1.5))
    if cuts:
        recesses=[m.Manifold.sphere(1,64).scale(radii).translate((center[0],center[1],center[2]-1.5)) for center,radii in cuts]
        solid=solid-m.Manifold.batch_boolean(recesses,m.OpType.Add)
    if params.get('base',True):
        radius=33 if kind=='turtle' else 25
        # Rounded top lip, flat bottom; all part of the actual exported model.
        profile=[(0,0),(radius-.6,0),(radius, .6),(radius,2.4),(radius-.6,3),(0,3)]
        solid=solid+m.CrossSection([profile]).revolve(96)
    bounds=solid.bounding_box()
    return solid.scale((params['height']/(bounds[5]-bounds[2]),)*3)
