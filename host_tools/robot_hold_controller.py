#!/usr/bin/env python3
"""MANUAL/CRUISE keyboard controller for the Arduino tracked robot."""

from __future__ import annotations

import argparse
import sys
import time

try:
    import pygame
except ImportError as exc:
    raise SystemExit(
        "pygame is not installed. Run: python3 -m pip install -r requirements.txt"
    ) from exc

from serial import SerialException

from robot_controller import (
    connect_to_robot,
    emergency_stop,
    read_lines,
    send_command,
)


WINDOW_SIZE = (760, 560)
BACKGROUND = (24, 29, 38)
TEXT = (230, 235, 242)
MUTED = (160, 172, 190)
SAFE = (49, 168, 103)
MOVING = (222, 157, 55)
STOPPED = (210, 72, 72)
MANUAL = "MANUAL"
CRUISE = "CRUISE"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Hold-to-drive keyboard controller for the tracked robot."
    )
    parser.add_argument(
        "--port",
        help="Serial port, for example /dev/ttyUSB0. Auto-detected by default.",
    )
    parser.add_argument(
        "--pwm",
        type=int,
        default=150,
        help="Outer-track PWM from 0 to 255 (default: 150).",
    )
    parser.add_argument(
        "--turn-ratio",
        type=float,
        default=0.5,
        help="Inner-track PWM ratio for arc turns, 0.0..1.0 (default: 0.5).",
    )
    parser.add_argument(
        "--accel",
        type=float,
        default=300.0,
        help="Acceleration ramp in PWM units per second (default: 300).",
    )
    parser.add_argument(
        "--decel",
        type=float,
        default=450.0,
        help="Deceleration ramp in PWM units per second (default: 450).",
    )
    parser.add_argument(
        "--watchdog",
        type=int,
        default=500,
        help="Arduino watchdog timeout in ms, 100..10000 (default: 500).",
    )
    parser.add_argument(
        "--heartbeat",
        type=float,
        default=0.2,
        help="Motion command repeat interval in seconds (default: 0.2).",
    )
    args = parser.parse_args()

    if not 0 <= args.pwm <= 255:
        parser.error("--pwm must be in range 0..255")
    if not 0.0 <= args.turn_ratio <= 1.0:
        parser.error("--turn-ratio must be in range 0.0..1.0")
    if args.accel <= 0:
        parser.error("--accel must be greater than zero")
    if args.decel <= 0:
        parser.error("--decel must be greater than zero")
    if not 100 <= args.watchdog <= 10000:
        parser.error("--watchdog must be in range 100..10000")
    if not 0.05 <= args.heartbeat < args.watchdog / 1000:
        parser.error("--heartbeat must be at least 0.05 s and shorter than watchdog")

    return args


def pressed(keys, *key_codes: int) -> bool:
    return any(keys[key_code] for key_code in key_codes)


def motion_from_keys(keys, pwm: int, turn_ratio: float) -> tuple[int, int]:
    forward = pressed(keys, pygame.K_w, pygame.K_UP)
    backward = pressed(keys, pygame.K_s, pygame.K_DOWN)
    steer_left = pressed(keys, pygame.K_a, pygame.K_LEFT)
    steer_right = pressed(keys, pygame.K_d, pygame.K_RIGHT)
    spin_left = pressed(keys, pygame.K_q)
    spin_right = pressed(keys, pygame.K_e)
    emergency = pressed(keys, pygame.K_SPACE)

    if emergency:
        return 0, 0
    if spin_left and spin_right:
        return 0, 0
    if spin_left:
        return -pwm, pwm
    if spin_right:
        return pwm, -pwm

    if forward and backward:
        return 0, 0
    if steer_left and steer_right:
        return 0, 0

    inner_pwm = round(pwm * turn_ratio)

    if forward:
        if steer_left:
            return inner_pwm, pwm
        if steer_right:
            return pwm, inner_pwm
        return pwm, pwm

    if backward:
        if steer_left:
            return -pwm, -inner_pwm
        if steer_right:
            return -inner_pwm, -pwm
        return -pwm, -pwm

    # A/D alone perform a forward arc; Q/E are reserved for spin-in-place.
    if steer_left:
        return inner_pwm, pwm
    if steer_right:
        return pwm, inner_pwm

    return 0, 0


