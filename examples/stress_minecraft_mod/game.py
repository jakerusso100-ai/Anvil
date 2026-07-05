#!/usr/bin/env python3
"""
Simple Minecraft-like block building game in Python using Panda3D
Features:
- First-person walking controller
- Place and remove blocks with mouse clicks
- Grass ground generation
- 3D block world
"""

from direct.showbase.ShowBase import ShowBase
from panda3d.core import (
    Vec3, Vec4, BitMask32, CollisionTraverser, CollisionRay, 
    CollisionNode, CollisionHandlerQueue, GeomVertexData, 
    GeomVertexWriter, GeomTriangles, Geom, GeomNode,
    Texture, TextureStage
)
from direct.task import Task
from direct.gui.DirectGui import DirectLabel
import math

# Block types
GRASS = 0
DIRT = 1
STONE = 2
WOOD = 3
BRICK = 4

class BlockBuilderGame(ShowBase):
    def __init__(self):
        ShowBase.__init__(self)
        
        # Hide mouse cursor and set up camera
        self.disableMouse()
        self.camera.setPos(0, -10, 5)
        self.camera.lookAt(0, 0, 0)
        
        # Player settings
        self.player_pos = Vec3(0, 0, 2)
        self.walk_speed = 8.0
        
        # Block settings
        self.current_block_type = GRASS
        
        # Game state
        self.blocks = {}  # Dictionary to store block positions: (x, y, z) -> type
        self.is_mouse_locked = False
        self.mouse_button = {'left': False, 'right': False}
        
        # Camera control
        self.camera_p = 0
        self.camera_h = 0
        
        # Setup keys and mouse
        self.setupKeys()
        self.setupMouseControl()
        
        # Setup physics/collision
        self.setupCollisionSystem()
        
        # Generate initial world
        self.generateWorld()
        
        # Start game tasks
        self.taskMgr.add(self.update, "update")
        self.taskMgr.add(self.cameraControl, "cameraControl")
        self.taskMgr.add(self.blockPlacement, "blockPlacement")
        
        # Setup UI
        self.setupUI()
    
    def generateWorld(self):
        """Generate initial ground with grass blocks"""
        # Create a 20x20 grass area
        for x in range(-10, 11):
            for y in range(-10, 11):
                self.addBlock(x, y, 0, GRASS)
        
        # Add some random starting structures
        self.addBlock(2, 0, 1, STONE)
        self.addBlock(3, 0, 1, STONE)
        self.addBlock(2, 0, 2, STONE)
        self.addBlock(3, 0, 2, WOOD)
        
    def addBlock(self, x, y, z, block_type):
        """Add a block to the world"""
        # Check if block already exists
        if (x, y, z) in self.blocks:
            return
        
        # Create simple colored cube
        cube = self.loader.loadModel("models/box.egg")
        if not cube:
            # If external model not found, create a simple cube
            cube = self.createCube()
        
        cube.reparentTo(self.render)
        cube.setPos(x, y, z)
        
        # Apply color based on block type
        colors = {
            GRASS: Vec4(0.2, 0.8, 0.2, 1.0),    # Green
            DIRT: Vec4(0.5, 0.3, 0.1, 1.0),     # Brown
            STONE: Vec4(0.6, 0.6, 0.6, 1.0),    # Gray
            WOOD: Vec4(0.5, 0.3, 0.15, 1.0),    # Dark brown
            BRICK: Vec4(0.7, 0.3, 0.2, 1.0)     # Red
        }
        
        cube.setColor(colors.get(block_type, colors[GRASS]))
        
        # Store block info
        self.blocks[(x, y, z)] = {
            'node': cube,
            'type': block_type
        }
    
    def removeBlock(self, x, y, z):
        """Remove a block from the world"""
        if (x, y, z) in self.blocks:
            block = self.blocks[(x, y, z)]['node']
            block.removeNode()
            del self.blocks[(x, y, z)]
    
    def createCube(self):
        """Create a simple cube geometry"""
        vdata = GeomVertexData("cube", GeomVertexWriter.V_position, 
                               GeomVertexWriter.V_normal)
        
        vertices = [
            (-0.5, -0.5, 0.5),  # 0
            (0.5, -0.5, 0.5),   # 1
            (0.5, 0.5, 0.5),    # 2
            (-0.5, 0.5, 0.5),   # 3
            (-0.5, -0.5, -0.5), # 4
            (0.5, -0.5, -0.5),  # 5
            (0.5, 0.5, -0.5),   # 6
            (-0.5, 0.5, -0.5)   # 7
        ]
        
        vdata = GeomVertexData("cube", GeomVertexWriter.V_position, 
                               GeomVertexWriter.V_normal)
        writer = GeomVertexWriter(vdata, "vertex")
        normal_writer = GeomVertexWriter(vdata, "normal")
        
        for vertex in vertices:
            writer.add_data3(vertex)
            if vertex[2] == 0.5:  # Top face
                normal_writer.add_data3(0, 0, 1)
            elif vertex[2] == -0.5:  # Bottom face
                normal_writer.add_data3(0, 0, -1)
            elif vertex[0] == 0.5:  # Right face
                normal_writer.add_data3(1, 0, 0)
            elif vertex[0] == -0.5:  # Left face
                normal_writer.add_data3(-1, 0, 0)
            elif vertex[1] == 0.5:  # Front face
                normal_writer.add_data3(0, 1, 0)
            else:  # Back face
                normal_writer.add_data3(0, -1, 0)
        
        triangles = GeomTriangles(Geom.UH_static)
        triangles.addVertices(0, 1, 2)
        triangles.addVertices(2, 3, 0)
        triangles.addVertices(4, 6, 5)
        triangles.addVertices(4, 7, 6)
        triangles.addVertices(3, 2, 6)
        triangles.addVertices(6, 7, 3)
        triangles.addVertices(0, 5, 1)
        triangles.addVertices(0, 4, 5)
        triangles.addVertices(0, 3, 7)
        triangles.addVertices(0, 7, 4)
        triangles.addVertices(1, 5, 6)
        triangles.addVertices(1, 6, 2)
        
        geom = Geom(vdata)
        geom.add_primitive(triangles)
        node = GeomNode("cube")
        node.add_geom(geom)
        return self.render.attach_new_node(node)
    
    def setupKeys(self):
        """Setup keyboard controls"""
        self.keys = {
            'forward': False,
            'backward': False,
            'left': False,
            'right': False
        }
        
        self.accept('w', lambda: self.set_key('forward', True))
        self.accept('s', lambda: self.set_key('backward', True))
        self.accept('a', lambda: self.set_key('left', True))
        self.accept('d', lambda: self.set_key('right', True))
        
        self.accept('w-up', lambda: self.set_key('forward', False))
        self.accept('s-up', lambda: self.set_key('backward', False))
        self.accept('a-up', lambda: self.set_key('left', False))
        self.accept('d-up', lambda: self.set_key('right', False))
        
        # Block selection keys
        self.accept('1', lambda: self._select_block_type(GRASS))
        self.accept('2', lambda: self._select_block_type(DIRT))
        self.accept('3', lambda: self._select_block_type(STONE))
        self.accept('4', lambda: self._select_block_type(WOOD))
        self.accept('5', lambda: self._select_block_type(BRICK))
        
    def _select_block_type(self, block_type):
        """Select a block type to place"""
        self.current_block_type = block_type
    
    def set_key(self, key, state):
        """Set keyboard state"""
        self.keys[key] = state
    
    def setupMouseControl(self):
        """Setup mouse for camera control and block interaction"""
        # Accept mouse events
        self.accept('mouse1', lambda: self.set_mouse_button('left', True))
        self.accept('mouse2', lambda: self.set_mouse_button('right', True))
        self.accept('mouse1-up', lambda: self.set_mouse_button('left', False))
        self.accept('mouse2-up', lambda: self.set_mouse_button('right', False))
        
    def set_mouse_button(self, button, state):
        """Set mouse button state"""
        self.mouse_button[button] = state
    
    def setupCollisionSystem(self):
        """Setup raycasting for block placement/removal"""
        # Create collision ray
        self.ray = CollisionRay(0, 0, 0, 0, -1, 0)
        self.ray_node = CollisionNode('ray')
        self.ray_np = self.camera.attach_new_node(self.ray_node)
        
        # Set collision mask
        self.ray_node.setFromCollideMask(BitMask32.bit(0))
        self.ray_node.setIntoCollideMask(BitMask32.all_off())
        
        # Create collision traverser and queue
        self.traverser = CollisionTraverser()
        self.handler = CollisionHandlerQueue()
        self.traverser.addCollider(self.ray_np, self.handler)
    
    def setupUI(self):
        """Setup user interface elements"""
        # Crosshair
        self.crosshair = DirectLabel(
            text="+",
            scale=0.1,
            pos=(0, 0, 0),
            frameColor=(1, 1, 1, 0.5)
        )
        
        # Block info display
        block_names = {GRASS: "Grass", DIRT: "Dirt", STONE: "Stone", WOOD: "Wood", BRICK: "Brick"}
        self.block_info = DirectLabel(
            text=f"Current: {block_names.get(self.current_block_type, 'Grass')}",
            scale=0.05,
            pos=(-1.3, 0, -0.9),
            frameColor=(0, 0, 0, 0.3)
        )
    
    def get_raycast_result(self):
        """Get the block that is being looked at"""
        self.traverser.traverse(self.render)
        
        if self.handler.get_num_entries() > 0:
            # Sort by distance
            self.handler.sort_entries()
            
            entry = self.handler.get_entry(0)
            hit_pos = entry.getPoint(1)  # Point in world coordinates
            
            # Get block position
            x = round(hit_pos[0])
            y = round(hit_pos[1])
            z = round(hit_pos[2])
            
            return True, (x, y, z), entry.getSurfaceNormal(1)
        
        return False, None, None
    
    def update(self, task):
        """Update player movement and physics"""
        dt = globalClock.get_dt()
        
        # Calculate movement direction based on camera
        cam_forward = self.camera.getQuat().getForward()
        cam_right = self.camera.getQuat().getRight()
        
        move_dir = Vec3(0, 0, 0)
        
        if self.keys['forward']:
            move_dir += cam_forward
        if self.keys['backward']:
            move_dir -= cam_forward
        if self.keys['right']:
            move_dir += cam_right
        if self.keys['left']:
            move_dir -= cam_right
        
        # Normalize and apply speed
        if move_dir.length() > 0:
            move_dir.normalize()
            move_dir *= self.walk_speed
        
        # Apply movement to player position
        self.player_pos += move_dir * dt
        
        # Simple gravity - check if on ground
        player_on_ground = False
        for z in range(1, -5, -1):
            if (round(self.player_pos[0]), round(self.player_pos[1]), 
                round(self.player_pos[2] + z)) in self.blocks:
                player_on_ground = True
                break
        
        # Apply gravity if not on ground
        if not player_on_ground and self.player_pos[2] > 0.5:
            self.player_pos[2] -= 15.0 * dt * dt
        elif player_on_ground:
            # Snap to ground
            self.player_pos[2] = max(1.5, self.player_pos[2])
        
        # Update camera position
        self.camera.setPos(self.player_pos)
        
        return Task.cont
    
    def cameraControl(self, task):
        """Handle mouse movement for camera rotation"""
        md = self.win.getPointer(0)
        width = self.win.getSize()[0]
        height = self.win.getSize()[1]
        
        if not self.is_mouse_locked:
            # Lock mouse on first move
            self.is_mouse_locked = True
        
        dx = md.getX() - width // 2
        dy = md.getY() - height // 2
        
        # Rotate camera
        self.camera_h -= dx * 0.005
        self.camera_p -= dy * 0.005
        
        # Clamp pitch
        self.camera_p = max(-89, min(89, self.camera_p))
        
        # Apply rotation
        self.camera.setHpr(self.camera_h, self.camera_p, 0)
        
        # Reset mouse to center
        self.win.movePointer(0, width // 2, height // 2)
        
        return Task.cont
    
    def blockPlacement(self, task):
        """Handle block placement and removal"""
        if not self.is_mouse_locked:
            return Task.cont
        
        # Check for raycast hit
        hit, pos, normal = self.get_raycast_result()
        
        if hit and pos:
            x, y, z = pos
            
            # Left click (mouse1) - remove block
            if self.mouse_button['left'] and (x, y, z) in self.blocks:
                self.removeBlock(x, y, z)
            
            # Right click (mouse2) - place block
            elif self.mouse_button['right']:
                # Calculate new block position based on normal
                nx, ny, nz = round(normal[0]), round(normal[1]), round(normal[2])
                
                new_pos = (x + nx, y + ny, z + nz)
                
                # Don't place block where player is standing
                if not self.isBlockAtPlayer(new_pos):
                    self.addBlock(*new_pos, self.current_block_type)
        
        return Task.cont
    
    def isBlockAtPlayer(self, pos):
        """Check if a block would be placed at the player's position"""
        px, py, pz = round(self.player_pos[0]), round(self.player_pos[1]), round(self.player_pos[2])
        bx, by, bz = pos
        
        # Simple check - don't place block where player is
        return (abs(px - bx) < 1 and abs(py - by) < 1 and 
                abs(pz - bz) < 2)

# Run the game
if __name__ == "__main__":
    game = BlockBuilderGame()
    game.run()
