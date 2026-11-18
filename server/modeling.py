"""Deterministic solid modeling. All dimensions are millimeters."""
from __future__ import annotations

import math
import re
import manifold3d as m
import numpy as np
import trimesh
from shapely.geometry import Polygon


CATALOG = {
    "bunny": ("治愈系小兔", "figurine", ["兔", "bunny", "rabbit"]),
    "cat": ("招财小猫", "figurine", ["猫", "cat", "kitten"]),
    "bear": ("圆滚滚小熊", "figurine", ["熊", "bear"]),
    "dog": ("乖巧小狗", "figurine", ["狗", "犬", "dog", "puppy"]),
    "fox": ("森林小狐狸", "figurine", ["狐狸", "fox"]),
    "penguin": ("呆萌企鹅", "figurine", ["企鹅", "penguin"]),
    "duck": ("小鸭子", "figurine", ["鸭", "duck"]),
    "pig": ("小猪", "figurine", ["猪", "pig"]),
    "frog": ("小青蛙", "figurine", ["蛙", "frog"]),
    "turtle": ("小乌龟", "figurine", ["龟", "turtle"]),
    "bracket": ("L 型安装支架", "part", ["支架", "角码", "bracket"]),
    "gear": ("直齿轮", "part", ["齿轮", "gear"]),
    "washer": ("圆形垫片", "part", ["垫片", "垫圈", "washer"]),
    "box": ("开口收纳盒", "part", ["收纳", "盒", "box", "托盘"]),
    "vase": ("桌面花瓶", "part", ["花瓶", "笔筒", "vase"]),
    "plate": ("安装板", "part", ["板", "plate"]),
    "knob": ("旋钮", "part", ["旋钮", "把手", "knob"]),
    "spacer": ("圆柱隔离柱", "part", ["隔离柱", "圆柱", "套筒", "spacer", "cylinder"]),
    "sphere": ("圆球", "part", ["球", "sphere"]),
    "cube": ("方块", "part", ["方块", "立方", "cube"]),
    "sketch": ("草图实体", "sketch", []),
    "custom": ("自定义组合模型", "custom", []),
}

DEFAULTS = {
    "figurine": {"height": 65, "ear_scale": 1, "head_scale": 1, "belly_scale": 1, "base": True},
    "bracket": {"width": 50, "depth": 40, "height": 40, "thickness": 4, "hole_diameter": 5, "holes": 4, "tolerance": 0.2},
    "gear": {"width": 40, "height": 8, "hole_diameter": 6, "teeth": 20, "tolerance": 0.2},
    "washer": {"width": 24, "height": 3, "hole_diameter": 8, "tolerance": 0.2},
    "box": {"width": 80, "depth": 60, "height": 35, "thickness": 2.4},
    "vase": {"width": 46, "height": 70, "thickness": 2.4},
    "plate": {"width": 80, "depth": 40, "height": 5, "hole_diameter": 5, "holes": 4, "tolerance": 0.2},
    "knob": {"width": 30, "height": 18, "hole_diameter": 6, "tolerance": 0.2},
    "spacer": {"width": 16, "height": 25, "hole_diameter": 6, "tolerance": 0.2},
    "sphere": {"width": 30},
    "cube": {"width": 30, "depth": 30, "height": 30},
    "sketch": {"width": 60, "height": 8},
    "custom": {"height": 60},
}


class ModelingError(ValueError):
    def __init__(self, message: str, code: str = "modeling_error"):
        super().__init__(message)
        self.code = code


def find_kind(text: str, mode: str = "auto") -> str | None:
    """Treat the direction picker as a preference, and English names as words."""
    matches = []
    for kind, (_, category, words) in CATALOG.items():
        for word in words:
            pattern = rf"(?<![a-z]){re.escape(word)}(?![a-z])" if word.isascii() else re.escape(word)
            match = re.search(pattern, text, re.I)
            if match:
                matches.append((mode != "auto" and category != mode, match.start(), -len(word), kind))
    return min(matches)[3] if matches else None


def number(text: str, labels: list[str]) -> float | None:
    for label in labels:
        match = re.search(rf"(?:{label})\s*(?:为|是|约|度|[:：=])?\s*(-?\d+(?:\.\d+)?)\s*(毫米|厘米|mm|cm)?", text, re.I)
        if match:
            return float(match[1]) * (10 if match[2] in ("厘米", "cm") else 1)
    return None


