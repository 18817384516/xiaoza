import bpy
import bmesh
import math


def activate(obj):
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj


def create_model():
    # Coordinates in millimeters: X width, Y depth, Z height.
    # Extrude a single U-shaped profile, not three touching boxes.
    profile = [(-18.0, 0.0), (18.0, 0.0),
               (18.0, 28.0), (15.0, 28.0),
               (15.0, 3.0), (-15.0, 3.0),
               (-15.0, 28.0), (-18.0, 28.0)]
    vertices = [(x, y, z) for y in (-10.0, 10.0) for x, z in profile]
    n = len(profile)
    faces = [tuple(range(n - 1, -1, -1)), tuple(range(n, 2 * n))]
    for i in range(n):
        j = (i + 1) % n
        faces.append((i, j, j + n, i + n))

    mesh = bpy.data.meshes.new('U_Profile_Solid')
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    bm = bmesh.new()
    bm.from_mesh(mesh)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(mesh)
    bm.free()
    body = bpy.data.objects.new('U形理线夹_36x20x28mm', mesh)
    bpy.context.collection.objects.link(body)
    activate(body)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)

    # True through holes, diameter 6 mm and center spacing 18 mm.
    for x in (-9.0, 9.0):
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=3.0, depth=9.0,
                                           end_fill_type='NGON', location=(x, 0.0, 1.5))
        cutter = bpy.context.object
        cutter.name = 'Through_Hole_Cutter'
        bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
        activate(body)
        boolean = body.modifiers.new('Diameter_6_Through_Hole', 'BOOLEAN')
        boolean.operation = 'DIFFERENCE'
        boolean.solver = 'EXACT'
        boolean.object = cutter
        bpy.ops.object.modifier_apply(modifier=boolean.name)
        bpy.data.objects.remove(cutter, do_unlink=True)

    # Round the exposed boundaries and both hole mouths, preserving the bore.
    activate(body)
    bevel = body.modifiers.new('Radius_1mm', 'BEVEL')
    bevel.width = 1.0
    bevel.segments = 5
    bevel.limit_method = 'ANGLE'
    bevel.angle_limit = math.radians(30.0)
    bevel.affect = 'EDGES'
    bevel.use_clamp_overlap = True
    bpy.ops.object.modifier_apply(modifier=bevel.name)

    bm = bmesh.new()
    bm.from_mesh(body.data)
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    bm.to_mesh(body.data)
    bm.free()
    body.data.update()
    # Keep broad mechanical planes flat; smooth the rounded strips.
    for face in body.data.polygons:
        face.use_smooth = face.area < 5.0

    material = bpy.data.materials.new('深蓝工程塑料')
    material.diffuse_color = (0.08, 0.23, 0.36, 1.0)
    body.data.materials.append(material)
    activate(body)
    return [body]
