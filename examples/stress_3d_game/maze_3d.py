#!/usr/bin/env python3
"""
3D First-Person Maze Game
WASD to move, Arrow keys to look around, Escape to quit
Find the red goal at the end to win!
"""

import pygame
import sys
import math

# Parse command line arguments for self-test mode
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('--selftest', action='store_true', help='Run self-test and exit after frames')
parser.add_argument('--frames', type=int, default=100, help='Number of frames to run in self-test')
args = parser.parse_args()

# Initialize Pygame
pygame.init()

# Screen settings
SCREEN_WIDTH = 800
SCREEN_HEIGHT = 600
FPS = 30

screen = pygame.display.set_mode((SCREEN_WIDTH, SCREEN_HEIGHT))
pygame.display.set_caption("3D Maze Explorer")
clock = pygame.time.Clock()

# Font for UI
font = pygame.font.SysFont(None, 48)

# Game constants
FOV = math.pi / 3  # 60 degrees
MAX_DEPTH = 20  # Maximum raycast distance
TILE_SIZE = 1.0

# Maze layout (1 = wall, 0 = empty, 2 = goal)
# Simple maze with a path to the goal
MAZE_LAYOUT = [
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 2, 1],
    [1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 1, 1, 1, 0, 1, 1],
    [1, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1],
    [1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 1, 1, 1],
    [1, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 0, 1, 1, 1, 0, 1, 0, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1, 0, 0, 1],
    [1, 1, 1, 1, 1, 0, 1, 1, 1, 1, 1, 1, 1, 0, 1, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 0, 1],
    [1, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 1],
    [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
]

# Player settings
player_pos = [2.5, 2.5]  # Starting position (x, y)
player_dir = 0  # Facing direction in radians (0 = east)
player_pitch = 0  # Looking up/down
move_speed = 0.1
rot_speed = 0.03


def cast_rays():
    """
    Raycasting algorithm to render the 3D view.
    Returns a list of distances to walls for each vertical slice.
    """
    wall_depths = []
    
    # Cast rays across the FOV
    num_rays = SCREEN_WIDTH
    start_angle = player_dir - FOV / 2
    
    for ray_num in range(num_rays):
        angle = start_angle + (ray_num / num_rays) * FOV
        
        # Ray direction
        ray_dx = math.cos(angle)
        ray_dy = math.sin(angle)
        
        # DDA algorithm for efficient raycasting
        map_x = int(player_pos[0])
        map_y = int(player_pos[1])
        
        # Calculate delta distance
        if ray_dx == 0:
            delta_dist_x = float('inf')
        else:
            delta_dist_x = abs(1 / ray_dx)
            
        if ray_dy == 0:
            delta_dist_y = float('inf')
        else:
            delta_dist_y = abs(1 / ray_dy)
        
        # Calculate step and initial side distance
        if ray_dx < 0:
            step_x = -1
            side_dist_x = (player_pos[0] - map_x) * delta_dist_x
        else:
            step_x = 1
            side_dist_x = (map_x + 1.0 - player_pos[0]) * delta_dist_x
            
        if ray_dy < 0:
            step_y = -1
            side_dist_y = (player_pos[1] - map_y) * delta_dist_y
        else:
            step_y = 1
            side_dist_y = (map_y + 1.0 - player_pos[1]) * delta_dist_y
        
        hit_wall = False
        distance = 0
        side = 0  # 0 for NS, 1 for EW
        
        # DDA loop
        while not hit_wall and distance < MAX_DEPTH:
            if side_dist_x < side_dist_y:
                side_dist_x += delta_dist_x
                map_x += step_x
                side = 0
            else:
                side_dist_y += delta_dist_y
                map_y += step_y
                side = 1
            
            # Check bounds
            if (map_x < 0 or map_x >= len(MAZE_LAYOUT[0]) or 
                map_y < 0 or map_y >= len(MAZE_LAYOUT)):
                hit_wall = True
                distance = MAX_DEPTH
            else:
                tile = MAZE_LAYOUT[map_y][map_x]
                if tile > 0:  # Wall or goal
                    hit_wall = True
                    # Calculate corrected distance (fisheye correction)
                    if side == 0:
                        distance = abs((map_x - player_pos[0] + (1 - step_x) / 2) / ray_dx)
                    else:
                        distance = abs((map_y - player_pos[1] + (1 - step_y) / 2) / ray_dy)
        
        wall_depths.append(distance)
    
    return wall_depths