def plan(prompt: str, mode: str = "auto", overrides: dict | None = None, previous: dict | None = None, sketch: list | None = None) -> dict:
    text = prompt.lower().strip()
    # Natural Chinese counts are common in first-time descriptions.
    for cn, digit in (("零", "0"), ("一", "1"), ("二", "2"), ("两", "2"), ("三", "3"), ("四", "4")):
        text = re.sub(cn + r"(?=\s*个(?:安装)?孔)", digit, text)
    if sketch:
        kind = "sketch"
    else:
        kind = find_kind(text, mode)
    if kind is None and previous:
        kind = previous["kind"]
    if kind is None:
        raise ModelingError("当前本地造型库暂不支持这段描述。你的描述已保留：可以查看可生成的模型、画平面轮廓并拉伸，或连接 AI 尝试组合形状。", code="unsupported_description")
    category = CATALOG[kind][1]
    params = dict(DEFAULTS.get(kind, DEFAULTS[category])) if kind not in DEFAULTS else dict(DEFAULTS[kind])
    if category == "figurine":
        if kind in ("duck", "penguin", "frog", "turtle"):
            params.pop("ear_scale", None)
        if kind == "turtle":
            params.pop("head_scale", None)
            params.pop("belly_scale", None)
    if previous and previous["kind"] == kind:
        params.update(previous.get("params", {}))
    mapping = {
        "height": ["总高", "高度", "高", "height"],
        "width": ["外径", "外直径", "(?<!孔)(?<!内)直径", "宽度", "宽", "长度", "长", "width", "diameter"],
        "depth": ["深度", "深", "depth"],
        "thickness": ["壁厚", "厚度", "厚", "thickness", "wall"],
        "hole_diameter": ["孔径", "孔直径", "内径", "hole"],
        "teeth": ["齿数", "teeth"],
        "tolerance": ["公差", "间隙", "tolerance"],
    }
    for key, labels in mapping.items():
        value = number(text, labels)
        if value is not None and key in params:
            params[key] = value
    if "depth" in params:
        length = number(text, ["长度", "长"])
        width = number(text, ["宽度", "宽"])
        if length is not None:
            params["width"] = length
            if width is not None and number(text, ["深度", "深", "depth"]) is None:
                params["depth"] = width
    if category == "figurine":
        reverse_height = re.search(r"(\d+(?:\.\d+)?)\s*(厘米|cm|毫米|mm)\s*(?:的)?高", text)
        if reverse_height:
            params["height"] = float(reverse_height[1]) * (10 if reverse_height[2] in ("厘米", "cm") else 1)
    dimension = re.search(r"(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*[x×*]\s*(\d+(?:\.\d+)?)\s*(cm|厘米|mm|毫米)?", text)
    if dimension and "depth" in params:
        factor = 10 if dimension[4] in ("cm", "厘米") else 1
        for key, val in zip(["width", "depth", "height"], dimension.groups()[:3]):
            params[key] = float(val) * factor
    if "height" in params and "thickness" not in params and kind in ("plate", "washer", "gear"):
        thickness = number(text, ["厚度", "厚"])
        if thickness is not None:
            params["height"] = thickness
    if "teeth" in params:
        teeth = re.search(r"(\d+)\s*齿", text)
        if teeth:
            params["teeth"] = int(teeth[1])
    holes = re.search(r"(\d+)\s*(?:个)?(?:安装)?孔", text)
    if holes and "holes" in params:
        params["holes"] = int(holes[1])
    if re.search(r"无孔|不要孔|不打孔|实心", text):
        if "holes" in params:
            params["holes"] = 0
        elif "hole_diameter" in params:
            params["hole_diameter"] = 0
    if category == "figurine":
        size = number(text, ["尺寸"])
        if size:
            params["height"] = size
        if "不要底座" in text or "去掉底座" in text:
            params["base"] = False
        if "加底座" in text or "带底座" in text:
            params["base"] = True
        for keyword, key in [("耳朵", "ear_scale"), ("脑袋", "head_scale"), ("头", "head_scale"), ("肚子", "belly_scale")]:
            if keyword in text:
                if key not in params:
                    continue
                if re.search(keyword + r".{0,4}(?:大|长)", text):
                    params[key] = min(1.4, params[key] * 1.15)
                elif re.search(keyword + r".{0,4}(?:小|短)", text):
                    params[key] = max(0.65, params[key] / 1.15)
    if overrides:
        for key in params:
            if key in overrides:
                params[key] = overrides[key]
    validate_params(kind, params)
    edits = list((previous or {}).get("edits", []))[-29:]
    if previous and prompt != previous.get("prompt"):
        edits.append(prompt)
    result = {"kind": kind, "category": category, "name": CATALOG[kind][0], "params": params, "prompt": previous.get("prompt", prompt) if previous else prompt, "edits": edits}
    if previous and kind == "custom":
        result["scene"] = previous.get("scene")
    if kind == "sketch":
        result["sketch"] = sketch or (previous or {}).get("sketch")
    return result


