# Ursina 3D engine — the easy way to real 3D in Python

Ursina (built on Panda3D) is far easier than raw Panda3D for a first-person game. It ships
a `FirstPersonController` with mouse-look, WASD, gravity, and collision built in. Needs
`python -m pip install ursina`. Use this when you want real 3D fast; use
[[Panda3D first-person walking sim]] only when you need low-level Bullet control.

## First-person walking sim in ~20 lines
```python
from ursina import *
from ursina.prefabs.first_person_controller import FirstPersonController
app = Ursina()
ground = Entity(model='plane', scale=64, texture='white_cube', texture_scale=(64,64),
                collider='box')                       # walkable, collidable ground
for i in range(20):                                   # some walls/props to explore
    Entity(model='cube', position=(random.uniform(-20,20),1,random.uniform(-20,20)),
           color=color.gray, collider='box')
player = FirstPersonController()                       # mouse-look + WASD + gravity + collision
# NPCs that wander
npcs = [Entity(model='cube', color=color.azure, position=(random.uniform(-15,15),1,random.uniform(-15,15)))
        for _ in range(5)]
def update():
    for n in npcs:
        n.x += (n.x_dir if hasattr(n,'x_dir') else setattr(n,'x_dir',random.choice([-1,1])) or n.x_dir) * time.dt
        if abs(n.x) > 20: n.x_dir *= -1
app.run()
```
`FirstPersonController` gives you: WASD movement, mouse look, gravity (you fall and land),
and `collider='box'` on walls/ground stops you walking through them — i.e. all the
"physics" a walking sim needs, for free.

## Headless self-test
Ursina needs a display; for CI-style checks, test your **NPC/game logic separately**
(pure functions) rather than launching the window, OR run with
`Ursina(window_type='none')` if available and step a few frames. Keep game logic (NPC
wander, collision math) in importable functions so you can unit-test them without a window.