def cruise_action_from_key(key: int, current_action: str | None) -> str | None:
    if key in (pygame.K_w, pygame.K_UP):
        return "FORWARD"
    if key in (pygame.K_s, pygame.K_DOWN):
        return "BACKWARD"

    moving_backward = current_action in {
        "BACKWARD",
        "BACKWARD_LEFT",
        "BACKWARD_RIGHT",
    }
    if key in (pygame.K_a, pygame.K_LEFT):
        return "BACKWARD_LEFT" if moving_backward else "FORWARD_LEFT"
    if key in (pygame.K_d, pygame.K_RIGHT):
        return "BACKWARD_RIGHT" if moving_backward else "FORWARD_RIGHT"
    if key == pygame.K_q:
        return "SPIN_LEFT"
    if key == pygame.K_e:
        return "SPIN_RIGHT"
    return current_action


def motion_from_cruise_action(
    action: str | None,
    pwm: int,
    turn_ratio: float,
) -> tuple[int, int]:
    inner_pwm = round(pwm * turn_ratio)
    motions = {
        "FORWARD": (pwm, pwm),
        "BACKWARD": (-pwm, -pwm),
        "FORWARD_LEFT": (inner_pwm, pwm),
        "FORWARD_RIGHT": (pwm, inner_pwm),
        "BACKWARD_LEFT": (-pwm, -inner_pwm),
        "BACKWARD_RIGHT": (-inner_pwm, -pwm),
        "SPIN_LEFT": (-pwm, pwm),
        "SPIN_RIGHT": (pwm, -pwm),
    }
    return motions.get(action, (0, 0))


def ramp_value(current: float, target: int, elapsed: float, accel: float, decel: float) -> float:
    if current == target:
        return current

    # Moving towards zero is braking; crossing zero is split into braking and acceleration.
    same_direction = current == 0 or target == 0 or (current > 0) == (target > 0)
    speeding_up = same_direction and abs(target) > abs(current)
    rate = accel if speeding_up else decel
    step = rate * elapsed

    if target > current:
        return min(current + step, float(target))
    return max(current - step, float(target))


def pwm_command(left: int, right: int) -> str:
    return "S" if left == 0 and right == 0 else f"M {left} {right}"


def draw_window(
    screen,
    title_font,
    font,
    small_font,
    control_mode: str,
    cruise_action: str | None,
    active_command: str,
    pwm: int,
    turn_ratio: float,
    watchdog_ms: int,
    port_name: str,
    last_message: str,
) -> None:
    screen.fill(BACKGROUND)
    moving = active_command != "S"
    status_color = MOVING if moving else STOPPED
    status_text = active_command if moving else "STOP"

    lines = [
        (title_font, "Tracked Robot Controller", TEXT),
        (
            font,
            f"MODE: {control_mode}    [Tab to switch]",
            SAFE if control_mode == MANUAL else MOVING,
        ),
        (title_font, status_text, status_color),
        (font, "W / Up       forward", TEXT),
        (font, "S / Down     backward", TEXT),
        (font, "A / Left     arc left", TEXT),
        (font, "D / Right    arc right", TEXT),
        (font, "Q / E        spin left / spin right", TEXT),
        (
            small_font,
            "MANUAL: hold keys   |   CRUISE: press once; direction stays active",
            MUTED,
        ),
        (font, "Space        emergency stop", TEXT),
        (font, "+ / -        change PWM", TEXT),
        (font, "Esc          stop and exit", TEXT),
        (
            small_font,
            f"PWM={pwm}  inner={round(pwm * turn_ratio)}  "
            f"watchdog={watchdog_ms} ms  port={port_name}",
            SAFE,
        ),
        (small_font, f"Arduino: {last_message}", MUTED),
        (
            small_font,
            f"Cruise command: {cruise_action or 'STOPPED'}",
            MUTED,
        ),
    ]

    y = 24
    for current_font, text, color in lines:
        surface = current_font.render(text, True, color)
        screen.blit(surface, (28, y))
        y += surface.get_height() + 12

    pygame.display.flip()


