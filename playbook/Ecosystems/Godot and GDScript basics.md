# Godot and GDScript basics

Godot is a full game engine with its own scripting language, GDScript (Python-like). Good
for 2D/3D games with a real editor. A Godot project is a folder of scenes (`.tscn`) + scripts
(`.gd`) + a `project.godot` file. You normally build scenes in the editor, but scripts are
plain text you can write.

## project.godot (minimal)
```ini
config_version=5
[application]
config/name="My Game"
run/main_scene="res://main.tscn"
```

## A GDScript player controller (attached to a CharacterBody2D)
```gdscript
extends CharacterBody2D

const SPEED := 200.0
const GRAVITY := 900.0

func _physics_process(delta: float) -> void:
    velocity.y += GRAVITY * delta                 # gravity
    var dir := Input.get_axis("ui_left", "ui_right")
    velocity.x = dir * SPEED
    if Input.is_action_just_pressed("ui_accept") and is_on_floor():
        velocity.y = -400.0                        # jump
    move_and_slide()                               # built-in collision + slide
```

## Key GDScript facts (differences from Python)
- `func name(arg: Type) -> Ret:` — typed, but `:=` infers types.
- `_ready()` runs when the node enters the tree; `_process(delta)` every frame;
  `_physics_process(delta)` every physics tick (use for movement/physics).
- Nodes form a tree; `$Child` or `get_node("Child")` accesses children.
- `CharacterBody2D.move_and_slide()` handles collision/slide; `is_on_floor()` for ground checks.

## Building / running headless
`godot --headless --quit` opens and closes the project (smoke test that it loads).
`godot --headless -s script.gd` runs a script. Requires the `godot` binary installed —
if it isn't, you can write and structure the project but can't run it; say so honestly.
For pure-Python 3D instead, see [[Ursina 3D engine (easy 3D)]] / [[Panda3D first-person walking sim]].
