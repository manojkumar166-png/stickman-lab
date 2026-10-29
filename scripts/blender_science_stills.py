"""Local Blender scene renderer for static science illustrations."""
import bpy, json, os, sys, math, random
from mathutils import Vector

def material(name, color, roughness=0.3, metallic=0.0, emission=0.0):
    m=bpy.data.materials.new(name); m.diffuse_color=(*color,1); m.use_nodes=True
    bs=m.node_tree.nodes.get("Principled BSDF")
    bs.inputs["Base Color"].default_value=(*color,1)
    bs.inputs["Roughness"].default_value=roughness
    bs.inputs["Metallic"].default_value=metallic
    if emission:
        bs.inputs["Emission Color"].default_value=(*color,1)
        bs.inputs["Emission Strength"].default_value=emission
    return m

def sphere(name, loc, scale, mat):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=20, location=loc)
    o=bpy.context.object; o.name=name; o.scale=scale if isinstance(scale,tuple) else (scale,)*3
    o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth=True
    return o

def ring(name, loc, radius, mat, rot=(math.pi/2,0,0)):
    bpy.ops.mesh.primitive_torus_add(major_radius=radius, minor_radius=.025, location=loc, rotation=rot)
    o=bpy.context.object; o.name=name; o.data.materials.append(mat)
    for p in o.data.polygons: p.use_smooth=True
    return o

def reset():
    bpy.ops.object.select_all(action="SELECT"); bpy.ops.object.delete(use_global=False)

def setup(width,height):
    bpy.ops.object.camera_add(location=(0,-10,2.6))
    cam=bpy.context.object; target=Vector((0,0,.1))
    cam.rotation_euler=(target-cam.location).to_track_quat("-Z","Y").to_euler()
    cam.data.type="ORTHO"; cam.data.ortho_scale=8.5; bpy.context.scene.camera=cam
    for loc,energy,size in [((-4,-4,6),850,5),((4,-2,3),500,4),((0,3,4),900,3)]:
        bpy.ops.object.light_add(type="AREA",location=loc); l=bpy.context.object
        l.data.energy=energy; l.data.shape="DISK"; l.data.size=size
    sc=bpy.context.scene; sc.render.engine="BLENDER_EEVEE_NEXT"
    sc.render.resolution_x=width; sc.render.resolution_y=height; sc.render.resolution_percentage=70
    sc.render.image_settings.file_format="PNG"; sc.view_settings.view_transform="AgX"
    sc.world.color=(.012,.02,.06)
    floor=material("Midnight stage",(.012,.025,.07),.6)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-1.4))
    bpy.context.object.data.materials.append(floor)
    return sc