def run_controller(
    connection,
    port_name: str,
    pwm: int,
    turn_ratio: float,
    watchdog_ms: int,
    heartbeat: float,
    accel: float,
    decel: float,
) -> None:
    send_command(connection, "S")
    send_command(connection, f"T {watchdog_ms}")
    time.sleep(0.1)

    pygame.init()
    screen = pygame.display.set_mode(WINDOW_SIZE)
    pygame.display.set_caption("Tracked Robot Controller")
    title_font = pygame.font.Font(None, 38)
    font = pygame.font.Font(None, 30)
    small_font = pygame.font.Font(None, 22)
    clock = pygame.time.Clock()

    active_command = "S"
    sent_command = "S"
    current_left = 0.0
    current_right = 0.0
    next_heartbeat = time.monotonic()
    previous_tick = time.monotonic()
    last_message = "connected; motors stopped"
    control_mode = MANUAL
    cruise_action: str | None = None
    running = True

    try:
        while running:
            emergency_stop_requested = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                    emergency_stop_requested = True
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        running = False
                        emergency_stop_requested = True
                    elif event.key == pygame.K_TAB:
                        control_mode = CRUISE if control_mode == MANUAL else MANUAL
                        cruise_action = None
                        emergency_stop_requested = True
                        last_message = f"mode changed to {control_mode}; STOP sent"
                    elif event.key == pygame.K_SPACE:
                        cruise_action = None
                        emergency_stop_requested = True
                    elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS):
                        pwm = min(255, pwm + 10)
                    elif event.key in (pygame.K_MINUS, pygame.K_UNDERSCORE, pygame.K_KP_MINUS):
                        pwm = max(0, pwm - 10)
                    elif event.key == pygame.K_i:
                        send_command(connection, "STATUS")
                    elif event.key == pygame.K_c:
                        send_command(connection, "E")
                    elif event.key == pygame.K_r:
                        send_command(connection, "RESET_E")
                    elif control_mode == CRUISE:
                        cruise_action = cruise_action_from_key(event.key, cruise_action)
                elif event.type == getattr(pygame, "WINDOWFOCUSLOST", -1):
                    cruise_action = None
                    emergency_stop_requested = True

            keys = pygame.key.get_pressed()
            if not pygame.key.get_focused() or pressed(keys, pygame.K_SPACE):
                cruise_action = None
                emergency_stop_requested = True

            if control_mode == MANUAL:
                target_left, target_right = motion_from_keys(keys, pwm, turn_ratio)
            else:
                target_left, target_right = motion_from_cruise_action(
                    cruise_action,
                    pwm,
                    turn_ratio,
                )

            now = time.monotonic()
            elapsed = min(now - previous_tick, 0.1)
            previous_tick = now

            if emergency_stop_requested:
                current_left = 0.0
                current_right = 0.0
                target_left = 0
                target_right = 0
            else:
                current_left = ramp_value(current_left, target_left, elapsed, accel, decel)
                current_right = ramp_value(current_right, target_right, elapsed, accel, decel)

            left_pwm = round(current_left)
            right_pwm = round(current_right)
            active_command = pwm_command(left_pwm, right_pwm)

            if active_command != sent_command or now >= next_heartbeat:
                send_command(connection, active_command)
                sent_command = active_command
                next_heartbeat = now + heartbeat
                last_message = "STOP sent" if active_command == "S" else active_command

            for line in read_lines(connection):
                if not line.startswith("OK M LEFT="):
                    last_message = line

            draw_window(
                screen,
                title_font,
                font,
                small_font,
                control_mode,
                cruise_action,
                active_command,
                pwm,
                turn_ratio,
                watchdog_ms,
                port_name,
                last_message,
            )
            clock.tick(60)
    finally:
        send_command(connection, "S")
        pygame.quit()


def main() -> int:
    args = parse_args()
    connection = None

    try:
        connection, port = connect_to_robot(args.port)
        print(f"Robot found on {port.device}: {port.description}")
        run_controller(
            connection,
            port_name=port.device,
            pwm=args.pwm,
            turn_ratio=args.turn_ratio,
            watchdog_ms=args.watchdog,
            heartbeat=args.heartbeat,
            accel=args.accel,
            decel=args.decel,
        )
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted; stopping robot.")
        return 130
    except (RuntimeError, SerialException, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    finally:
        emergency_stop(connection)
        if connection is not None and connection.is_open:
            connection.close()


if __name__ == "__main__":
    raise SystemExit(main())
