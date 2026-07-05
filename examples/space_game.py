#!/usr/bin/env python3
"""
Space Game - A modern take on asteroids with UFOs, power-ups, and smooth gameplay
"""

import pygame
import math
import random
import sys

# Initialize Pygame
pygame.init()
pygame.font.init()

# Screen dimensions
WIDTH, HEIGHT = 1024, 768
FPS = 60

# Colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
RED = (255, 50, 50)
GREEN = (50, 255, 50)
YELLOW = (255, 255, 50)
BLUE = (50, 50, 255)
ORANGE = (255, 165, 0)
PURPLE = (165, 50, 165)

# Game constants
SHIP_SIZE = 15
ASTEROID_SIZES = [40, 30, 20]  # Large, medium, small
ASTEROID_SPEEDS = [1.5, 2.5, 3.5]
LASER_SPEED = 8
LASER_RANGE = 800
SHIP_SPEED = 0.2
SHIP_TURN_SPEED = 4
FRICTION = 0.98

# Set up display
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("Space Defender")
clock = pygame.time.Clock()
font = pygame.font.Font(None, 36)
large_font = pygame.font.Font(None, 72)


class Vector:
    """Simple 2D vector class"""
    def __init__(self, x, y):
        self.x = x
        self.y = y
    
    def __add__(self, other):
        return Vector(self.x + other.x, self.y + other.y)
    
    def __sub__(self, other):
        return Vector(self.x - other.x, self.y - other.y)
    
    def __mul__(self, scalar):
        return Vector(self.x * scalar, self.y * scalar)
    
    def magnitude(self):
        return math.sqrt(self.x ** 2 + self.y ** 2)
    
    def normalize(self):
        mag = self.magnitude()
        if mag > 0:
            return Vector(self.x / mag, self.y / mag)
        return Vector(0, 0)


