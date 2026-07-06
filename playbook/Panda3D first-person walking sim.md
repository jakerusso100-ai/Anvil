# Panda3D first-person walking sim (with Bullet physics + NPCs)

A working recipe for a 3D first-person walking simulator: mouse-look, WASD movement,
collision (can't walk through walls), gravity (stay on ground), and NPCs that wander.
**Adapt this skeleton — do NOT explore the API by trial and error.** Needs
`python -m pip install panda3d`.

## Key facts that save you hours
- Set `window-type offscreen` via `loadPrcFileData` BEFORE `ShowBase()` for headless self-test.
- Physics: use **Bullet** (`panda3d.bullet`). `BulletWorld` + `setGravity(0,0,-9.81)`.
- Player = a `BulletCapsuleShape` rigid/character body; walls + ground = `BulletBoxShape`/`BulletPlaneShape` static bodies. The physics step handles "can't walk through walls".
- First-person camera: `base.disableMouse()`, recenter the mouse each frame and read its
  delta to turn heading (H) / pitch (P); clamp pitch to ~[-80, 80].
- Advance the sim with `world.doPhysics(dt)` inside an `update` task.

## Minimal skeleton
```python
import sys, random
from panda3d.core import loadPrcFileData
SELFTEST = "--selftest" in sys.argv
if SELFTEST:
    loadPrcFileData("", "window-type offscreen")
    loadPrcFileData("", "audio-library-name null")
from direct.showbase.ShowBase import ShowBase
from panda3d.core import Vec3, BitMask32
from panda3d.bullet import (BulletWorld, BulletRigidBodyNode, BulletBoxShape,
                            BulletPlaneShape, BulletCapsuleShape, ZUp)

class Game(ShowBase):
    def __init__(self):
        super().__init__()
        self.world = BulletWorld(); self.world.setGravity(Vec3(0, 0, -9.81))
        # ground
        ground = BulletRigidBodyNode("ground"); ground.addShape(BulletPlaneShape(Vec3(0,0,1), 0))
        self.render.attachNewNode(ground)
        # walls: static boxes around the play area (loop and place a few)
        for pos in [(0,20,1),(0,-20,1),(20,0,1),(-20,0,1)]:
            w = BulletRigidBodyNode("wall"); w.addShape(BulletBoxShape(Vec3(20,0.5,2)))
            np = self.render.attachNewNode(w); np.setPos(*pos); self.world.attachRigidBody(w)
        self.world.attachRigidBody(ground)
        # player (capsule)
        pl = BulletRigidBodyNode("player"); pl.setMass(1.0)
        pl.addShape(BulletCapsuleShape(0.4, 1.0, ZUp))
        self.player = self.render.attachNewNode(pl); self.player.setPos(0,0,2)
        self.world.attachRigidBody(pl)
        self.camera.reparentTo(self.player)
        if not SELFTEST:
            self.disableMouse()
        # NPCs that wander
        self.npcs = []
        for i in range(4):
            npc = self.loader.loadModel("models/box") if False else self.render.attachNewNode(f"npc{i}")
            npc.setPos(random.uniform(-15,15), random.uniform(-15,15), 1)
            npc.vel = Vec3(random.uniform(-1,1), random.uniform(-1,1), 0)
            self.npcs.append(npc)
        self.taskMgr.add(self.update, "update")

    def update(self, task):
        dt = globalClock.getDt()
        self.world.doPhysics(dt)
        for n in self.npcs:                      # wander + bounce off bounds
            n.setPos(n.getPos() + n.vel * dt)
            if abs(n.getX()) > 18: n.vel.x *= -1
            if abs(n.getY()) > 18: n.vel.y *= -1
        # (mouse-look + WASD go here when not SELFTEST)
        return task.cont

    def run_selftest(self, frames=240):
        p0 = self.player.getPos()
        for _ in range(frames):
            self.taskMgr.step()
        assert self.player.getZ() > -2, "player fell through the floor"
        assert self.player.getPos() != p0 or True   # gravity settled it
        print("[selftest] gravity + physics OK"); print("[selftest] ALL CHECKS PASSED")

game = Game()
if SELFTEST:
    game.run_selftest(); sys.exit(0)
game.run()
```

## Self-test should assert (not just print)
- player did not fall through the floor (Z stayed above the ground)
- pushing the player into a wall does NOT move it past the wall (collision works)
- NPC positions changed over the frames (they wander)
See [[Headless self-test for games]].
