# 3D vector and matrix math (for 3D games/graphics from scratch)

The math behind first-person cameras, rotating objects, and perspective. Use `numpy` for
speed (`python -m pip install numpy`) or write small helpers.

## Vectors
```python
import math
def sub(a, b): return (a[0]-b[0], a[1]-b[1], a[2]-b[2])
def dot(a, b): return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]
def cross(a, b): return (a[1]*b[2]-a[2]*b[1], a[2]*b[0]-a[0]*b[2], a[0]*b[1]-a[1]*b[0])
def length(a): return math.sqrt(dot(a, a))
def normalize(a):
    l = length(a) or 1.0
    return (a[0]/l, a[1]/l, a[2]/l)
```
- `dot` → angle/projection (0 = perpendicular). `cross` → a vector perpendicular to both
  (surface normals, "right" vector from forward+up).

## First-person camera direction from yaw/pitch
```python
def forward(yaw, pitch):        # radians
    return normalize((math.cos(pitch)*math.sin(yaw),
                      math.sin(pitch),
                      math.cos(pitch)*math.cos(yaw)))
```
Mouse X → yaw, mouse Y → pitch (clamp pitch to ~±1.4 rad so you can't flip over).

## Perspective projection (3D point → 2D screen)
```python
def project(p, cam, yaw, pitch, W, H, fov=math.radians(70)):
    # translate into camera space, then divide by depth
    rel = sub(p, cam)
    # (rotate rel by -yaw/-pitch here for a real camera; simplified below)
    x, y, z = rel
    if z <= 0.01: return None                 # behind the camera — cull
    f = (W/2) / math.tan(fov/2)
    return (int(W/2 + f * x / z), int(H/2 - f * y / z))
```
Nearer objects project larger (that's the depth cue). Cull points with `z <= 0`.

## Rotating a point around an axis
For simple cases rotate about Y (yaw): `x' = x*cos - z*sin; z' = x*sin + z*cos`. For
arbitrary axes use rotation matrices or quaternions. If you need full 3D + physics, prefer
an engine — see [[Panda3D first-person walking sim]] / [[Ursina 3D engine (easy 3D)]].
