"""The generated program is allowed to model, not access files or the system.

This is a restricted modeling interpreter plus process limits, not an OS sandbox.
The trusted Blender worker alone handles project files, rendering and exports.
"""
from __future__ import annotations

import ast

ALLOWED_MODULES = {"bpy", "bmesh", "math", "mathutils", "random"}
FORBIDDEN_NAMES = {
    "eval", "exec", "compile", "open", "input", "getattr", "setattr", "delattr", "hasattr",
    "globals", "locals", "vars", "dir", "type", "object", "super", "help", "breakpoint",
    "exit", "quit", "memoryview", "classmethod", "staticmethod", "property",
}
FORBIDDEN_ATTRIBUTES = {
    "app", "utils", "path", "types", "msgbus", "handlers", "timers", "texts", "libraries",
    "screens", "window_managers", "workspaces", "preferences", "addons", "keyconfigs",
    "load", "save", "read", "write", "load_from_file", "write_file", "save_render",
    "filepath", "directory", "filename", "file_path", "rna_type", "bl_rna", "id_data",
    "driver_add", "driver_remove", "animation_data", "animation_data_create", "drivers",
    "from_pydata_file", "external", "command", "system", "popen", "environ", "from_address",
    "gi_frame", "gi_code", "cr_frame", "cr_code", "f_globals", "f_locals", "f_builtins",
    "tb_frame", "format", "format_map", "mro", "subclasses", "as_pointer", "user_resource",
    "to_socket", "to_file", "bake", "wm", "import_scene", "export_scene", "script", "console",
    "material_slots",  # use data.materials.append instead of context-dependent operators
}
SAFE_OPERATORS = {
    "object": {"select_all", "delete", "join", "convert", "transform_apply", "modifier_apply",
               "shade_smooth", "shade_flat", "mode_set", "origin_set", "duplicate", "parent_set"},
    "mesh": {"primitive_cube_add", "primitive_uv_sphere_add", "primitive_ico_sphere_add",
             "primitive_cylinder_add", "primitive_cone_add", "primitive_torus_add", "primitive_plane_add",
             "primitive_circle_add", "select_all", "remove_doubles", "merge_by_distance", "normals_make_consistent",
             "subdivide", "extrude_region_move", "extrude_faces_move", "bevel", "delete", "fill", "edge_face_add"},
    "curve": {"primitive_bezier_curve_add", "primitive_bezier_circle_add", "primitive_nurbs_curve_add"},
    "transform": {"translate", "rotate", "resize"},
}


class ScriptPolicyError(ValueError):
    pass


def dotted(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        base = dotted(node.value)
        return base + "." + node.attr if base else None
    return None


def validate_script(code):
    if not isinstance(code, str) or not 20 <= len(code) <= 60_000:
        raise ScriptPolicyError("建模脚本需要在 20–60000 字符之间。")
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        raise ScriptPolicyError(f"脚本第 {error.lineno} 行语法错误：{error.msg}") from None
    if not any(isinstance(node, ast.FunctionDef) and node.name == "create_model" for node in tree.body):
        raise ScriptPolicyError("脚本必须定义 create_model() 并返回建模对象列表。")
    if sum(1 for _ in ast.walk(tree)) > 16_000:
        raise ScriptPolicyError("建模脚本过大，请简化实现。")
    for node in ast.walk(tree):
        if isinstance(node, (ast.While, ast.AsyncFunctionDef, ast.Await, ast.ClassDef, ast.Global, ast.Nonlocal, ast.With, ast.AsyncWith)):
            raise ScriptPolicyError(f"建模脚本不能使用 {type(node).__name__}。")
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.name.startswith("_")):
            raise ScriptPolicyError("建模辅助函数不能使用装饰器或私有名称。")
        if isinstance(node, ast.Name) and (node.id.startswith("_") or node.id in FORBIDDEN_NAMES):
            raise ScriptPolicyError(f"建模脚本不允许访问 {node.id}。")
        if isinstance(node, ast.Attribute) and (node.attr.startswith("_") or node.attr in FORBIDDEN_ATTRIBUTES):
            raise ScriptPolicyError(f"建模脚本不允许访问属性 {node.attr}。")
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and "__" in node.value:
            raise ScriptPolicyError("建模脚本不能访问内部属性。")
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name not in ALLOWED_MODULES or (alias.asname and alias.asname != alias.name):
                    raise ScriptPolicyError("仅可导入 bpy、bmesh、math、mathutils、random，且不使用别名。")
        if isinstance(node, ast.ImportFrom):
            if node.module not in ("math", "mathutils") or node.level or any(a.name.startswith("_") or a.name == "*" for a in node.names):
                raise ScriptPolicyError("仅可从 math、mathutils 导入公开函数；bpy 和 bmesh 请完整导入。")
        if isinstance(node, ast.Call):
            path = dotted(node.func)
            if path and path.startswith("bpy.ops."):
                segments = path.split(".")
                if len(segments) != 4 or segments[3] not in SAFE_OPERATORS.get(segments[2], set()):
                    raise ScriptPolicyError(f"不支持该 Blender 操作：{path}。请使用数据接口建模。")
            if path == "range" and any(isinstance(a, ast.Constant) and isinstance(a.value, int) and abs(a.value) > 500_000 for a in node.args):
                raise ScriptPolicyError("单个建模循环过大。")
            if path and path.split(".")[-1] in ("new", "get"):
                if any(isinstance(a, ast.Constant) and a.value in ("ShaderNodeScript", "GeometryNodeImportOBJ", "GeometryNodeImportPLY", "GeometryNodeImportSTL", "GeometryNodeImportCSV", "GeometryNodeImportVDB") for a in node.args):
                    raise ScriptPolicyError("不能创建外部文件或脚本节点。")
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in ALLOWED_MODULES:
                    raise ScriptPolicyError("不能覆盖建模模块名称。")
    return tree
