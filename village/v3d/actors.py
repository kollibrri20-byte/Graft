"""Персонажі з готових моделей (three.js examples: Xbot, Michelle — Mixamo-скелет з анімаціями)
та реалістична голова (LeePerrySmith) для крупних планів."""
import math
import os

import bpy
from mathutils import Vector

from lib import link, mat, setp, sphere

MODELS = os.environ.get("V3D_MODELS", "/tmp/claude-0/models")
SRC_FPS = 30.0


def _import(fname):
    before = set(bpy.data.objects)
    acts_before = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, fname))
    new = [o for o in bpy.data.objects if o not in before]
    acts = {a.name: a for a in bpy.data.actions if a not in acts_before}
    # прибираємо службові сфери
    for o in list(new):
        if o.type == "MESH" and o.name.startswith("Icosphere"):
            bpy.data.objects.remove(o)
            new.remove(o)
    return new, acts


def _bone_obj(arm, bone_name, obj, offset=(0, 0, 0)):
    obj.parent = arm
    obj.parent_type = "BONE"
    obj.parent_bone = bone_name
    obj.location = offset


def cloth_gradient(name, top, bottom, split_z=0.52, skin=(0.62, 0.44, 0.34), head_z=0.83, noise=50, axis="Z", height=180.0):
    """Матеріал за висотою (у координатах об'єкта): штани/сукня → куртка → шкіра голови."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 0.85
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    sep = nt.nodes.new("ShaderNodeSeparateXYZ")
    attr = nt.nodes.new("ShaderNodeTexCoord")
    nt.links.new(attr.outputs["Object"], sep.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    cr = ramp.color_ramp
    cr.interpolation = "CONSTANT"
    cr.elements[0].position = 0.0
    cr.elements[0].color = (*bottom, 1)
    cr.elements[1].position = split_z
    cr.elements[1].color = (*top, 1)
    e = cr.elements.new(head_z)
    e.color = (*skin, 1)
    dv = nt.nodes.new("ShaderNodeMath")
    dv.operation = "DIVIDE"
    dv.inputs[1].default_value = height
    nt.links.new(sep.outputs[axis], dv.inputs[0])
    nt.links.new(dv.outputs[0], ramp.inputs["Fac"])
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = noise
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.blend_type = "MULTIPLY"
    mix.inputs["Factor"].default_value = 0.35
    nt.links.new(ramp.outputs["Color"], mix.inputs["A"])
    nt.links.new(tex.outputs["Color"], mix.inputs["B"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    bp = nt.nodes.new("ShaderNodeBump")
    bp.inputs["Strength"].default_value = 0.15
    nt.links.new(tex.outputs["Fac"], bp.inputs["Height"])
    nt.links.new(bp.outputs["Normal"], b.inputs["Normal"])
    return m


class Actor:
    """Персонаж зі скелетом. kind: andriy / man / old / child / hanna / woman."""

    def __init__(self, mats, kind="andriy", name="a", height=1.8):
        self.kind = kind
        fem = kind in ("hanna", "woman")
        new, acts = _import("Michelle.glb" if fem else "Xbot.glb")
        self.arm = next(o for o in new if o.type == "ARMATURE")
        self.meshes = [o for o in new if o.type == "MESH"]
        self.acts = acts
        self.root = bpy.data.objects.new(name + "_root", None)
        link(self.root)
        self.arm.parent = self.root
        # масштаб: модель ~1.8 м (Xbot) / ~1.6 м (Michelle)
        base = 1.8 if not fem else 1.62
        k = height / base
        self.name = name
        self._dress(mats, fem)
        self.root.scale = (k, k, k)
        self.arm.animation_data_create()
        self.track = self.arm.animation_data.nla_tracks.new()

    def bone(self, key):
        for b in self.arm.data.bones:
            if b.name.lower().endswith(key.lower()):
                return b.name
        return None

    def _dress(self, mats, fem):
        k = self.kind
        if fem:
            top = (0.30, 0.30, 0.31) if k == "hanna" else (0.32, 0.26, 0.2)
            m = cloth_gradient(self.name + "_cl", top, (0.045, 0.032, 0.028), split_z=0.56,
                               skin=(0.6, 0.45, 0.38), head_z=0.845, axis="Y", height=161.0)
        elif k == "andriy":
            m = cloth_gradient(self.name + "_cl", (0.075, 0.095, 0.04), (0.04, 0.05, 0.075), split_z=0.5)
        elif k == "child":
            m = cloth_gradient(self.name + "_cl", (0.6, 0.56, 0.48), (0.5, 0.46, 0.4), split_z=0.5)
        else:
            m = cloth_gradient(self.name + "_cl", (0.58, 0.54, 0.46) if k == "man" else (0.2, 0.17, 0.13),
                               (0.16, 0.13, 0.1), split_z=0.5, skin=(0.55, 0.4, 0.32))
        for o in self.meshes:
            o.data.materials.clear()
            o.data.materials.append(m)
            setp(o, "visible_shadow", True)
        head = self.bone("Head")
        if head is None:
            return
        bpy.context.view_layer.update()
        hb = self.arm.data.bones[head]
        hw = self.arm.matrix_world @ hb.head_local          # основа голови (світ)
        hc = hw + Vector((0, 0, 0.1 if not fem else 0.09))   # центр голови
        acc = []
        if fem:
            acc.append(sphere(hc + Vector((0, 0.025, 0.02)), 0.13, mats["scarf"], scale=(1.22, 1.12, 1.08)))
            acc.append(sphere(hc + Vector((0, 0.09, -0.07)), 0.12, mats["scarf"], scale=(1.15, 0.8, 1.25)))
            acc.append(sphere(hw + Vector((0, 0.02, -0.12)), 0.19, mats["shawl"], scale=(1.2, 0.75, 0.7)))
            bpy.ops.mesh.primitive_cone_add(vertices=32, radius1=0.3, radius2=0.16, depth=0.92,
                                            location=(hw.x, hw.y + 0.01, 0.46))
            sk = bpy.context.object
            sk.data.materials.append(mats["dress"])
            bpy.ops.object.shade_smooth()
            acc.append(("hips", sk))
        elif k == "andriy":
            acc.append(sphere(hc + Vector((0, 0.015, 0.035)), 0.102, mats["hair"], scale=(0.95, 1.02, 0.78)))
        elif k == "old":
            acc.append(sphere(hc + Vector((0, 0.0, 0.07)), 0.11, mats["villager"], scale=(1.08, 1.1, 0.42)))
        else:
            acc.append(sphere(hc + Vector((0, 0.015, 0.035)), 0.102, mats["hair"], scale=(0.95, 1.02, 0.75)))
        for it in acc:
            bone_name, o = (self.bone("Hips"), it[1]) if isinstance(it, tuple) else (head, it)
            mw = o.matrix_world.copy()
            o.parent = self.arm
            o.parent_type = "BONE"
            o.parent_bone = bone_name
            bpy.context.view_layer.update()
            o.matrix_world = mw

    # ---- анімація
    def play(self, action, f0, f1, speed=1.0, offset=0.0):
        """Відтворює дію (Walk/Run/Idle/sad_pose/...) з кадру f0 до f1 у 12 fps сцени."""
        act = self.acts.get(action) or self.acts.get(action.lower()) or self.acts.get(action.capitalize())
        if act is None:
            return
        scene_fps = bpy.context.scene.render.fps
        strip = self.track.strips.new(f"{action}_{f0}", int(f0), act)
        a0, a1 = act.frame_range
        strip.action_frame_start = a0 + offset
        strip.action_frame_end = a1
        strip.scale = scene_fps / SRC_FPS / speed
        length_needed = f1 - f0
        one = (a1 - a0 - offset) * strip.scale
        strip.repeat = max(1.0, length_needed / max(one, 1e-3))
        strip.extrapolation = "HOLD"
        return strip

    def place(self, loc, yaw_deg):
        self.root.location = loc
        self.root.rotation_euler = (0, 0, math.radians(yaw_deg))

    def path(self, pts, f0, f1, face=True):
        P = [Vector(p) for p in pts]
        L = [0.0]
        for a, b in zip(P, P[1:]):
            L.append(L[-1] + (b - a).length)
        tot = max(L[-1], 1e-6)
        for f in range(f0, f1 + 1):
            u = (f - f0) / max(f1 - f0, 1)
            d = u * tot
            i = min(max(j for j in range(len(L)) if L[j] <= d + 1e-9), len(P) - 2)
            seg = max(L[i + 1] - L[i], 1e-6)
            self.root.location = P[i].lerp(P[i + 1], (d - L[i]) / seg)
            if face:
                dv = P[i + 1] - P[i]
                self.root.rotation_euler = (0, 0, math.atan2(dv.y, dv.x) - math.pi / 2 + math.pi)
            self.root.keyframe_insert("location", frame=f)
            self.root.keyframe_insert("rotation_euler", frame=f)


def scan_head(loc, rot, size=0.25, name="head"):
    """Реалістична голова-скан (LeePerrySmith) з текстурами."""
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=os.path.join(MODELS, "LeePerrySmith.glb"))
    new = [o for o in bpy.data.objects if o not in before]
    mesh = next(o for o in new if o.type == "MESH")
    m = bpy.data.materials.new(name + "_skin")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    t = nt.nodes.new("ShaderNodeTexImage")
    t.image = bpy.data.images.load(os.path.join(MODELS, "Map-COL.jpg"))
    nt.links.new(t.outputs["Color"], b.inputs["Base Color"])
    n = nt.nodes.new("ShaderNodeTexImage")
    n.image = bpy.data.images.load(os.path.join(MODELS, "Infinite-Level_02_Tangent_SmoothUV.jpg"))
    n.image.colorspace_settings.name = "Non-Color"
    nm = nt.nodes.new("ShaderNodeNormalMap")
    nt.links.new(n.outputs["Color"], nm.inputs["Color"])
    nt.links.new(nm.outputs["Normal"], b.inputs["Normal"])
    b.inputs["Roughness"].default_value = 0.5
    setp(b.inputs["Subsurface Weight"], "default_value", 0.15)
    mesh.data.materials.clear()
    mesh.data.materials.append(m)
    root = bpy.data.objects.new(name, None)
    link(root)
    for o in new:
        if o.parent is None:
            o.parent = root
    dims = max(mesh.dimensions)
    k = size / max(dims, 1e-6)
    root.scale = (k, k, k)
    root.location = loc
    root.rotation_euler = rot
    return root, mesh
