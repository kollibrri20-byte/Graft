"""Переносить анімації Mixamo (з Xbot) на інші Mixamo-сумісні моделі й зберігає .blend-бібліотеку.

python3 retarget.py marvin.glb out/marvin.blend
"""
import math
import re
import sys

import bpy
from mathutils import Matrix, Quaternion, Vector

SRC = "/tmp/claude-0/models/Xbot.glb"
ACTIONS = ["walk", "run", "idle", "sad_pose", "sneak_pose", "agree", "headShake"]


def imp(p):
    b = set(bpy.data.objects)
    a0 = set(bpy.data.actions)
    bpy.ops.import_scene.gltf(filepath=p)
    return [o for o in bpy.data.objects if o not in b], [a for a in bpy.data.actions if a not in a0]


def clean(n):
    return re.sub(r"_\d+$", "", n.replace("mixamorig_", "mixamorig:"))


def main(src_glb, out_blend, name):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    sc = bpy.context.scene
    so, sacts = imp(SRC)
    sarm = next(o for o in so if o.type == "ARMATURE")
    to, _ = imp(src_glb)
    tarm = next(o for o in to if o.type == "ARMATURE")
    for b in tarm.data.bones:
        b.name = clean(b.name)
    for a in list(bpy.data.actions):           # прибираємо власні дії моделі
        if a not in sacts:
            bpy.data.actions.remove(a)
    pairs = [b.name for b in tarm.data.bones if b.name in sarm.data.bones]
    order = [b.name for b in tarm.data.bones if b.name in pairs]   # батьки йдуть першими
    bpy.context.view_layer.update()
    SW, TW = sarm.matrix_world.copy(), tarm.matrix_world.copy()
    srest = {n: (SW @ sarm.data.bones[n].matrix_local).to_quaternion() for n in pairs}
    trest = {n: (TW @ tarm.data.bones[n].matrix_local).to_quaternion() for n in pairs}
    off = {n: srest[n].inverted() @ trest[n] for n in pairs}
    # висота стегон для масштабування переміщення
    sh = (SW @ sarm.data.bones["mixamorig:Hips"].head_local).z
    th = (TW @ tarm.data.bones["mixamorig:Hips"].head_local).z
    kz = th / max(sh, 1e-6)
    s_h0 = SW @ sarm.data.bones["mixamorig:Hips"].head_local
    t_h0 = TW @ tarm.data.bones["mixamorig:Hips"].head_local
    TWi = TW.inverted()
    tarm.animation_data_create()
    sarm.animation_data_create()
    for aname in ACTIONS:
        act = next((a for a in sacts if a.name.lower() == aname.lower()), None)
        if act is None:
            continue
        sarm.animation_data.action = act
        try:
            sarm.animation_data.action_slot = act.slots[0]
        except Exception:
            pass
        new = bpy.data.actions.new(f"{name}_{aname}")
        tarm.animation_data.action = new
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        for f in range(f0, f1 + 1):
            sc.frame_set(f)
            M = {}
            for n in order:
                spb = sarm.pose.bones[n]
                sw = SW @ spb.matrix
                rot_w = sw.to_quaternion() @ off[n]
                tb = tarm.data.bones[n]
                if tb.parent and tb.parent.name in M:
                    p = tb.parent
                    fk = M[p.name] @ (p.matrix_local.inverted() @ tb.matrix_local)
                    pos = fk.to_translation()
                else:
                    if n == "mixamorig:Hips":
                        sp = sw.to_translation()
                        pos_w = t_h0 + (sp - s_h0) * kz
                        pos = TWi @ pos_w
                    else:
                        pos = tb.matrix_local.to_translation()
                    fk = None
                rot_a = (TWi.to_quaternion() @ rot_w)
                desired = Matrix.Translation(pos) @ rot_a.to_matrix().to_4x4()
                M[n] = desired
                if tb.parent and tb.parent.name in M:
                    p = tb.parent
                    base = M[p.name] @ (p.matrix_local.inverted() @ tb.matrix_local)
                else:
                    base = tb.matrix_local
                basis = base.inverted() @ desired
                pb = tarm.pose.bones[n]
                pb.rotation_mode = "QUATERNION"
                pb.rotation_quaternion = basis.to_quaternion()
                pb.keyframe_insert("rotation_quaternion", frame=f)
                if n == "mixamorig:Hips":
                    pb.location = basis.to_translation()
                    pb.keyframe_insert("location", frame=f)
        new.use_fake_user = True
        print("baked", new.name, f0, f1)
    tarm.animation_data.action = None
    for pb in tarm.pose.bones:
        pb.rotation_quaternion = (1, 0, 0, 0)
        pb.location = (0, 0, 0)
    for o in so:
        bpy.data.objects.remove(o, do_unlink=True)
    for a in sacts:
        bpy.data.actions.remove(a)
    bpy.ops.wm.save_as_mainfile(filepath=out_blend)


if __name__ == "__main__":
    a = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else sys.argv[1:]
    main(a[0], a[1], a[2])