class Ship:
    """Player's spaceship"""
    def __init__(self):
        self.pos = Vector(WIDTH // 2, HEIGHT // 2)
        self.velocity = Vector(0, 0)
        self.angle = -math.pi / 2  # Pointing up
        self.radius = SHIP_SIZE
        self.lives = 3
        self.invincible_until = 0
        self.visible = True
    
    def update(self):
        # Apply friction
        self.velocity.x *= FRICTION
        self.velocity.y *= FRICTION
        
        # Update position
        self.pos += self.velocity
        
        # Screen wrapping
        if self.pos.x < 0:
            self.pos.x = WIDTH
        elif self.pos.x > WIDTH:
            self.pos.x = 0
        if self.pos.y < 0:
            self.pos.y = HEIGHT
        elif self.pos.y > HEIGHT:
            self.pos.y = 0
    
    def rotate(self, direction):
        """Rotate ship left or right"""
        self.angle += direction * math.radians(SHIP_TURN_SPEED)
    
    def thrust(self):
        """Apply thrust"""
        thrust_force = Vector(
            math.cos(self.angle) * SHIP_SPEED,
            math.sin(self.angle) * SHIP_SPEED
        )
        self.velocity += thrust_force
    
    def draw(self, surface):
        if not self.visible:
            return
        
        # Blink if invincible
        current_time = pygame.time.get_ticks()
        if current_time < self.invincible_until and (current_time // 100) % 2 == 0:
            return
        
        # Draw ship as a triangle
        tip = (
            self.pos.x + self.radius * math.cos(self.angle),
            self.pos.y + self.radius * math.sin(self.angle)
        )
        left = (
            self.pos.x + self.radius * math.cos(self.angle + 2.5),
            self.pos.y + self.radius * math.sin(self.angle + 2.5)
        )
        right = (
            self.pos.x + self.radius * math.cos(self.angle - 2.5),
            self.pos.y + self.radius * math.sin(self.angle - 2.5)
        )
        
        pygame.draw.polygon(surface, WHITE, [tip, left, right], 2)
    
    def get_hitbox(self):
        """Return circle hitbox for collision detection"""
        return (self.pos.x, self.pos.y, self.radius)


class Asteroid:
    """Asteroid object"""
    def __init__(self, x=None, y=None, size_idx=0):
        # Spawn at edge or random position
        if x is None:
            if random.random() < 0.5:
                x = random.choice([0, WIDTH])
                y = random.randint(0, HEIGHT)
            else:
                x = random.randint(0, WIDTH)
                y = random.choice([0, HEIGHT])
        else:
            x = x + random.randint(-20, 20)
            y = y + random.randint(-20, 20)
        
        self.pos = Vector(x, y)
        # Velocity away from center
        angle = math.atan2(HEIGHT/2 - y, WIDTH/2 - x) + random.uniform(-1, 1)
        speed = ASTEROID_SPEEDS[size_idx] * random.uniform(0.5, 1.5)
        self.velocity = Vector(
            math.cos(angle) * speed,
            math.sin(angle) * speed
        )
        
        self.size_idx = size_idx
        self.radius = ASTEROID_SIZES[size_idx]
        # Create jagged polygon shape
        self.vertices = []
        num_vertices = 8 + random.randint(0, 4)
        for i in range(num_vertices):
            angle = (2 * math.pi * i) / num_vertices
            r = self.radius * random.uniform(0.7, 1.3)
            self.vertices.append((r, angle))
        self.rotation = 0
        self.rot_speed = random.uniform(-0.05, 0.05)
    
    def update(self):
        self.pos += self.velocity
        self.rotation += self.rot_speed
        
        # Screen wrapping
        if self.pos.x < -self.radius:
            self.pos.x = WIDTH + self.radius
        elif self.pos.x > WIDTH + self.radius:
            self.pos.x = -self.radius
        if self.pos.y < -self.radius:
            self.pos.y = HEIGHT + self.radius
        elif self.pos.y > HEIGHT + self.radius:
            self.pos.y = -self.radius
    
    def draw(self, surface):
        # Calculate vertex positions
        points = []
        for r, angle in self.vertices:
            pos_angle = angle + self.rotation
            x = self.pos.x + r * math.cos(pos_angle)
            y = self.pos.y + r * math.sin(pos_angle)
            points.append((x, y))
        
        # Draw asteroid
        color = GRAY if hasattr(self, 'GRAY') else (150, 150, 150)
        pygame.draw.polygon(surface, color, points, 2)
    
    def get_hitbox(self):
        return (self.pos.x, self.pos.y, self.radius)


class Laser:
    """Laser beam from ship or UFO"""
    def __init__(self, x, y, angle, owner='ship'):
        self.pos = Vector(x, y)
        self.velocity = Vector(
            math.cos(angle) * LASER_SPEED,
            math.sin(angle) * LASER_SPEED
        )
        self.life = LASER_RANGE / LASER_SPEED  # Frames to live
        self.owner = owner  # 'ship' or 'enemy'
    
    def update(self):
        self.pos += self.velocity
        self.life -= 1
    
    def draw(self, surface):
        color = GREEN if self.owner == 'ship' else RED
        pygame.draw.circle(surface, color, (int(self.pos.x), int(self.pos.y)), 3)
    
    def is_dead(self):
        return (self.life <= 0 or
                self.pos.x < 0 or self.pos.x > WIDTH or
                self.pos.y < 0 or self.pos.y > HEIGHT)

    def get_hitbox(self):
        # laser is a small point; radius 3 matches its drawn size
        return (self.pos.x, self.pos.y, 3)


POWERUP_TYPES = ("shield", "rapid", "life")
POWERUP_COLORS = {"shield": BLUE, "rapid": YELLOW, "life": GREEN}


class PowerUp:
    """Collectible dropped by destroyed asteroids: shield, rapid-fire, or +1 life."""
    def __init__(self, x, y):
        self.pos = Vector(x, y)
        self.kind = random.choice(POWERUP_TYPES)
        self.radius = 12
        self.life = 480  # frames before it fades
        self.pulse = 0

    def update(self):
        self.life -= 1
        self.pulse += 0.15

    def is_dead(self):
        return self.life <= 0

    def draw(self, surface):
        c = POWERUP_COLORS[self.kind]
        r = self.radius + int(2 * math.sin(self.pulse))
        pygame.draw.circle(surface, c, (int(self.pos.x), int(self.pos.y)), r, 2)
        letter = {"shield": "S", "rapid": "R", "life": "+"}[self.kind]
        font = pygame.font.Font(None, 22)
        surface.blit(font.render(letter, True, c),
                     (int(self.pos.x) - 6, int(self.pos.y) - 8))

    def get_hitbox(self):
        return (self.pos.x, self.pos.y, self.radius)


class UFO:
    """Enemy UFO"""
    def __init__(self):
        # Spawn at random edge
        if random.random() < 0.5:
            self.pos = Vector(random.randint(0, WIDTH), -50)
        else:
            self.pos = Vector(-50, random.randint(0, HEIGHT))
        
        # Move toward center but with some randomness
        target_x = WIDTH / 2 + random.uniform(-100, 100)
        target_y = HEIGHT / 2 + random.uniform(-100, 100)
        angle = math.atan2(target_y - self.pos.y, target_x - self.pos.x)
        speed = 2
        self.velocity = Vector(
            math.cos(angle) * speed,
            math.sin(angle) * speed
        )
        
        self.radius = 20
        self.shoot_timer = 0
        self.health = 3
    
    def update(self, player_pos):
        # Move toward player slowly
        angle = math.atan2(player_pos.y - self.pos.y, player_pos.x - self.pos.x)
        speed = 1.5
        self.velocity.x = math.cos(angle) * speed
        self.velocity.y = math.sin(angle) * speed
        
        self.pos += self.velocity
        
        # Shooting logic
        self.shoot_timer += 1
        if self.shoot_timer > random.randint(60, 180):  # Shoot every 1-3 seconds
            self.shoot_timer = 0
            angle = math.atan2(player_pos.y - self.pos.y, player_pos.x - self.pos.x)
            return Laser(self.pos.x, self.pos.y, angle, 'enemy')
        
        return None
    
    def draw(self, surface):
        # Draw UFO as a flying saucer shape
        pygame.draw.ellipse(surface, ORANGE, 
                          (self.pos.x - self.radius, self.pos.y - self.radius // 2,
                           self.radius * 2, self.radius), 2)
        pygame.draw.ellipse(surface, PURPLE, 
                          (self.pos.x - self.radius // 2, self.pos.y - self.radius // 4,
                           self.radius, self.radius // 2))
        
        # Blinking lights
        current_time = pygame.time.get_ticks()
        if (current_time // 100) % 2 == 0:
            pygame.draw.circle(surface, RED, 
                             (int(self.pos.x - self.radius//2), int(self.pos.y)), 3)
            pygame.draw.circle(surface, RED,
                             (int(self.pos.x + self.radius//2), int(self.pos.y)), 3)
    
    def get_hitbox(self):
        return (self.pos.x, self.pos.y, self.radius)


def check_collision(obj1, obj2):
    """Check collision between two objects with get_hitbox() method"""
    x1, y1, r1 = obj1.get_hitbox()
    x2, y2, r2 = obj2.get_hitbox()
    
    dx = x1 - x2
    dy = y1 - y2
    distance = math.sqrt(dx*dx + dy*dy)
    
    return distance < (r1 + r2)


def create_asteroid_belt(num_asteroids):
    """Create initial asteroids"""
    asteroids = []
    for _ in range(num_asteroids):
        asteroid = Asteroid()
        # Ensure it doesn't spawn too close to player
        dist = math.sqrt((asteroid.pos.x - WIDTH//2)**2 + (asteroid.pos.y - HEIGHT//2)**2)
        while dist < 150:
            asteroid = Asteroid()
            dist = math.sqrt((asteroid.pos.x - WIDTH//2)**2 + (asteroid.pos.y - HEIGHT//2)**2)
        asteroids.append(asteroid)
    return asteroids


def draw_starfield(surface, stars):
    """Draw and animate starfield"""
    for star in stars:
        pygame.draw.circle(surface, WHITE, 
                          (int(star[0]), int(star[1])), 1)


def main(max_frames=1000):
    """Main game loop"""
    # Game state
    score = 0
    level = 1
    game_over = False
    restart = False
    
    # Create objects
    ship = Ship()
    asteroids = create_asteroid_belt(5 + level * 2)
    lasers = []
    ufos = []
    powerups = []
    rapid_until = 0          # ms; rapid-fire power-up expiry
    level_cooldown_until = 0  # ms; earliest time the next level-up may fire
    
    # Starfield
    stars = [(random.randint(0, WIDTH), random.randint(0, HEIGHT)) 
             for _ in range(100)]
    
    frames_run = 0
    
    # Game control variables
    keys_pressed = set()
    last_shot_time = 0
    
    # UFO spawn timer
    ufo_timer = 0
    
    while True:
        current_time = pygame.time.get_ticks()
        
        # Handle events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            
            if game_over and event.type == pygame.KEYDOWN:
                restart = True
        
        if restart or (game_over and pygame.key.get_pressed()[pygame.K_r]):
            return "RESTART"
        
        if not game_over:
            # Input handling
            keys_pressed.clear()
            for event in pygame.event.get(pygame.KEYDOWN):
                keys_pressed.add(event.key)
            
            # Check current key states
            keys = pygame.key.get_pressed()
            
            # Rotation
            if keys[pygame.K_LEFT] or keys[pygame.K_a]:
                ship.rotate(-1)
            if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
                ship.rotate(1)
            
            # Thrust
            if keys[pygame.K_UP] or keys[pygame.K_w]:
                ship.thrust()
            
            # Shooting (spacebar) — rapid-fire power-up shortens the cooldown
            if keys[pygame.K_SPACE]:
                shot_cooldown = 90 if current_time < rapid_until else 250  # ms
                if current_time - last_shot_time > shot_cooldown:
                    lasers.append(Laser(
                        ship.pos.x + math.cos(ship.angle) * ship.radius,
                        ship.pos.y + math.sin(ship.angle) * ship.radius,
                        ship.angle,
                        'ship'
                    ))
                    last_shot_time = current_time
            
            # Update objects
            ship.update()
            
            # Update asteroids
            for asteroid in asteroids:
                asteroid.update()
            
            # Update lasers
            for laser in lasers[:]:
                laser.update()
                if laser.is_dead():
                    lasers.remove(laser)
            
            # UFO spawning
            ufo_timer += 1
            spawn_interval = max(600, 1800 - level * 100)  # Decrease interval each level
            if ufo_timer > spawn_interval and len(ufos) < 2:
                ufos.append(UFO())
                ufo_timer = 0
            
            # Update UFOs
            for ufo in ufos[:]:
                laser = ufo.update(ship.pos)
                if laser:
                    lasers.append(laser)
                ufo_pos = ufo.get_hitbox()
                
                # Remove UFO if off screen
                if (ufo_pos[0] < -100 or ufo_pos[0] > WIDTH + 100 or
                    ufo_pos[1] < -100 or ufo_pos[1] > HEIGHT + 100):
                    ufos.remove(ufo)
            
            # Collision detection: Laser vs Asteroid
            for laser in lasers[:]:
                if laser.owner == 'ship':
                    for asteroid in asteroids[:]:
                        if check_collision(laser, asteroid):
                            lasers.remove(laser)
                            
                            # Split asteroid
                            asteroids.remove(asteroid)
                            score += 100 * (3 - asteroid.size_idx)

                            # 12% chance to drop a power-up where it broke
                            if random.random() < 0.12:
                                powerups.append(PowerUp(asteroid.pos.x, asteroid.pos.y))

                            if asteroid.size_idx > 0:
                                # Create two smaller asteroids
                                for _ in range(2):
                                    new_asteroid = Asteroid(
                                        asteroid.pos.x, 
                                        asteroid.pos.y,
                                        asteroid.size_idx - 1
                                    )
                                    # Add some random velocity variation
                                    new_asteroid.velocity.x += random.uniform(-0.5, 0.5)
                                    new_asteroid.velocity.y += random.uniform(-0.5, 0.5)
                                    asteroids.append(new_asteroid)
                            
                            # Level up only when the whole wave is truly cleared,
                            # AND at most once every 3s (timer guard stops the
                            # rapid re-trigger that let the counter run away).
                            if not asteroids and current_time > level_cooldown_until:
                                level += 1
                                level_cooldown_until = current_time + 3000
                                asteroids = create_asteroid_belt(5 + level * 2)
                            
                            break
            
            # Collision detection: Laser vs UFO
            for laser in lasers[:]:
                if laser.owner == 'ship':
                    for ufo in ufos[:]:
                        if check_collision(laser, ufo):
                            lasers.remove(laser)
                            ufo.health -= 1
                            if ufo.health <= 0:
                                score += 500
                                ufos.remove(ufo)
                            break
            
            # Collision detection: Ship vs Asteroid
            ship_hitbox = ship.get_hitbox()
            for asteroid in asteroids:
                if check_collision(ship, asteroid):
                    if current_time > ship.invincible_until:
                        ship.lives -= 1
                        ship.invincible_until = current_time + 2000  # 2 seconds invincibility
                        
                        # Reset position
                        ship.pos = Vector(WIDTH // 2, HEIGHT // 2)
                        ship.velocity = Vector(0, 0)

                        if ship.lives <= 0:
                            game_over = True

            # Collision: enemy UFO laser vs ship (UFOs are now actually dangerous)
            for laser in lasers[:]:
                if laser.owner == 'enemy' and check_collision(laser, ship):
                    if laser in lasers:
                        lasers.remove(laser)
                    if current_time > ship.invincible_until:
                        ship.lives -= 1
                        ship.invincible_until = current_time + 2000
                        ship.pos = Vector(WIDTH // 2, HEIGHT // 2)
                        ship.velocity = Vector(0, 0)
                        if ship.lives <= 0:
                            game_over = True

            # Power-ups: update, expire, and collect on contact with the ship
            for pu in powerups[:]:
                pu.update()
                if pu.is_dead():
                    powerups.remove(pu)
                    continue
                if check_collision(pu, ship):
                    powerups.remove(pu)
                    if pu.kind == "life":
                        ship.lives += 1
                    elif pu.kind == "shield":
                        ship.invincible_until = current_time + 6000  # 6s shield
                    elif pu.kind == "rapid":
                        rapid_until = current_time + 6000  # 6s rapid fire

        # Draw everything
        screen.fill(BLACK)
        
        # Draw stars
        draw_starfield(screen, stars)
        
        if not game_over:
            ship.draw(screen)
            
            for asteroid in asteroids:
                asteroid.draw(screen)
            
            for laser in lasers:
                laser.draw(screen)
            
            for ufo in ufos:
                ufo.draw(screen)

            for pu in powerups:
                pu.draw(screen)

            # Shield bubble when invincible from a shield power-up
            if current_time < ship.invincible_until:
                pygame.draw.circle(screen, BLUE,
                                   (int(ship.pos.x), int(ship.pos.y)),
                                   ship.radius + 10, 1)

            # Draw UI
            score_text = font.render(f"Score: {score}", True, WHITE)
            lives_text = font.render(f"Lives: {ship.lives}", True, WHITE)
            level_text = font.render(f"Level: {level}", True, YELLOW)

            screen.blit(score_text, (20, 20))
            screen.blit(lives_text, (20, 60))
            screen.blit(level_text, (WIDTH - 150, 20))
            if current_time < rapid_until:
                screen.blit(font.render("RAPID FIRE", True, YELLOW), (WIDTH - 180, 60))
        else:
            # Game over screen
            game_over_text = large_font.render("GAME OVER", True, RED)
            score_final_text = font.render(f"Final Score: {score}", True, WHITE)
            restart_text = font.render("Press any key to play again", True, WHITE)
            
            # Center text
            game_rect = game_over_text.get_rect(center=(WIDTH//2, HEIGHT//2 - 50))
            score_rect = score_final_text.get_rect(center=(WIDTH//2, HEIGHT//2 + 20))
            restart_rect = restart_text.get_rect(center=(WIDTH//2, HEIGHT//2 + 60))
            
            screen.blit(game_over_text, game_rect)
            screen.blit(score_final_text, score_rect)
            screen.blit(restart_text, restart_rect)
        
        pygame.display.flip()
        clock.tick(FPS)
        
        frames_run += 1
        
        # Auto-quit for testing
        if frames_run >= max_frames and max_frames > 0:
            print(f"SELFTEST PASSED: {frames_run} frames completed, score={score}")
            return "DONE"
    
    return "DONE"


if __name__ == "__main__":
    import sys
    
    # Check for self-test mode
    if len(sys.argv) > 1 and "--selftest" in sys.argv:
        max_frames = 200  # Test for 200 frames
        if "--frames" in sys.argv:
            idx = sys.argv.index("--frames")
            max_frames = int(sys.argv[idx + 1]) if idx + 1 < len(sys.argv) else 200
        
        result = main(max_frames=max_frames)
        sys.exit(0 if result == "DONE" else 1)
    
    while True:
        result = main()
        if result != "RESTART":
            break