def validate_params(kind: str, p: dict):
    for key, value in p.items():
        if key == "base":
            if not isinstance(value, bool):
                raise ModelingError("底座开关必须是开启或关闭。")
            continue
        if not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ModelingError("尺寸需要填写有效数字。")
        low, high = ((0.65, 1.4) if key.endswith("_scale") else (0, 1) if key == "tolerance" else (0, 4) if key == "holes" else (8, 80) if key == "teeth" else (0, 200) if key == "hole_diameter" else (1.2, 20) if key == "thickness" else (5, 250) if kind not in ("washer", "plate", "gear", "sketch") or key != "height" else (1.2, 100))
        if not low <= value <= high:
            raise ModelingError(f"{ {'width':'宽度 / 外径','depth':'深度','height':'高度','thickness':'壁厚','hole_diameter':'孔径','teeth':'齿数','holes':'孔数量','tolerance':'孔径补偿'}.get(key, key) }需要在 {low}–{high} 之间。")
        if key in ("teeth", "holes") and value != int(value):
            raise ModelingError("齿数和孔数量需要填写整数。")
    w, d, h, t = p.get("width", 60), p.get("depth", p.get("width", 60)), p.get("height", 60), p.get("thickness", 2)
    hd = p.get("hole_diameter", 0) + p.get("tolerance", 0)
    if kind in ("washer", "gear", "spacer", "knob") and hd >= w * 0.7:
        raise ModelingError("孔径太大，请把孔径调整到外径的 70% 以下，留出足够实体。")
    if kind in ("box", "vase", "bracket") and t * 2.5 >= min(w, d, h):
        raise ModelingError("壁厚相对尺寸太大，请减小壁厚或增大模型。")
    if kind in ("plate", "bracket") and p.get("holes", 0) and hd * 3.5 > min(w, d, h if kind == "bracket" else d):
        raise ModelingError("安装孔太大或边距不足，请减小孔径或增大支架 / 安装板。")
    if kind in ("bracket", "plate") and p.get("holes", 0) not in (0, 2, 4):
        raise ModelingError("安装孔数量支持 0、2 或 4 个。")


def sphere(center, scale, segments=40):
    return m.Manifold.sphere(1, segments).scale(scale).translate(center)


def cylinder(radius, height, pos=(0, 0, 0), segments=64):
    return m.Manifold.cylinder(height, radius, circular_segments=segments).translate(pos)


def box(w, d, h, pos=(0, 0, 0)):
    return m.Manifold.cube((w, d, h)).translate((-w / 2 + pos[0], -d / 2 + pos[1], pos[2]))


def union(parts):
    return m.Manifold.batch_boolean(parts, m.OpType.Add)


def involute_gear(w, h, teeth, bore):
    # True involute flank profile, 20 degree pressure angle, module from outside diameter.
    module = w / (teeth + 2)
    pitch = module * teeth / 2
    base = pitch * math.cos(math.radians(20))
    outer = w / 2
    root = max(pitch - 1.25 * module, module)
    half_angle = math.pi / (2 * teeth)
    involute_pitch = math.tan(math.radians(20)) - math.radians(20)
    outline = []
    for tooth in range(teeth):
        center = tooth * 2 * math.pi / teeth
        flank = []
        for r in np.linspace(max(base, root), outer, 7):
            t = math.sqrt(max(0, (r / base) ** 2 - 1))
            theta = half_angle + involute_pitch - (t - math.atan(t))
            flank.append((float(r), theta))
        root_angle = half_angle + involute_pitch
        samples = [(root, -math.pi / teeth), (root, -root_angle)]
        samples += [(r, -a) for r, a in flank]
        samples += [(r, a) for r, a in reversed(flank)]
        samples += [(root, root_angle), (root, math.pi / teeth)]
        outline.extend((r * math.cos(center + angle), r * math.sin(center + angle)) for r, angle in samples)
    solid = m.CrossSection([outline]).extrude(h)
    return solid - cylinder(bore / 2, h + 2, (0, 0, -1)) if bore > 0 else solid


