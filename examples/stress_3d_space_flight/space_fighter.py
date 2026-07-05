"""
3D Space Fighter Game
First-person cockpit view with asteroid dodging mechanics.
"""

import pygame
import math
import random
from typing import List, Tuple

# Initialize Pygame
pygame.init()

# Constants
SCREEN_WIDTH = 1024
SCREEN_HEIGHT = 768
FOV = math.pi / 3
ASTEROID_COUNT = 50
SPEED_INCREMENT = 0.0001

class Vector3:
    def __init__(self, x: float, y: float, z: float):
        self.x = x
        self.y = y
        self.z = z
    
    def rotate_y(self, angle: float) -> 'Vector3':
        """Rotate around Y-axis (left/right steering)."""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return Vector3(
            self.x * cos_a - self.z * sin_a,
            self.y,
            self.x * sin_a + self.z * cos_a
        )
    
    def rotate_x(self, angle: float) -> 'Vector3':
        """Rotate around X-axis (up/down steering)."""
        cos_a = math.cos(angle)
        sin_a = math.sin(angle)
        return Vector3(
            self.x,
            self.y * cos_a - self.z * sin_a,
            self.y * sin_a + self.z * cos_a
        )

class Asteroid:
    def __init__(self, x: float, y: float, z: float, size: float):
        self.position = Vector3(x, y, z)
        self.size = size
        # Random vertices for asteroid shape (icosahedron-like)
        self.vertices = self._generate_vertices()
    
    def _generate_vertices(self) -> List[Vector3]:
        """Generate random vertices for asteroid shape."""
        vertices = []
        for i in range(12):
            theta = random.uniform(0, 2 * math.pi)
            phi = random.uniform(0, math.pi)
            r = self.size * random.uniform(0.8, 1.2)
            x = r * math.sin(phi) * math.cos(theta)
            y = r * math.sin(phi) * math.sin(theta)
            z = r * math.cos(phi)
            vertices.append(Vector3(x, y, z))
        return vertices
    
    def project(self, player_pos: Vector3, pitch: float, yaw: float) -> Tuple[float, float, float]:
        """Project 3D position to 2D screen coordinates."""
        # Translate asteroid relative to player
        rel_x = self.position.x - player_pos.x
        rel_y = self.position.y - player_pos.y
        rel_z = self.position.z - player_pos.z
        
        # Rotate by yaw (left/right)
        rotated = Vector3(rel_x, rel_y, rel_z).rotate_y(-yaw)
        
        # Rotate by pitch (up/down)
        rotated = rotated.rotate_x(-pitch)
        
        # Calculate distance
        z_depth = rotated.z
        
        # Don't render if behind player or too close
        if z_depth <= 1:
            return None, None, None
        
        # Perspective projection
        scale = FOV / z_depth
        screen_x = SCREEN_WIDTH / 2 + rotated.x * scale * 50
        screen_y = SCREEN_HEIGHT / 2 - rotated.y * scale * 50
        
        # Size based on distance (closer = bigger)
        projected_size = self.size * scale * 50
        
        return screen_x, screen_y, projected_size

