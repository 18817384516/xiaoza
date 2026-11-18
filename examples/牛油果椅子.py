import bpy
import bmesh
import math


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def material(name, color):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = color
    return mat


def mesh_object(name, verts, faces):
    mesh = bpy.data.meshes.new(name + 'Mesh')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    return obj


def bevel(obj, width, segments=4):
    activate(obj)
    mod = obj.modifiers.new('Soft edges', 'BEVEL')
    mod.width = width
    mod.segments = segments
    bpy.ops.object.modifier_apply(modifier=mod.name)


def unite(target, addition):
    activate(target)
    mod = target.modifiers.new('Solid connection', 'BOOLEAN')
    mod.operation = 'UNION'
    mod.solver = 'EXACT'
    mod.object = addition
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(addition, do_unlink=True)


def make_back(skin, flesh, border):
    n = 96
    # Each ring follows a pear-shaped silhouette in the XZ plane.
    # Front faces -Y; its recessed center is farther toward +Y.
    rings = [
        (0.20, 14.30),
        (0.43, 13.95),
        (0.65, 12.95),
        (0.81, 11.35),
        (0.88, 10.45),
        (0.94, 10.15),
        (0.982, 11.35),
        (1.0, 14.10),
        (0.991, 17.80),
        (0.95, 20.50),
        (0.79, 22.10),
        (0.48, 22.75),
        (0.20, 23.0)
    ]
    verts = [(0, 14.4, 46)]
    for r, y in rings:
        for i in range(n):
            t = 2 * math.pi * i / n
            x = r * 22 * math.sin(t) * (1 - 0.18 * math.cos(t))
            z = 46 + r * 24 * math.cos(t)
            verts.append((x, y, z))
    faces = []
    indices = []
    for i in range(n):
        faces.append((0, 1 + i, 1 + (i + 1) % n))
        indices.append(1)
    for j in range(len(rings) - 1):
        a = 1 + j * n
        b = a + n
        for i in range(n):
            k = (i + 1) % n
            faces.append((a + i, b + i, b + k, a + k))
            indices.append(1 if j < 4 else (2 if j == 4 else 0))
    center = len(verts)
    verts.append((0, 23.1, 46))
    start = 1 + (len(rings) - 1) * n
    for i in range(n):
        faces.append((start + i, center, start + (i + 1) % n))
        indices.append(0)
    obj = mesh_object('Pear shaped avocado back', verts, faces)
    for mat in (skin, flesh, border):
        obj.data.materials.append(mat)
    for poly, index in zip(obj.data.polygons, indices):
        poly.material_index = index
        poly.use_smooth = True
    return obj


def make_leg(xsign, front, mat):
    bottom_x = xsign * 17.4
    top_x = xsign * 14.6
    bottom_y = -16.5 if front else 12.6
    top_y = -13.2 if front else 10.1
    n = 40
    verts = []
    # Horizontal rings give four genuinely flat contacts at Z=0.
    profiles = [(0.0, 2.75), (0.65, 3.12), (23.2, 4.0), (26.0, 4.05)]
    for z, radius in profiles:
        t = z / 26.0
        cx = bottom_x + (top_x - bottom_x) * t
        cy = bottom_y + (top_y - bottom_y) * t
        for i in range(n):
            a = 2 * math.pi * i / n
            verts.append((cx + radius * math.cos(a), cy + radius * math.sin(a), z))
    faces = [tuple(reversed(range(n)))]
    for j in range(len(profiles) - 1):
        for i in range(n):
            k = (i + 1) % n
            faces.append((j*n+i, j*n+k, (j+1)*n+k, (j+1)*n+i))
    faces.append(tuple((len(profiles)-1)*n+i for i in range(n)))
    obj = mesh_object('Splayed short leg', verts, faces)
    obj.data.materials.append(mat)
    for poly in obj.data.polygons:
        poly.use_smooth = len(poly.vertices) == 4
    return obj


def create_model():
    skin = material('Deep avocado peel', (0.115, 0.255, 0.055, 1))
    flesh = material('Avocado flesh', (0.72, 0.84, 0.28, 1))
    border = material('Fresh green rim', (0.36, 0.58, 0.10, 1))
    brown = material('Warm brown stone', (0.34, 0.135, 0.055, 1))

    back = make_back(skin, flesh, border)

    # An eight-millimeter thick seat has a usable flat upper surface.
    bpy.ops.mesh.primitive_cube_add(size=1, location=(0, -2.5, 25))
    seat = bpy.context.object
    seat.name = 'Rounded usable seat'
    seat.dimensions = (44, 39, 8)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bevel(seat, 3.5, 6)
    seat.data.materials.append(flesh)
    for poly in seat.data.polygons:
        poly.use_smooth = poly.area < 80
    unite(back, seat)

    for sign in (-1, 1):
        for front in (True, False):
            leg = make_leg(sign, front, skin)
            unite(back, leg)

    # A substantial buried rear portion bonds the pit to the concave flesh.
    bpy.ops.mesh.primitive_uv_sphere_add(segments=48, ring_count=32, location=(0, 10.25, 45))
    pit = bpy.context.object
    pit.name = 'Raised avocado stone cushion'
    pit.scale = (9.8, 5.8, 11.6)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    pit.data.materials.append(brown)
    for poly in pit.data.polygons:
        poly.use_smooth = True
    unite(back, pit)

    back.name = 'Avocado chair 70mm single solid'
    bm = bmesh.new()
    bm.from_mesh(back.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(back.data)
    bm.free()
    back.data.update()
    activate(back)
    return [back]