def mechanical(kind, p):
    w, d, h, t = p.get("width", 40), p.get("depth", 40), p.get("height", 30), p.get("thickness", 3)
    bore = p.get("hole_diameter", 0)
    if bore > 0:
        bore += p.get("tolerance", 0)
    if kind == "cube":
        return box(w, d, h)
    if kind == "sphere":
        return sphere((0, 0, w / 2), (w / 2,) * 3, 64)
    if kind == "gear":
        return involute_gear(w, h, int(p["teeth"]), bore)
    if kind in ("washer", "spacer", "knob"):
        solid = cylinder(w / 2, h)
        if kind == "knob":
            cuts = [cylinder(w * .065, h + 2, (w * .51 * math.cos(a), w * .51 * math.sin(a), -1), 20) for a in np.linspace(0, math.tau, 18, endpoint=False)]
            solid = solid - union(cuts)
        return solid - cylinder(bore / 2, h + 2, (0, 0, -1)) if bore else solid
    if kind == "box":
        return box(w, d, h) - box(w - 2 * t, d - 2 * t, h, (0, 0, t))
    if kind == "vase":
        # Revolved hollow profile with a sealed base.
        profile = [(0, 0), (w*.35, 0), (w*.49, h*.18), (w*.5, h*.45), (w*.28, h*.83), (w*.29, h), (w*.29-t, h), (w*.28-t, h*.83), (w*.5-t, h*.45), (w*.49-t, h*.18), (w*.35-t, t), (0, t)]
        return m.CrossSection([profile]).revolve(96)
    if kind in ("plate", "bracket"):
        solid = box(w, d, h if kind == "plate" else t)
        if kind == "bracket":
            solid = solid + box(w, t, h, (0, d / 2 - t / 2, 0))
        holes = int(p["holes"])
        cuts = []
        if holes:
            for x in (-w * .28, w * .28):
                if kind == "plate":
                    for y in ((-d*.27, d*.27) if holes == 4 else (0,)):
                        cuts.append(cylinder(bore / 2, h + 2, (x, y, -1)))
                else:
                    cuts.append(cylinder(bore / 2, t + 2, (x, -d * .15, -1)))
                    if holes == 4:
                        cuts.append(cylinder(bore / 2, t + 2).rotate((90, 0, 0)).translate((x, d / 2 + 1, h * .68)))
        return solid - union(cuts) if cuts else solid
    raise ModelingError("暂不支持这个模型类型。")


def sketch_solid(recipe):
    paths = recipe.get("sketch", [])
    if not paths or len(paths) > 16:
        raise ModelingError("请先画一个封闭轮廓，最多可画 16 个轮廓。")
    region = None
    for path in paths:
        if len(path) < 3 or len(path) > 3000:
            raise ModelingError("轮廓太短或太复杂，请重新画一个清晰的封闭轮廓。")
        points = np.array(path, dtype=float)
        if points.shape[1] != 2 or not np.isfinite(points).all() or (np.abs(points) > 2000).any():
            raise ModelingError("草图坐标无效。")
        polygon = Polygon(points).buffer(0).simplify(.8, preserve_topology=True)
        if polygon.area < 12:
            continue
        region = polygon if region is None else region.symmetric_difference(polygon)
    if region is None or region.is_empty:
        raise ModelingError("没有可用的轮廓。请画出有面积的形状，内部再画一圈可以开孔。")
    regions = list(region.geoms) if region.geom_type == "MultiPolygon" else [region]
    if len(regions) > 1:
        raise ModelingError("这些轮廓彼此分离，会打印成多个零件。请让外轮廓相连；画在内部的轮廓会成为孔。")
    poly = regions[0]
    bounds = poly.bounds
    scale = recipe["params"]["width"] / (bounds[2] - bounds[0])
    cx, cy = (bounds[0] + bounds[2]) / 2, (bounds[1] + bounds[3]) / 2
    contours = [[((x - cx) * scale, -(y - cy) * scale) for x, y in ring.coords] for ring in [poly.exterior, *poly.interiors]]
    solid = m.CrossSection(contours, m.FillRule.EvenOdd).extrude(recipe["params"]["height"])
    return solid