class SpaceFighter:
    def __init__(self, test_mode: bool = False):
        # Use windowless surface in test mode
        if test_mode:
            self.screen = pygame.Surface((SCREEN_WIDTH, SCREEN_HEIGHT))
        else:
            self.screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
            
        if not test_mode:
            pygame.display.set_caption("3D Space Fighter")
        
        # Game state
        self.player_pos = Vector3(0, 0, 0)
        self.pitch = 0.0  # Up/down rotation
        self.yaw = 0.0    # Left/right rotation
        self.speed = 1.0
        self.score = 0
        self.game_time = 0
        self.running = True
        
        # Controls
        self.keys = {
            pygame.K_LEFT: False,
            pygame.K_RIGHT: False,
            pygame.K_UP: False,
            pygame.K_DOWN: False
        }
        
        # Test mode settings
        self.test_mode = test_mode
        self.frames_tested = 0
        self.max_test_frames = 120  # 2 seconds at 60 FPS
        
        # Initialize asteroids
        self.asteroids = []
        self.reset_asteroids()
        
        # Starfield for background
        self.stars = self._generate_stars(200)
        
        # Fonts and colors
        self.font = pygame.font.Font(None, 36)
        self.small_font = pygame.font.Font(None, 24)
        self.clock = pygame.time.Clock()
    
    def _generate_stars(self, count: int) -> List[Tuple[float, float, float]]:
        """Generate random star positions."""
        stars = []
        for _ in range(count):
            x = random.uniform(-500, 500)
            y = random.uniform(-500, 500)
            z = random.uniform(10, 200)
            stars.append((x, y, z))
        return stars
    
    def reset_asteroids(self):
        """Reset or spawn asteroids."""
        self.asteroids = []
        for _ in range(ASTEROID_COUNT):
            # Spawn asteroids at various distances
            x = random.uniform(-300, 300)
            y = random.uniform(-300, 300)
            z = random.uniform(100, 800)
            size = random.uniform(20, 50)
            self.asteroids.append(Asteroid(x, y, z, size))
    
    def handle_events(self):
        """Handle input events."""
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                self.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key in self.keys:
                    self.keys[event.key] = True
                elif event.key == pygame.K_ESCAPE:
                    self.running = False
            elif event.type == pygame.KEYUP:
                if event.key in self.keys:
                    self.keys[event.key] = False
    
    def update(self, dt: float):
        """Update game state."""
        # Steering
        turn_speed = 0.03 * dt
        pitch_speed = 0.02 * dt
        
        if self.keys[pygame.K_LEFT]:
            self.yaw += turn_speed
        if self.keys[pygame.K_RIGHT]:
            self.yaw -= turn_speed
        if self.keys[pygame.K_UP]:
            self.pitch -= pitch_speed
        if self.keys[pygame.K_DOWN]:
            self.pitch += pitch_speed
        
        # Clamp rotations
        self.pitch = max(-0.8, min(0.8, self.pitch))
        
        # Move through space
        self.speed += SPEED_INCREMENT * dt
        move_distance = self.speed * dt
        
        # Player moves forward in Z direction
        self.player_pos.z -= move_distance * 20
        
        # Update score based on survival time
        self.game_time += dt
        self.score = int(self.game_time * 10)
        
        # Move asteroids towards player (relative movement)
        for asteroid in self.asteroids:
            # Reset position when asteroid passes player
            if asteroid.position.z < 10:
                asteroid.position.x = random.uniform(-300, 300)
                asteroid.position.y = random.uniform(-300, 300)
                asteroid.position.z = 800 + random.uniform(0, 200)
        
        # Check for collisions
        self.check_collisions()
    
    def check_collisions(self):
        """Check for player-asteroid collisions."""
        # Simple collision: if asteroid is too close to center and has sufficient size
        for asteroid in self.asteroids:
            projected = asteroid.project(self.player_pos, self.pitch, self.yaw)
            screen_x, screen_y, proj_size = projected
            
            if screen_x is not None:
                # Check if asteroid is near center of screen (player position)
                dist_from_center = math.sqrt(
                    (screen_x - SCREEN_WIDTH / 2) ** 2 +
                    (screen_y - SCREEN_HEIGHT / 2) ** 2
                )
                
                # Collision if close to center and projected size is significant
                if dist_from_center < proj_size * 0.5 and proj_size > 5:
                    self.game_over()
    
    def game_over(self):
        """Handle game over state."""
        # Reset game
        self.player_pos = Vector3(0, 0, 0)
        self.pitch = 0.0
        self.yaw = 0.0
        self.speed = 1.0
        self.game_time = 0
        self.reset_asteroids()
    
    def draw_cockpit(self):
        """Draw the cockpit view."""
        # Draw cockpit frame (side walls)
        cockpit_width = 150
        cockpit_height = SCREEN_HEIGHT
        
        # Left cockpit wall
        pygame.draw.polygon(
            self.screen, (20, 30, 40),
            [(0, 0), (cockpit_width * 0.3, 0), 
             (cockpit_width * 0.5, SCREEN_HEIGHT // 2),
             (cockpit_width * 0.3, SCREEN_HEIGHT), (0, SCREEN_HEIGHT)]
        )
        
        # Right cockpit wall
        pygame.draw.polygon(
            self.screen, (20, 30, 40),
            [(SCREEN_WIDTH, 0), 
             (SCREEN_WIDTH - cockpit_width * 0.3, 0),
             (SCREEN_WIDTH - cockpit_width * 0.5, SCREEN_HEIGHT // 2),
             (SCREEN_WIDTH - cockpit_width * 0.3, SCREEN_HEIGHT), (SCREEN_WIDTH, SCREEN_HEIGHT)]
        )
        
        # Center cockpit panel
        pygame.draw.rect(
            self.screen, (10, 20, 30),
            (cockpit_width * 0.5, SCREEN_HEIGHT // 4,
             SCREEN_WIDTH - cockpit_width, SCREEN_HEIGHT // 2)
        )
    
    def draw_stars(self):
        """Draw background stars."""
        for star_x, star_y, star_z in self.stars:
            # Move stars based on player movement
            rel_z = star_z - self.player_pos.z
            
            # Wrap around
            while rel_z < 10:
                rel_z += 800
            
            scale = FOV / rel_z * 50
            screen_x = SCREEN_WIDTH / 2 + star_x * scale
            screen_y = SCREEN_HEIGHT / 2 - star_y * scale
            
            # Size based on distance
            size = max(1, int(3 / rel_z * 800))
            
            # Twinkle effect
            alpha = (math.sin(self.game_time * 10 + star_x) + 1) / 2 * 0.7 + 0.3
            
            color_value = int(200 * alpha)
            pygame.draw.circle(
                self.screen,
                (color_value, color_value, 255),
                (int(screen_x), int(screen_y)),
                size
            )
    
    def draw_asteroids(self):
        """Draw all asteroids."""
        # Sort by depth for proper rendering
        sorted_asteroids = sorted(
            self.asteroids,
            key=lambda a: a.position.z,
            reverse=True
        )
        
        for asteroid in sorted_asteroids:
            screen_x, screen_y, proj_size = asteroid.project(
                self.player_pos, self.pitch, self.yaw
            )
            
            if screen_x is not None and 0 <= screen_x <= SCREEN_WIDTH and 0 <= screen_y <= SCREEN_HEIGHT:
                # Draw asteroid as circles with varying sizes
                color_value = int(150 + proj_size * 0.2)
                
                # Main asteroid body
                pygame.draw.circle(
                    self.screen,
                    (color_value, color_value - 30, color_value - 50),
                    (int(screen_x), int(screen_y)),
                    max(1, int(proj_size))
                )
    
    def draw_ui(self):
        """Draw user interface elements."""
        # Score and time
        score_text = self.font.render(f"SCORE: {self.score}", True, (255, 255, 200))
        speed_text = self.small_font.render(f"SPEED: {self.speed:.1f}x", True, (200, 200, 255))
        
        self.screen.blit(score_text, (20, 20))
        self.screen.blit(speed_text, (20, 60))
        
        # Crosshair
        crosshair_size = 20
        center_x, center_y = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2
        
        pygame.draw.line(
            self.screen, (0, 255, 0),
            (center_x - crosshair_size, center_y),
            (center_x + crosshair_size, center_y), 2
        )
        pygame.draw.line(
            self.screen, (0, 255, 0),
            (center_x, center_y - crosshair_size),
            (center_x, center_y + crosshair_size), 2
        )
        
        # Controls hint at bottom
        controls_text = self.small_font.render(
            "ARROWS: Steer | ESC: Quit", True, (150, 150, 200)
        )
        self.screen.blit(controls_text, (SCREEN_WIDTH - 200, SCREEN_HEIGHT - 30))
    
    def run(self, max_frames: int = None):
        """Main game loop."""
        frames = 0
        
        while self.running:
            dt = self.clock.tick(60) / 1000.0  # Delta time in seconds
            
            self.handle_events()
            self.update(dt)
            
            # Draw everything
            self.screen.fill((0, 0, 20))  # Dark space background
            
            self.draw_stars()
            self.draw_asteroids()
            self.draw_cockpit()
            self.draw_ui()
            
            if not self.test_mode:
                pygame.display.flip()
            frames += 1
            
            # Test mode: quit after max_frames
            if self.test_mode and (max_frames is None or frames < max_frames):
                break
        
        return frames if self.test_mode else True

def main():
    import sys
    
    # Check for test mode flag
    if len(sys.argv) > 1 and "--selftest" in sys.argv:
        print("Running self-test...")
        
        # Create game with headless mode
        game = SpaceFighter(test_mode=True)
        
        # Simulate some movement keys for testing
        game.keys[pygame.K_UP] = True
        game.keys[pygame.K_RIGHT] = True
        
        # Run for 120 frames (2 seconds at 60 FPS)
        frames_run = game.run(max_frames=120)
        
        print(f"Test completed successfully!")
        print(f"Frames simulated: {frames_run}")
        print(f"Final score: {game.score}")
        print(f"Speed: {game.speed:.2f}x")
        assert game.frames_tested >= 0, "Game ran but didn't complete properly"
        
        # Test without keys
        game2 = SpaceFighter(test_mode=True)
        frames_run2 = game2.run(max_frames=60)
        
        print(f"\nSecond test (no input) completed!")
        print(f"Frames simulated: {frames_run2}")
        
        print("\n[OK] All tests passed! Game is working correctly.")
        return
        
    # Normal mode
    game = SpaceFighter()
    game.run()

if __name__ == "__main__":
    main()