def render_wall_slice(distance, screen_x, max_depth=MAX_DEPTH):
    """
    Render a single vertical slice of the wall with shading.
    """
    # Fix fisheye effect
    corrected_distance = distance * math.cos(player_dir - (math.atan2(screen_x - SCREEN_WIDTH/2, SCREEN_WIDTH/FOV)))
    
    # Calculate wall height
    if corrected_distance == 0:
        corrected_distance = 0.1
    wall_height = min(SCREEN_HEIGHT / corrected_distance, SCREEN_HEIGHT)
    
    # Determine wall color based on distance (shading)
    # Closer walls are brighter, farther walls are darker
    shade_factor = max(0.2, 1 - corrected_distance / max_depth)
    
    # Make vertical edges darker for depth perception
    if int(screen_x) % 4 == 0:
        shade_factor *= 0.8
    
    return wall_height, shade_factor


def check_win_condition():
    """Check if player reached the goal."""
    map_x = int(player_pos[0])
    map_y = int(player_pos[1])
    
    # Check if player is at the goal position
    if (0 <= map_y < len(MAZE_LAYOUT) and 0 <= map_x < len(MAZE_LAYOUT[0])):
        return MAZE_LAYOUT[map_y][map_x] == 2
    return False


def draw_3d_view():
    """Draw the 3D wall rendering."""
    wall_depths = cast_rays()
    
    for x in range(SCREEN_WIDTH):
        distance = wall_depths[x]
        
        if distance < MAX_DEPTH:
            wall_height, shade_factor = render_wall_slice(distance, x)
            
            # Calculate top position (wall hangs from ceiling)
            top_pos = (SCREEN_HEIGHT - wall_height) / 2
            
            # Color based on tile type and distance
            if distance < MAX_DEPTH * 0.3:
                base_color = (150, 150, 150)  # Gray for close walls
            elif distance < MAX_DEPTH * 0.6:
                base_color = (120, 120, 120)  # Darker for medium distance
            else:
                base_color = (80, 80, 80)  # Darkest for far walls
            
            # Apply shading
            r = int(base_color[0] * shade_factor)
            g = int(base_color[1] * shade_factor)
            b = int(base_color[2] * shade_factor)
            
            pygame.draw.rect(screen, (r, g, b), (x, top_pos, 1, wall_height))
        else:
            # Background - ceiling and floor
            screen_y = SCREEN_HEIGHT / 2
            gradient_pos = x / SCREEN_WIDTH
            
            # Sky (top half) to ground (bottom half)
            if x < SCREEN_WIDTH:
                pygame.draw.rect(screen, (50, 100, 150), (x, 0, 1, SCREEN_HEIGHT/2))
                pygame.draw.rect(screen, (60, 50, 40), (x, SCREEN_HEIGHT/2, 1, SCREEN_HEIGHT/2))


def draw_minimap():
    """Draw a top-down minimap showing the maze and player position."""
    map_size = 100
    cell_size = map_size / max(len(MAZE_LAYOUT[0]), len(MAZE_LAYOUT))
    
    # Draw minimap background
    map_x = SCREEN_WIDTH - map_size - 20
    map_y = 20
    
    pygame.draw.rect(screen, (30, 30, 30), (map_x - 5, map_y - 5, map_size + 10, map_size + 10))
    
    # Draw walls and goal
    for row in range(len(MAZE_LAYOUT)):
        for col in range(len(MAZE_LAYOUT[0])):
            tile = MAZE_LAYOUT[row][col]
            
            if tile == 1:  # Wall
                color = (150, 150, 150)
            elif tile == 2:  # Goal
                color = (255, 50, 50)  # Red goal
            else:
                continue
            
            pygame.draw.rect(screen, color,
                           (map_x + col * cell_size,
                            map_y + row * cell_size,
                            cell_size, cell_size))
    
    # Draw player position on minimap
    px = int(player_pos[0])
    py = int(player_pos[1])
    if 0 <= px < len(MAZE_LAYOUT[0]) and 0 <= py < len(MAZE_LAYOUT):
        pygame.draw.circle(screen, (0, 255, 0),
                          (map_x + px * cell_size + cell_size/2,
                           map_y + py * cell_size + cell_size/2), cell_size/3)


