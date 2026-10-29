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
    sc=bpy.context.scene
    # EEVEE Next became the default engine in Blender 4.2; Blender 4.0/4.1 use BLENDER_EEVEE.
    sc.render.engine = "BLENDER_EEVEE_NEXT" if bpy.app.version >= (4, 2, 0) else "BLENDER_EEVEE"
    sc.render.resolution_x=width; sc.render.resolution_y=height; sc.render.resolution_percentage=100
    sc.render.image_settings.file_format="PNG"; sc.view_settings.view_transform="AgX"
    sc.world.color=(.012,.02,.06)
    floor=material("Midnight stage",(.012,.025,.07),.6)
    bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-1.4))
    bpy.context.object.data.materials.append(floor)
    return sc

def create_subject(scene):
    # Use the generated visual brief as well as narration to choose a relevant model.
    words=(" ".join(str(scene.get(k,"")) for k in ("title","visual","narration","background"))).lower()
    blue=material("Sapphire",(.025,.22,.78),.22,.12)
    cyan=material("Energy cyan",(.02,.65,1),.2,.1,1.4)
    gold=material("Amber", (1,.43,.045),.24,.18)
    pink=material("Coral",(.95,.09,.28),.25)
    green=material("Leaf green",(.04,.43,.13),.32)
    pearl=material("Pearl",(.82,.91,1),.2)
    purple=material("Violet",(.32,.07,.68),.25)
    dark=material("Deep slate",(.035,.06,.13),.4,.1)
    if any(k in words for k in ("heart","heartbeat","blood vessel","circulation","artery","vein")):
        # Heart chambers, vessels and circulating blood cells.
        sphere("Heart main chamber",(-.1,0,.15),(.72,.42,.85),pink)
        sphere("Heart left chamber",(-.52,-.02,.55),(.43,.4,.48),pink)
        sphere("Heart right chamber",(.42,-.02,.52),(.4,.4,.45),pink)
        for x,z,ang,mat in [(-.35,1.05,-18,blue),(.1,1.18,10,pink),(.52,.93,24,blue),(-.55,-.45,-25,pink),(.4,-.48,20,blue)]:
            bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.13,depth=.9,location=(x,-.02,z),rotation=(0,math.radians(ang),0))
            bpy.context.object.data.materials.append(mat)
        for i in range(18):
            a=i*2.399
            sphere("Blood cell",(.15+math.cos(a)*(.55+(i%3)*.12),-.5,.12+math.sin(a)*(.62+(i%4)*.08)),(.075,.035,.05),gold)
    elif any(k in words for k in ("lung","lungs","breathing","respiration","oxygen","alveol")):
        # Lungs with branching airways and alveoli.
        bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.13,depth=1.0,location=(0,0,.78))
        bpy.context.object.data.materials.append(gold)
        for x in (-.48,.48):
            sphere("Lung",(x,0,.05),(.52,.3,.82),pink)
            for j in range(3):
                start=Vector((0,-.05,.55-j*.13)); end=Vector((x*.72,-.08,.38-j*.2)); d=end-start
                bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.035,depth=d.length,location=(start+end)/2)
                o=bpy.context.object; o.rotation_euler=d.to_track_quat("Z","Y").to_euler(); o.data.materials.append(gold)
            for j in range(7):
                sphere("Alveoli",(x+random.uniform(-.3,.3),-.28,random.uniform(-.45,.42)),(.09,.07,.09),cyan)
    elif any(k in words for k in ("eye","eyes","vision","retina","pupil")):
        sphere("Eyeball",(0,0,.2),(1.0,.42,.7),pearl)
        sphere("Iris",(0,-.39,.2),(.37,.09,.38),blue)
        sphere("Pupil",(0,-.47,.2),(.17,.045,.2),dark)
        sphere("Eye highlight",(-.09,-.515,.32),(.07,.025,.07),pearl)
        for i in range(7):
            x=-1.6+i*.17
            bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.018,depth=.6,location=(x,-.05,.2),rotation=(0,math.radians(-20),0))
            bpy.context.object.data.materials.append(gold)
    elif any(k in words for k in ("brain","neuron","memory","dream","sleep","nerve")):
        for x,z,r,m in [(-.8,.2,.52,pink),(-.4,.6,.58,pearl),(.2,.65,.62,pink),(.72,.35,.52,pink),(-.5,-.3,.48,purple),(.2,-.25,.56,pink),(.7,-.15,.4,pink)]:
            sphere("Brain lobe",(x,0,z),(r,.42,r*.8),m)
        # Neural nodes and fine branches add depth to the brain model.
        random.seed(24)
        for i in range(24):
            x=random.uniform(-1.15,1.1); z=random.uniform(-.45,1.05)
            sphere("Neural node",(x,-.43,z),(.035,.025,.035),gold if i%3==0 else cyan)
        for i in range(10):
            x=-1.1+i*.23
            bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.012,depth=random.uniform(.25,.65),location=(x,-.4,random.uniform(-.2,.65)),rotation=(0,random.uniform(-.8,.8),0))
            bpy.context.object.data.materials.append(cyan)
    elif any(k in words for k in ("solar system","planet orbit","planets","saturn","jupiter","mars","earth","moon","galaxy","universe","black hole","space")):
        sunmat=material("Solar gold",(1,.55,.04),.22,.05,1.2)
        sphere("Sun",(-2.15,.15,.25),(.48,.42,.48),sunmat)
        for i,(x,z,r,col) in enumerate([(-1.05,.45,.16,blue),(-.55,-.15,.23,gold),(.25,.45,.29,green),(1.05,-.1,.2,pink),(2.0,.5,.42,purple)]):
            sphere("Planet",(x,.05,z),(r,r*.8,r),col)
            if i==4: ring("Planet rings",(x,.05,z),r*1.45,pearl,(math.radians(68),0,.2))
        random.seed(18)
        for i in range(85):
            sphere("Star",(random.uniform(-3.8,3.8),1.2,random.uniform(-.7,2.8)),(.012,)*3,pearl)
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
            bpy.ops.mesh.primitive_cylinder_add(vertices=10,radius=.012,depth=.7,location=(x,-.13,z),rotation=(0,math.radians(a),0))
            bpy.context.object.data.materials.append(pearl)
        for i in range(8):
            sphere("Photosynthesis particle",(-.9+i*.25,-.25,1.25+(i%2)*.15),(.035,)*3,gold if i%2 else cyan)
        sphere("Sun",(1.7,.2,1.2),(.42,.3,.42),gold)
    elif any(k in words for k in ("cell","bacteria","virus","microscope","organelle")):
        sphere("Cell membrane",(0,0,.1),(1.45,.55,1.05),cyan)
        sphere("Cell interior",(0,-.1,.1),(1.25,.48,.88),purple)
        sphere("Nucleus",(-.2,-.5,.2),(.45,.2,.42),pink)
        for p in [(.6,-.5,.45),(.65,-.45,-.25),(-.8,-.4,.25)]:
            sphere("Organelle",p,(.2,.12,.13),gold)
        for i in range(24):
            a=i*2*math.pi/24
            sphere("Membrane pore",(1.43*math.cos(a),-.12,.1+.99*math.sin(a)),(.035,.035,.035),pearl)
        for p in [(-.65,-.48,-.35),(.35,-.48,.65),(-.75,-.48,.05),(.8,-.4,.05)]:
            sphere("Mitochondrion",p,(.16,.08,.09),gold)
    elif any(k in words for k in ("ancient rome","roman empire","roman forum","colosseum","roman","ancient egypt","egyptian","pharaoh","pyramid","hieroglyph","ancient civilization","archaeology","archaeological","ancient greece","greek temple","mesopotamia","indus valley","maya civilization","aztec","medieval castle","medieval village","historical architecture","ancient history")):
        # Adaptive historical reconstruction: choose architecture from the scene's
        # own description rather than defaulting unfamiliar history to a planet.
        stone=material("Weathered limestone",(.63,.49,.31),.82)
        pale=material("Sunlit sandstone",(.88,.70,.43),.76)
        shadow=material("Carved stone",(.27,.22,.17),.9)
        accent=material("Ancient pigment",(.12,.34,.49),.48)
        sand=material("Desert ground",(.43,.28,.14),.95)
        bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-1.18))
        bpy.context.object.data.materials.append(sand)
        if any(k in words for k in ("egypt","pharaoh","pyramid","hieroglyph")):
            # Pyramids, temple pylons, obelisks and a stylized sphinx silhouette.
            for x,z,s in [(-1.45,-.12,1.55),(.65,-.25,1.15)]:
                bpy.ops.mesh.primitive_cone_add(vertices=4, radius1=s, radius2=0, depth=s*1.65, location=(x,.15,z), rotation=(0,0,math.radians(45)))
                obj=bpy.context.object; obj.name="Ancient Egyptian pyramid"; obj.data.materials.append(pale)
                obj.rotation_euler[0]=math.radians(90)
            # Temple pylons and a colonnaded entrance add scale and context.
            for x in (1.75,2.35):
                bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.05,-.05))
                obj=bpy.context.object; obj.name="Egyptian temple pylon"; obj.scale=(.42,.48,1.0); obj.data.materials.append(stone)
            for x in (-.2,.2,.6,1.0):
                bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.075,depth=.9,location=(x,-.28,-.25))
                obj=bpy.context.object; obj.name="Temple column"; obj.data.materials.append(pale)
                for z in (.17,-.66):
                    sphere("Carved column capital",(x,-.28,z),(.12,.12,.08),accent)
            # An obelisk and engraved-looking horizontal bands.
            bpy.ops.mesh.primitive_cube_add(size=1,location=(2.8,-.1,.0))
            obj=bpy.context.object; obj.name="Obelisk"; obj.scale=(.12,.13,.92); obj.data.materials.append(pale)
            bpy.ops.mesh.primitive_cone_add(vertices=4,radius1=.12,radius2=0,depth=.22,location=(2.8,-.1,.57))
            bpy.context.object.data.materials.append(accent)
        elif any(k in words for k in ("rome","roman","colosseum","forum")):
            # Roman amphitheatre facade, repeated arches, columns and tiled forum.
            bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.15,-.08))
            obj=bpy.context.object; obj.name="Roman amphitheatre core"; obj.scale=(3.6,.62,1.55); obj.data.materials.append(stone)
            for row,z in enumerate((-.38,.12,.62)):
                for i in range(9):
                    x=-1.55+i*.39
                    bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.22,z))
                    obj=bpy.context.object; obj.name="Roman arch opening"; obj.scale=(.25,.08,.30); obj.data.materials.append(shadow)
                    bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.045,depth=.42,location=(x-.18,-.28,z),rotation=(math.pi/2,0,0))
                    bpy.context.object.data.materials.append(pale)
            # Forum columns and pediment evoke a temple without requiring external assets.
            for x in (-2.35,-1.9,1.9,2.35):
                bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=.09,depth=.95,location=(x,-.48,-.22))
                obj=bpy.context.object; obj.name="Roman forum column"; obj.data.materials.append(pale)
            bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-.48,.28))
            obj=bpy.context.object; obj.name="Roman temple entablature"; obj.scale=(1.25,.16,.14); obj.data.materials.append(pale)
        else:
            # Fallback for other historical settings: layered settlement, walls,
            # towers, a central public building and repeated architectural detail.
            for i,(x,h,w) in enumerate([(-2.1,.8,.65),(-1.15,1.25,.8),(0,1.65,1.0),(1.2,1.0,.72),(2.15,.72,.55)]):
                bpy.ops.mesh.primitive_cube_add(size=1,location=(x,.1,-.55+h/2))
                obj=bpy.context.object; obj.name="Historic settlement building"; obj.scale=(w,.5,h); obj.data.materials.append(pale if i%2==0 else stone)
                for j in range(max(1,int(h*3))):
                    bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.17,-.4+j*.28))
                    obj=bpy.context.object; obj.name="Building inset"; obj.scale=(.11,.04,.15); obj.data.materials.append(shadow)
            for x in (-2.7,2.7):
                bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.12,depth=1.5,location=(x,.15,-.35))
                bpy.context.object.data.materials.append(stone)
    elif any(k in words for k in ("ocean","sea floor","underwater","coral reef","deep sea","marine","tide","ocean current","sea life","whale","shark","dolphin")):
        # Layered ocean diorama: deep water, textured waves, coral, fish, bubbles and seabed.
        deep=material("Ocean depth",(.008,.075,.24),.24,.1)
        teal=material("Tropical water",(.015,.34,.48),.22,.08)
        coral=material("Reef coral",(1,.19,.22),.3)
        sand=material("Seabed sand",(.55,.34,.14),.8)
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.35,-.95))
        seabed=bpy.context.object; seabed.name="Ocean floor"; seabed.scale=(7,.7,.22); seabed.data.materials.append(sand)
        for i in range(7):
            pts=[(x,-.25,-.25+i*.12+math.sin(x*2.2+i*.8)*.1) for x in [j*.1-3.5 for j in range(71)]]
            cu=bpy.data.curves.new("Layered ocean wave","CURVE"); cu.dimensions="3D"; cu.bevel_depth=.025 if i%2 else .04
            sp=cu.splines.new("POLY"); sp.points.add(len(pts)-1)
            for q,p in zip(sp.points,pts): q.co=(*p,1)
            ob=bpy.data.objects.new("Ocean wave",cu); bpy.context.collection.objects.link(ob); cu.materials.append(teal if i%2 else cyan)
        # Branching coral and sea plants on the seabed.
        for base_x,mat in [(-2.4,coral),(-1.8,pink),(2.3,gold)]:
            for j in range(5):
                height=.35+.12*(j%3)
                bpy.ops.mesh.primitive_cylinder_add(vertices=10,radius=.045,depth=height,location=(base_x+(j-2)*.09,-.25,-.45+height/2))
                bpy.context.object.data.materials.append(mat)
                sphere("Coral tip",(base_x+(j-2)*.09,-.25,-.45+height),(.07,.07,.07),mat)
        for i in range(9):
            x=-2.8+i*.68; z=random.uniform(-.05,.8)
            fish=sphere("Reef fish",(x,-.42,z),(.2,.07,.095),[gold,cyan,pink][i%3])
            tail=sphere("Fish tail",(x-.19,-.4,z),(.08,.035,.07),[gold,cyan,pink][i%3])
        for i in range(24):
            x=random.uniform(-3.2,3.2); z=random.uniform(-.1,1.5)
            sphere("Ocean bubble",(x,-.35,z),(.025,.025,.025),pearl)
        for x in (-2.8,2.7):
            for j in range(4):
                sphere("Sea plant",(x+j*.08,-.3,-.55+j*.08),(.08,.05,.22),green)
    elif any(k in words for k in ("weather","thunderstorm","cloud","rainfall","water cycle","hurricane","tornado","cyclone","lightning","storm","rain")):
        cloud=material("Cloud white",(.78,.88,1),.8)
        for x,z,s in [(-1.8,.8,.55),(-1.3,1,.65),(-.8,.8,.5),(.7,1,.6),(1.2,.8,.55)]:
            sphere("Cloud",(x,.1,z),(s,.3,s*.55),cloud)
        for i in range(22):
            x=-2.1+(i%11)*.42; z=.2-(i//11)*.35
            drop=sphere("Raindrop",(x,-.1,z),(.035,.035,.09),cyan); drop.rotation_euler[1]=math.radians(-12)
        # Lightning forks and a sun peeking through the clouds.
        if any(k in words for k in ("lightning","thunderstorm","storm","thunder")):
            for x in (-.2,1.5):
                for j in range(4):
                    bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.025,depth=.28,location=(x-j*.07,-.05,.55-j*.24),rotation=(0,math.radians(18),0))
                    bpy.context.object.data.materials.append(gold)
        sphere("Sun through clouds",(2.5,.2,1.3),(.28,.2,.28),gold)
    elif any(k in words for k in ("volcano","eruption","lava","magma","fire","heat","geothermal")):
        rock=material("Volcanic rock",(.09,.07,.08),.9)
        lava=material("Molten lava",(1,.12,.008),.22,.05,2.0)
        bpy.ops.mesh.primitive_cone_add(vertices=64,radius1=1.55,radius2=.18,depth=2.4,location=(0,0,-.05))
        mountain=bpy.context.object; mountain.name="Volcanic cone"; mountain.data.materials.append(rock)
        sphere("Crater glow",(0,-.18,1.08),(.36,.12,.13),lava)
        for i in range(20):
            x=random.uniform(-1.0,1.0); z=random.uniform(.75,2.0)
            sphere("Glowing ember",(x,-.25,z),(.035,.035,.045),gold if i%3 else lava)
        for x in (-.55,.25,.7):
            bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.035,depth=random.uniform(.45,.9),location=(x,-.24,random.uniform(-.55,.35)),rotation=(0,random.uniform(-.45,.45),0))
            bpy.context.object.data.materials.append(lava)
    elif any(k in words for k in ("electricity","electric circuit","circuit board","light bulb","current","voltage","magnet","magnetic field","electromagnet")):
        board=material("Circuit board",(.015,.16,.12),.3,.2)
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.15,-.15)); obj=bpy.context.object; obj.name="Circuit board"; obj.scale=(3.7,.18,1.35); obj.data.materials.append(board)
        for i in range(9):
            x=-1.55+i*.39
            bpy.ops.mesh.primitive_cylinder_add(vertices=24,radius=.11,depth=.08,location=(x,-.08,.05+(i%3)*.18),rotation=(math.pi/2,0,0))
            bpy.context.object.data.materials.append(gold if i%2 else cyan)
        for i in range(8):
            x=-1.7+i*.48
            bpy.ops.mesh.primitive_cylinder_add(vertices=8,radius=.025,depth=.55,location=(x,-.12,.25),rotation=(0,math.pi/2,0))
            bpy.context.object.data.materials.append(cyan)
        if any(k in words for k in ("magnet","magnetic field","electromagnet")):
            for x in (-.75,.75):
                bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.35,.65)); obj=bpy.context.object; obj.scale=(.42,.18,.35); obj.data.materials.append(pink if x<0 else blue)
            for i in range(5): ring("Magnetic field line",(0,-.2,.6),.5+i*.22,cyan)
    elif any(k in words for k in ("insect","bee","bees","butterfly","ant","pollination","spider","ladybug")):
        yellow=material("Insect gold",(1,.57,.04),.28)
        sphere("Insect body",(0,0,.2),(.55,.25,.28),yellow)
        sphere("Insect head",(.53,-.02,.28),(.23,.22,.22),dark)
        for x in (-.25,.05,.3):
            for side in (-1,1):
                bpy.ops.mesh.primitive_cylinder_add(vertices=10,radius=.025,depth=.48,location=(x,-.05,.0),rotation=(0,math.radians(side*35),side*.3))
                bpy.context.object.data.materials.append(dark)
        for x in (-.18,.18):
            wing=sphere("Translucent wing",(x,-.16,.58),(.28,.045,.19),pearl); wing.rotation_euler[1]=math.radians(x*90)
        for i in range(12):
            sphere("Pollen grain",(random.uniform(-1.4,1.4),-.25,random.uniform(-.25,1.1)),(.035,)*3,gold)
    elif any(k in words for k in ("dinosaur","fossil","prehistoric","paleontology")):
        bone=material("Fossil bone",(.78,.67,.46),.8)
        sphere("Dinosaur torso",(-.1,0,.15),(.9,.35,.42),green)
        sphere("Dinosaur head",(.8,-.02,.48),(.38,.3,.32),green)
        sphere("Dinosaur jaw",(.95,-.12,.27),(.3,.2,.1),bone)
        for x in (-.65,-.2,.25):
            bpy.ops.mesh.primitive_cone_add(vertices=8,radius1=.12,radius2=.025,depth=.38,location=(x,-.02,.55),rotation=(0,math.radians(90),0))
        for x in (-.55,.4):
            bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.09,depth=.48,location=(x,-.05,-.2),rotation=(0,math.radians(90),0))
            bpy.context.object.data.materials.append(green)
        for i in range(6):
            sphere("Fossil fragment",(random.uniform(-1.8,1.8),-.2,random.uniform(-.9,-.55)),(.12,.05,.07),bone)
    elif any(k in words for k in ("ocean","water","ice","sea","river","underwater","current","glacier","waterfall")):
        # Detailed layered water scene for general water-related topics.
        for i in range(8):
            pts=[(x,-.1,-.8+i*.2+math.sin(x*2+i)*.1) for x in [j*.1-3 for j in range(61)]]
            cu=bpy.data.curves.new("Water wave","CURVE"); cu.dimensions="3D"; cu.bevel_depth=.025
            sp=cu.splines.new("POLY"); sp.points.add(len(pts)-1)
            for q,p in zip(sp.points,pts): q.co=(*p,1)
            ob=bpy.data.objects.new("Water wave",cu); bpy.context.collection.objects.link(ob); cu.materials.append(cyan if i%2 else blue)
        for i in range(16):
            sphere("Water particle",(random.uniform(-3,3),-.3,random.uniform(-.5,.8)),(.025,)*3,pearl)
    elif any(k in words for k in ("robot","robotics","artificial intelligence","machine learning","computer","computing","processor","microchip","server","algorithm","automation","engineering","engine","vehicle","rocket","satellite","battery","solar panel","wind turbine","factory","industrial","technology","technology")):
        # Modular engineering/technology scene: chassis, components, connectors and indicator lights.
        metal=material("Brushed titanium",(.24,.31,.4),.26,.78)
        casing=material("Enamel casing",(.055,.16,.29),.28,.42)
        board=material("Circuit substrate",(.025,.23,.17),.35,.25)
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.05,.0))
        chassis=bpy.context.object; chassis.name="Technology chassis"; chassis.scale=(2.05,.55,1.05); chassis.data.materials.append(casing)
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,-.27,.02))
        core=bpy.context.object; core.name="Central processor"; core.scale=(.75,.12,.55); core.data.materials.append(metal)
        for x in (-.55,-.35,-.15,.05,.25,.45):
            for z in (-.22,.26):
                sphere("Processor contact",(x,-.36,z),(.035,.025,.035),gold)
        # Connected modules make this a system rather than an isolated generic sphere.
        for x,z in [(-1.25,.3),(-1.22,-.32),(1.2,.3),(1.22,-.3)]:
            bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.05,z))
            obj=bpy.context.object; obj.name="System module"; obj.scale=(.36,.35,.25); obj.data.materials.append(board)
            start=Vector((x*.7,-.28,z*.7)); end=Vector((0,-.3,0)); delta=end-start
            bpy.ops.mesh.primitive_cylinder_add(vertices=12,radius=.025,depth=delta.length,location=(start+end)/2)
            obj=bpy.context.object; obj.name="Module connector"; obj.rotation_euler=delta.to_track_quat("Z","Y").to_euler(); obj.data.materials.append(cyan)
        for i in range(14):
            sphere("Status indicator",(-.8+i*.12,-.38,.43),(.025,.02,.025),green if i%3 else gold)
        if any(k in words for k in ("robot","robotics","robot arm","automation")):
            # A simple articulated arm adds an immediately recognizable robotic silhouette.
            for loc,scale in [((-.8,-.45,.7),(.22,.18,.22)),((-.45,-.45,1.0),(.48,.13,.13)),((-.1,-.45,1.2),(.18,.15,.18)),((.25,-.45,1.0),(.42,.12,.12))]:
                sphere("Robot joint or link",loc,scale,metal)
            for x in (-.55,.0,.42):
                sphere("Robot joint",(x,-.48,1.0 if x!=-0.0 else 1.2),(.11,.1,.11),gold)
    else:
        # General-purpose conceptual composition for topics without a specialist builder.
        # Prefer objects named by the brief's strongest concrete nouns over a misleading planet.
        visual_text=str(scene.get("visual","")).strip()
        title_text=str(scene.get("title","")).strip()
        description=(visual_text+" "+title_text).lower()
        print("Using general-purpose concept builder for:", title_text, flush=True)
        hero_mat=material("Concept hero",(.08,.32,.58),.25,.22)
        accent_mat=material("Concept accent",(.98,.43,.09),.24,.12,0.25)
        pale_mat=material("Concept highlight",(.65,.85,.96),.25,.05)
        # Compose a layered, dimensional exhibit: central subject, supporting forms,
        # a grounded platform, and small details. The brief/title remains visible.
        bpy.ops.mesh.primitive_cube_add(size=1,location=(0,.15,-.92))
        plinth=bpy.context.object; plinth.name="Concept display plinth"; plinth.scale=(5.8,1.25,.16); plinth.data.materials.append(dark)
        if any(k in description for k in ("building","architecture","city","house","structure","bridge","tower")):
            for i,(x,h,w) in enumerate([(-1.65,.9,.7),(-.65,1.35,.8),(.45,1.05,.75),(1.45,1.55,.8)]):
                bpy.ops.mesh.primitive_cube_add(size=1,location=(x,.05,-.15+h/2))
                obj=bpy.context.object; obj.name="Architectural mass"; obj.scale=(w,.48,h); obj.data.materials.append(hero_mat if i%2==0 else pale_mat)
                for j in range(max(1,int(h*3))):
                    bpy.ops.mesh.primitive_cube_add(size=1,location=(x,-.22,-.15+j*.27))
                    obj=bpy.context.object; obj.name="Facade detail"; obj.scale=(.09,.035,.13); obj.data.materials.append(accent_mat)
        elif any(k in description for k in ("mountain","landscape","continent","geography","earthquake","tectonic","canyon","cave","rock","mineral")):
            for i,(x,z,s) in enumerate([(-1.7,-.05,.95),(-.55,.18,1.3),(.8,-.02,.85),(1.75,.05,.65)]):
                bpy.ops.mesh.primitive_cone_add(vertices=7,radius1=s,radius2=.08,depth=s*1.6,location=(x,.15,z))
                obj=bpy.context.object; obj.name="Terrain formation"; obj.data.materials.append([dark,hero_mat,pale_mat,green][i])
            for i in range(8):
                sphere("Terrain detail",(random.uniform(-2.5,2.5),-.35,random.uniform(-.75,.1)),(.045,.035,.04),accent_mat)
        elif any(k in description for k in ("energy","force","motion","gravity","field","wave","radiation","particle","light")):
            for i in range(5):
                ring("Concept field line",(0,.0,.0),.42+i*.28,cyan)
            for i in range(11):
                a=i*2*math.pi/11
                sphere("Concept particle",(math.cos(a)*(.65+(i%3)*.2),-.22,math.sin(a)*(.48+(i%2)*.16)),(.075,.065,.075),accent_mat if i%3==0 else hero_mat)
            sphere("Concept core",(0,-.18,0),(.42,.3,.42),pale_mat)
        else:
            # Neutral exhibit of linked components; avoids falsely claiming the subject is a planet.
            for i,(x,z,s) in enumerate([(-1.25,.15,.42),(-.55,.48,.55),(.25,.22,.68),(1.05,.48,.4)]):
                sphere("Concept component",(x,-.12,z),(s,.22,s*.82),hero_mat if i%2==0 else accent_mat)
            for a,b in [((-1.25,.15),(-.55,.48)),((-.55,.48),(.25,.22)),((.25,.22),(1.05,.48))]:
                p1=Vector((a[0],-.22,a[1])); p2=Vector((b[0],-.22,b[1])); delta=p2-p1
                bpy.ops.mesh.primitive_cylinder_add(vertices=16,radius=.025,depth=delta.length,location=(p1+p2)/2)
                obj=bpy.context.object; obj.name="Concept connection"; obj.rotation_euler=delta.to_track_quat("Z","Y").to_euler(); obj.data.materials.append(pale_mat)
            for i in range(18):
                x=-2.1+i*.24
                sphere("Fine detail",(x,-.34,-.48+(i%3)*.06),(.022,.02,.022),cyan)
    # Log the concrete visual brief to make topic mismatches easier to diagnose.
    print("Scene visual brief:", str(scene.get("visual",""))[:180], flush=True)
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
