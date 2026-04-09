from importlib.resources import files
from math import radians
from os import environ
from pathlib import Path
from random import choice, randint

import nova
import pygame
import pygame._sdl2 as sdl2
import tinyecs as ecs

from pgcooldown import Cooldown, LerpThing, LTRepeat

if 'XDG_SESSION_TYPE' in environ and environ['XDG_SESSION_TYPE'] == 'wayland':
    environ['SDL_VIDEODRIVER'] = 'wayland'

TITLE = 'Nova & tinyecs'
SCREEN = pygame.Rect(0, 0, 1024, 768)
FPS = 60
DT_MAX = 3 / FPS

BOUNCY_AF = nova.Material(density=1.0, restitution=1.0, friction=0.0)
HITBOX_SIZE = 32
MAX_SCALE = 3

ASSETS = files('tinynova.assets')

pygame.font.init()
clock = pygame.time.Clock()
window = pygame.Window(title=TITLE, size=SCREEN.size)
renderer = sdl2.Renderer(window)


def slurp_textures(assets):
    cache = {}
    for fname in assets.glob('*.png'):
        animal = fname.stem
        base = pygame.image.load(fname)
        cache[animal] = sdl2.Texture.from_surface(renderer, base)

    return cache


CACHE = slurp_textures(ASSETS)


def nova_setup():
    space = nova.Space()
    space.broadphase = nova.BroadPhaseAlgorithm.BVH

    container = nova.RigidBody(position=nova.Vector2(SCREEN.center),
                               material=BOUNCY_AF)
    container.add_shape(nova.ShapeFactory.box(10, SCREEN.height, nova.Vector2(-SCREEN.centerx - 5, 0)))
    container.add_shape(nova.ShapeFactory.box(10, SCREEN.height, nova.Vector2(SCREEN.centerx + 3, 0)))
    container.add_shape(nova.ShapeFactory.box(SCREEN.width, 10, nova.Vector2(0, -SCREEN.centery - 5)))
    container.add_shape(nova.ShapeFactory.box(SCREEN.width, 10, nova.Vector2(0, SCREEN.centery + 3)))
    space.add_rigidbody(container)

    return space


space = nova_setup()


def mk_ball(pos, space):
    animal = choice(list(CACHE))
    scale = randint(1, MAX_SCALE)
    radius = (HITBOX_SIZE * scale) / 2
    direction = nova.Vector2(1, 0).rotate(radians(randint(0, 359)))
    speed = randint(100, 250)
    momentum = direction * speed
    angle = LerpThing(0, 360, 1, repeat=LTRepeat.LOOP)

    sprite = CACHE[animal]
    rect = sprite.get_rect().scale_by(scale)
    lifetime = Cooldown(randint(5, 10))
    alpha_ramp = LerpThing(255, 0, lifetime.duration)

    ball = nova.RigidBody(type=nova.RigidBodyType.DYNAMIC,
                          position=nova.Vector2(pos),
                          material=BOUNCY_AF)

    ball.add_shape(nova.ShapeFactory.circle(radius))
    ball.linear_velocity = momentum
    ball.gravity_scale = 0

    space.add_rigidbody(ball)

    ecs.create_entity(ball)
    ecs.add_component(ball, 'pos', nova.Vector2(pos))
    ecs.add_component(ball, 'rect', rect)
    ecs.add_component(ball, 'anchor', 'center')
    ecs.add_component(ball, 'radius', radius)
    ecs.add_component(ball, 'sprite', sprite)
    ecs.add_component(ball, 'angle', angle)
    ecs.add_component(ball, 'lifetime', lifetime)
    ecs.add_component(ball, 'alpha', alpha_ramp)


def mk_textlabel(renderer, font, pos, text):
    img = font.render(text, True, 'white')
    label = sdl2.Texture.from_surface(renderer, img)
    rect = label.get_rect(topleft=pos)
    anchor = 'topleft'

    eid = ecs.create_entity()
    ecs.add_component(eid, 'sprite', label)
    ecs.add_component(eid, 'rect', rect)
    ecs.add_component(eid, 'anchor', anchor)
    ecs.add_component(eid, 'pos', nova.Vector2(SCREEN.topleft))
    ecs.set_property(eid, 'is-static')


@space.visitor(nova.ShapeType.POLYGON)
def draw_poly(vertices, aux: nova.VisitorAuxiliary):
    points = [v.to_tuple() for v in vertices]
    for p0, p1 in zip(points[:-1], points[1:]):
        renderer.draw_line(p0, p1)
    renderer.draw_line(points[-1], points[0])


@space.visitor(nova.ShapeType.CIRCLE)
def draw_circle(center, radius, aux):
    ecs.update_component(aux.body, 'pos', center)


def sys_draw_circle(dt, eid, pos, radius, *, renderer):
    angles = [radians(_) for _ in list(range(0, 360, 10))]
    v = nova.Vector2(radius, 0)
    renderer.draw_color = 'cyan'
    for phi1, phi2 in zip(angles[:-1], angles[1:]):
        p1 = pos + v.rotate(phi1)
        p2 = pos + v.rotate(phi2)
        renderer.draw_line(p1, p2)

    p1 = pos + v.rotate(angles[-1])
    p2 = pos + v.rotate(angles[0])
    renderer.draw_line(p1, p2)


def sys_draw_sprite(dt, eid, sprite, rect, angle, alpha, *, renderer):
    bkp_alpha = sprite.alpha
    sprite.alpha = alpha()
    sprite.draw(dstrect=rect, angle=angle())
    sprite.alpha = bkp_alpha


def sys_draw_static_sprite(dt, eid, sprite, rect, *, renderer):
    sprite.draw(dstrect=rect)


def sys_lifetime(dt, eid, lifetime, *, space):
    if lifetime.cold():
        space.remove_rigidbody(eid)
        ecs.remove_entity(eid)


def sys_pos_to_rect(dt, eid, rect, pos, anchor):
    setattr(rect, anchor, pos.to_tuple())


def main():
    mk_ball(SCREEN.center, space)

    mk_textlabel(renderer,
                 pygame.font.SysFont(None, 24),
                 SCREEN.topleft,
                 'Press <space> to toggle hitbox circles\nPress mouse button to emit bouncers')

    debug = False
    running = True
    while running:
        dt = min(clock.tick(FPS) / 1000.0, DT_MAX)

        for e in pygame.event.get():
            if e.type == pygame.QUIT:
                running = False
            elif e.type == pygame.KEYDOWN:
                if e.key == pygame.K_ESCAPE:
                    running = False
                elif e.key == pygame.K_SPACE:
                    debug = not debug

        mp = pygame.mouse.get_pos()
        mb = pygame.mouse.get_pressed()
        if mb[0]:
            mk_ball(mp, space)

        space.step(dt)

        renderer.draw_color = 'darkslategray'
        renderer.clear()

        space.visit_geometry()

        ecs.run_system(dt, sys_pos_to_rect, 'rect', 'pos', 'anchor')
        ecs.run_system(dt, sys_draw_sprite, 'sprite', 'rect', 'angle', 'alpha', renderer=renderer)
        ecs.run_system(dt, sys_draw_static_sprite, 'sprite', 'rect', has_properties={'is-static'}, renderer=renderer)
        ecs.run_system(dt, sys_lifetime, 'lifetime', space=space)
        if debug:
            ecs.run_system(dt, sys_draw_circle, 'pos', 'radius', renderer=renderer)

        renderer.present()
        window.title = f'{TITLE} - entities={len(ecs.eidx)}  fps={clock.get_fps():.2f}'


if __name__ == "__main__":
    main()