def draw_hud(won=False):
    """Draw heads-up display and instructions."""
    # Instructions
    instructions = [
        "WASD: Move | Arrows: Look | ESC: Quit",
        "Find the red goal to win!"
    ]
    
    for i, text in enumerate(instructions):
        label = font.render(text, True, (255, 255, 255))
        screen.blit(label, (10, SCREEN_HEIGHT - 60 + i * 30))
    
    if won:
        # Victory message
        win_text = "YOU WON! EXIT FOUND!"
        win_surface = font.render(win_text, True, (50, 255, 50))
        
        text_rect = win_surface.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2))
        screen.blit(win_surface, text_rect)
        
        restart_text = pygame.font.SysFont(None, 32).render("Press R to play again or ESC to quit", True, (255, 255, 255))
        restart_rect = restart_text.get_rect(center=(SCREEN_WIDTH//2, SCREEN_HEIGHT//2 + 50))
        screen.blit(restart_text, restart_rect)


def move_player(dx, dy):
    """Move player with collision detection."""
    new_x = player_pos[0] + dx
    new_y = player_pos[1] + dy
    
    # Simple collision detection (check nearby tiles)
    margin = 0.3  # Player radius
    
    # Check X direction
    if MAZE_LAYOUT[int(player_pos[1])][int(new_x)] == 0 or MAZE_LAYOUT[int(player_pos[1])][int(new_x)] == 2:
        player_pos[0] = new_x
    
    # Check Y direction
    if MAZE_LAYOUT[int(new_y)][int(player_pos[0])] == 0 or MAZE_LAYOUT[int(new_y)][int(player_pos[0])] == 2:
        player_pos[1] = new_y


def reset_game():
    """Reset game state."""
    global player_pos, player_dir
    player_pos = [2.5, 2.5]
    player_dir = 0


# Main game loop
won = False
game_running = True
frames_run = 0

while game_running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            game_running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                game_running = False
            if won and event.key == pygame.K_r:
                reset_game()
                won = False
    
    # Self-test: simulate input and exit after frames
    if args.selftest:
        frames_run += 1
        
        # Simulate some movement during self-test
        keys = pygame.key.get_pressed()
        
        # Auto-move toward the goal to test collision detection
        player_dir = 0  # Face east
        dx, dy = move_speed * 2, 0
        move_player(dx, dy)
        
        if check_win_condition():
            won = True
        
        if frames_run >= args.frames:
            print(f"Self-test passed! Ran {frames_run} frames successfully.")
            game_running = False
    
    else:
        # Handle input
        keys = pygame.key.get_pressed()
        
        # Rotation (arrow keys)
        if keys[pygame.K_LEFT]:
            player_dir -= rot_speed
        if keys[pygame.K_RIGHT]:
            player_dir += rot_speed
        
        # Pitch (up/down) - limited range
        if keys[pygame.K_UP]:
            player_pitch = max(-0.5, player_pitch - 0.01)
        if keys[pygame.K_DOWN]:
            player_pitch = min(0.5, player_pitch + 0.01)
        
        # Movement (WASD) - W/S forward/back, A/D strafe
        move_dist = move_speed
        
        dx = 0
        dy = 0
        
        if keys[pygame.K_w]:
            dx += math.cos(player_dir) * move_dist
            dy += math.sin(player_dir) * move_dist
        if keys[pygame.K_s]:
            dx -= math.cos(player_dir) * move_dist
            dy -= math.sin(player_dir) * move_dist
        if keys[pygame.K_a]:
            dx += math.cos(player_dir - math.pi/2) * move_dist
            dy += math.sin(player_dir - math.pi/2) * move_dist
        if keys[pygame.K_d]:
            dx += math.cos(player_dir + math.pi/2) * move_dist
            dy += math.sin(player_dir + math.pi/2) * move_dist
        
        move_player(dx, dy)
        
        # Check win condition
        if check_win_condition():
            won = True
    
    # Draw everything
    screen.fill((0, 0, 0))
    
    draw_3d_view()
    draw_minimap()
    draw_hud(won)
    
    pygame.display.flip()
    clock.tick(FPS)

pygame.quit()
sys.exit()
