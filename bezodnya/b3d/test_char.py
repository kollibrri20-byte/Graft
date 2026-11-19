import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import bpy
from lib import *
from character import Character
reset((0.02,0.03,0.05), 0.0)
c = Character("Host")
cam = camera((0.08, -0.95, 0.42), (0, 0, 0.36), lens=45)
light("AREA", (-0.5, -0.6, 0.8), 25, (1.0, 0.85, 0.7), target=(0,0,0.42), size=0.6)
light("AREA", (0.6, 0.4, 0.7), 30, (0.4, 0.7, 1.0), target=(0,0,0.45), size=0.4)
light("AREA", (0.3, -0.8, 0.2), 5, (0.5,0.8,1.0), target=(0,0,0.45), size=0.5)
out=sys.argv[sys.argv.index('--')+1]
for i,(j,w,r,b) in enumerate(((0,0,0,0),(0.9,0.2,0,0),(0.5,0,1,0),(0.6,0.8,0,0.2))):
    c.face(jaw=j, wide=w, round_=r, blink=b, brow=0.5 if i==3 else 0)
    bpy.context.scene.render.filepath=f"{out}/char{i}.jpg"
    bpy.ops.render.render(write_still=True)