def custom_solid(scene):
    if not isinstance(scene, list) or not 1 <= len(scene) <= 32:
        raise ModelingError("AI 需要返回 1–32 个组合实体。请简化描述后重试。")
    solid = None
    for item in scene:
        if not isinstance(item, dict):
            raise ModelingError("AI 返回的形状数据不完整。")
        shape = item.get("shape")
        size = item.get("size", [10, 10, 10])
        pos = item.get("position", [0, 0, 0])
        rot = item.get("rotation", [0, 0, 0])
        for values in (size, pos, rot):
            if not isinstance(values, list) or len(values) != 3 or any(not isinstance(v, (float, int)) or not math.isfinite(v) or abs(v) > 500 for v in values):
                raise ModelingError("AI 返回的尺寸超出安全建模范围。")
        if any(v < 0.5 or v > 250 for v in size):
            raise ModelingError("AI 返回的部件尺寸需要在 0.5–250 mm 之间。")
        if shape == "box":
            piece = box(*size)
        elif shape == "sphere":
            piece = sphere((0, 0, size[2] / 2), tuple(v / 2 for v in size))
        elif shape in ("cylinder", "cone"):
            piece = m.Manifold.cylinder(size[2], size[0] / 2, size[1] / 2 if shape == "cone" else size[0] / 2, 64)
        else:
            raise ModelingError("AI 返回了尚不支持的形状，请要求使用方块、球、圆柱或圆锥组合。")
        piece = piece.rotate(rot).translate(pos)
        if item.get("operation", "add") == "subtract":
            if solid is None:
                raise ModelingError("组合模型需要先添加实体，再开孔。")
            solid = solid - piece
        else:
            solid = piece if solid is None else solid + piece
    return solid


def build(recipe: dict) -> tuple[trimesh.Trimesh, dict]:
    kind, p = recipe["kind"], recipe["params"]
    validate_params(kind, p)
    if recipe["category"] == "figurine":
        from .organic import animal as organic_animal
        solid = organic_animal(kind, p)
    elif kind == "sketch":
        solid = sketch_solid(recipe)
    elif kind == "custom":
        solid = custom_solid(recipe.get("scene"))
        bounds = solid.bounding_box()
        if bounds[5] > bounds[2]:
            solid = solid.scale((p["height"] / (bounds[5] - bounds[2]),) * 3)
    else:
        solid = mechanical(kind, p)
    if solid.is_empty() or solid.status() != m.Error.NoError:
        raise ModelingError("这组参数无法组成实体，请调整尺寸或让各部分相接。")
    raw = solid.to_mesh()
    mesh = trimesh.Trimesh(vertices=np.array(raw.vert_properties)[:, :3], faces=np.array(raw.tri_verts), process=True)
    mesh.remove_unreferenced_vertices()
    # Preserve inward-facing cavity shells from the solid kernel.
    mesh.fix_normals(multibody=False)
    mesh.apply_translation([-mesh.bounds[:, 0].mean(), -mesh.bounds[:, 1].mean(), -mesh.bounds[0, 2]])
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume <= 0:
        raise ModelingError("模型未通过封闭实体检查，请调整参数后重新生成。")
    components = int(sum(part.volume > 1e-7 for part in mesh.split(only_watertight=False)))
    if components != 1:
        raise ModelingError(f"模型有 {components} 个分离实体，请让部件相互连接后再生成。")
    warnings = []
    if recipe["category"] == "figurine":
        warnings.append("耳朵、下巴或尾部可能需要支撑；请在切片软件中检查悬垂。")
        if p["height"] < 35:
            warnings.append("尺寸较小，眼睛和耳朵细节可能变弱，建议用 0.2 mm 喷嘴或放大到 50 mm 以上。")
    if kind == "gear":
        warnings.append("采用 20° 渐开线直齿轮轮廓。啮合间隙与承载能力需要试印验证。")
        if p["width"] / (p["teeth"] + 2) < .8:
            warnings.insert(0, "齿轮模数小于 0.8 mm，齿形较细。建议增大外径或减少齿数，并检查切片预览。")
    if kind == "custom":
        warnings.append("AI 组合形状已通过封闭性检查，但结构强度、配合和最小壁厚需要自行核对。")
    if kind == "sketch":
        warnings.append("已沿轮廓拉伸；较细的线颈和孔边请在切片预览中核对壁厚。")
    if kind in ("bracket", "knob", "spacer", "plate", "washer"):
        warnings.append("孔径已增加所设补偿值；装配件建议先小样试印，承重部件须验证强度。")
    return mesh, {
        "dimensions": [round(float(v), 2) for v in mesh.extents],
        "volume_cm3": round(float(mesh.volume) / 1000, 3),
        "triangles": len(mesh.faces), "watertight": True, "components": components,
        "warnings": warnings, "units": "mm",
    }