def create_subject(scene):
    words=(str(scene.get("title",""))+" "+str(scene.get("narration",""))[:500]).lower()
    blue=material("Sapphire",(.025,.22,.78),.22,.12)
    cyan=material("Energy cyan",(.02,.65,1),.2,.1,1.4)
    gold=material("Amber", (1,.43,.045),.24,.18)
    pink=material("Coral",(.95,.09,.28),.25)
    green=material("Leaf green",(.04,.43,.13),.32)
    pearl=material("Pearl",(.82,.91,1),.2)
    purple=material("Violet",(.32,.07,.68),.25)
    dark=material("Deep slate",(.035,.06,.13),.4,.1)
    if any(k in words for k in ("brain","neuron","memory","dream","sleep","nerve")):
        for x,z,r,m in [(-.8,.2,.52,pink),(-.4,.6,.58,pearl),(.2,.65,.62,pink),(.72,.35,.52,pink),(-.5,-.3,.48,purple),(.2,-.25,.56,pink),(.7,-.15,.4,pink)]:
            sphere("Brain lobe",(x,0,z),(r,.42,r*.8),m)
    elif any(k in words for k in ("sound","noise","hearing","ear","vibration","frequency","echo","music","pitch")):
        sphere("Sound source",(-1.3,0,.15),(.38,.35,.38),gold)
        for r in (.6,.95,1.35,1.8,2.25): ring("Sound wave",(-.7,0,.15),r,cyan)
        for i in range(12): sphere("Air particle",(-.1+i*.3,-.1,.1+math.sin(i*.8)*.2),(.05,)*3,pearl)
    elif any(k in words for k in ("molecule","atom","electron","chemical","dna","protein","bond")):
        pts=[(-1,.1,.2),(-.4,.1,.75),(.35,.1,.55),(1,.1,.05),(.4,.1,-.45),(-.4,.1,-.35)]
        for i,p in enumerate(pts):
            sphere("Atom",p,(.23,)*3,[cyan,gold,pink,green,purple,blue][i])
        for a,b in [(0,1),(1,2),(2,3),(3,4),(4,5),(5,0),(1,5)]:
            v1=Vector(pts[a]); v2=Vector(pts[b]); delta=v2-v1
            mid=(v1+v2)/2
            bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=.045,depth=delta.length,location=mid)
            o=bpy.context.object; o.rotation_euler=delta.to_track_quat("Z","Y").to_euler(); o.data.materials.append(pearl)
    elif any(k in words for k in ("plant","tree","photosynthesis","flower","forest","leaf","chlorophyll")):
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.08,depth=1.8,location=(0,0,0))
        bpy.context.object.data.materials.append(green)
        for x,z,a in [(-.4,.5,-25),(.4,.2,25),(-.4,-.1,20),(.4,.75,-25),(0,1,0)]:
            o=sphere("Leaf",(x,0,z),(.48,.12,.18),green); o.rotation_euler[1]=math.radians(a)
        sphere("Sun",(1.7,.2,1.2),(.42,.3,.42),gold)
    elif any(k in words for k in ("cell","bacteria","virus","microscope","organelle")):
        sphere("Cell membrane",(0,0,.1),(1.45,.55,1.05),cyan)
        sphere("Cell interior",(0,-.1,.1),(1.25,.48,.88),purple)
        sphere("Nucleus",(-.2,-.5,.2),(.45,.2,.42),pink)
        for p in [(.6,-.5,.45),(.65,-.45,-.25),(-.8,-.4,.25)]:
            sphere("Organelle",p,(.2,.12,.13),gold)
    elif any(k in words for k in ("volcano","eruption","lava","magma","fire","heat","lightning","storm")):
        bpy.ops.mesh.primitive_cone_add(vertices=48,radius1=1.45,radius2=.15,depth=2.3,location=(0,0,-.05))
        bpy.context.object.data.materials.append(dark)
        sphere("Lava glow",(0,-.2,1.0),(.3,.15,.15),gold)
        for i in range(12): sphere("Ember",(random.uniform(-.8,.8),-.1,random.uniform(.8,2)),(.06,)*3,gold)
    elif any(k in words for k in ("ocean","water","rain","ice","sea","river","underwater","current")):
        for i in range(6):
            pts=[(x,-.1,-.8+i*.25+math.sin(x*2+i)*.1) for x in [j*.1-3 for j in range(61)]]
            cu=bpy.data.curves.new("Wave","CURVE"); cu.dimensions="3D"; cu.bevel_depth=.025
            sp=cu.splines.new("POLY"); sp.points.add(len(pts)-1)
            for q,p in zip(sp.points,pts): q.co=(*p,1)
            ob=bpy.data.objects.new("Wave",cu); bpy.context.collection.objects.link(ob); cu.materials.append(cyan)
    else:
        # Space / general science gets a detailed planet with an atmosphere and moon.
        sphere("Hero planet",(-.2,0,.25),(1.25,1,1.25),blue)
        sphere("Continental feature",(-.7,-.85,.5),(.38,.06,.22),green)
        sphere("Continental feature",(.35,-.8,-.1),(.48,.06,.25),green)
        ring("Atmospheric rim",(-.2,0,.25),1.38,cyan,(math.radians(70),0,-.2))
        ring("Orbital path",(-.2,0,.25),1.9,gold,(math.radians(68),0,.3))
        sphere("Moon",(1.65,.1,.9),(.3,)*3,pearl)
        random.seed(10)
        for i in range(45): sphere("Star",(random.uniform(-3.8,3.8),1.3,random.uniform(-.1,3)),(.018,)*3,pearl)
    # Clean 3D typography is part of the rendered still, not a moving overlay.
    title=str(scene.get("title","SCIENCE")).upper()[:44]
    cu=bpy.data.curves.new("Scene title","FONT"); cu.body=title; cu.size=.19; cu.extrude=.002
    ob=bpy.data.objects.new("Scene title",cu); bpy.context.collection.objects.link(ob)
    ob.location=(-3.5,-.7,-1.22); ob.rotation_euler=(math.pi/2,0,0); cu.materials.append(pearl)

def main():
    args=sys.argv[sys.argv.index("--")+1:]
    story_path,outdir,width,height=args[0],args[1],int(args[2]),int(args[3])
    os.makedirs(outdir,exist_ok=True)
    with open(story_path,encoding="utf-8") as f: story=json.load(f)
    for i,scene in enumerate(story.get("scenes",[]),1):
        reset(); sc=setup(width,height); create_subject(scene)
        sc.render.filepath=os.path.abspath(os.path.join(outdir,f"scene-{i:03d}.png"))
        bpy.ops.render.render(write_still=True)
        print(f"Rendered static 3D still {i}: {scene.get('title','Scene')}",flush=True)

if __name__=="__main__": main()
