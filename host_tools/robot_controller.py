#!/usr/bin/env python3
"""Keyboard controller for the Arduino tracked robot."""

from __future__ import annotations

import argparse
import os
import select
import sys
import time
from dataclasses import dataclass
from typing import Iterable

try:
    import serial
    from serial import SerialException
    from serial.tools import list_ports
except ImportError as exc:
    raise SystemExit(
        "pyserial is not installed. Run: python -m pip install -r requirements.txt"
    ) from exc


BAUD_RATE = 115200
CH340_USB_IDS = {
    (0x1A86, 0x7523),
    (0x1A86, 0x5523),
}


@dataclass(frozen=True)
class PortCandidate:
    device: str
    description: str
    vid: int | None
    pid: int | None

    @property
    def is_ch340(self) -> bool:
        return (self.vid, self.pid) in CH340_USB_IDS


class ConsoleKeyboard:
    """Read one key at a time on Windows or a POSIX terminal."""

    def __init__(self) -> None:
        self._fd: int | None = None
        self._old_settings = None

    def __enter__(self) -> "ConsoleKeyboard":
        if os.name != "nt":
            if not sys.stdin.isatty():
                raise RuntimeError("Keyboard control requires an interactive terminal.")

            import termios
            import tty

            self._fd = sys.stdin.fileno()
            self._old_settings = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if os.name != "nt" and self._fd is not None:
            import termios

            termios.tcsetattr(
                self._fd,
                termios.TCSADRAIN,
                self._old_settings,
            )

    def read_key(self) -> str | None:
        if os.name == "nt":
            import msvcrt

            if not msvcrt.kbhit():
                return None
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                msvcrt.getwch()
                return None
            return key

        ready, _, _ = select.select([sys.stdin], [], [], 0)
        if not ready:
            return None
        return sys.stdin.read(1)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Keyboard controller for the Arduino tracked robot."
    )
    parser.add_argument(
        "--port",
        help="Serial port, for example COM5 or /dev/ttyUSB0. Auto-detected by default.",
    )
    parser.add_argument(
        "--pwm",
        type=int,
        default=150,
        help="Initial PWM from 0 to 255 (default: 150).",
    )
    parser.add_argument(
        "--watchdog",
        type=int,
        default=500,
        help="Arduino watchdog timeout in ms from 100 to 10000 (default: 500).",
    )
    parser.add_argument(
        "--heartbeat",
        type=float,
        default=0.2,
        help="Motion command repeat interval in seconds (default: 0.2).",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List serial ports and exit.",
    )
    args = parser.parse_args()

    if not 0 <= args.pwm <= 255:
        parser.error("--pwm must be in range 0..255")
    if not 100 <= args.watchdog <= 10000:
        parser.error("--watchdog must be in range 100..10000")
    if not 0.05 <= args.heartbeat < args.watchdog / 1000:
        parser.error("--heartbeat must be at least 0.05 s and shorter than watchdog")

    return args


def available_ports() -> list[PortCandidate]:
    ports = [
        PortCandidate(
            device=port.device,
            description=port.description or "unknown device",
            vid=port.vid,
            pid=port.pid,
        )
        for port in list_ports.comports()
    ]
    return sorted(ports, key=lambda port: (not port.is_ch340, port.device))


def print_ports(ports: Iterable[PortCandidate]) -> None:
    found = False
    for port in ports:
        found = True
        usb_id = (
            f"{port.vid:04X}:{port.pid:04X}"
            if port.vid is not None and port.pid is not None
            else "no USB ID"
        )
        marker = " CH340" if port.is_ch340 else ""
        print(f"{port.device}: {port.description} [{usb_id}]{marker}")
    if not found:
        print("No serial ports found.")


def read_lines(connection: serial.Serial) -> list[str]:
    lines: list[str] = []
    while connection.in_waiting:
        raw = connection.readline()
        if not raw:
            break
        text = raw.decode("utf-8", errors="replace").strip()
        if text:
            lines.append(text)
    return lines


def send_command(connection: serial.Serial, command: str) -> None:
    connection.write((command + "\n").encode("ascii"))
    connection.flush()


def verify_robot(connection: serial.Serial, timeout: float = 4.0) -> bool:
    deadline = time.monotonic() + timeout
    next_status_request = time.monotonic() + 0.4

    while time.monotonic() < deadline:
        for line in read_lines(connection):
            if line.startswith("ROBOT READY") or line.startswith("STATUS FT="):
                return True

        now = time.monotonic()
        if now >= next_status_request:
            send_command(connection, "STATUS")
            next_status_request = now + 0.5
        time.sleep(0.03)

    return False


def connect_to_robot(
    requested_port: str | None,
) -> tuple[serial.Serial, PortCandidate]:
    detected = available_ports()

    if requested_port:
        matching = [port for port in detected if port.device == requested_port]
        candidates = matching or [
            PortCandidate(requested_port, "manually selected", None, None)
        ]
    else:
        candidates = detected

    if not candidates:
        raise RuntimeError("No serial ports found. Connect Arduino and try again.")

    errors: list[str] = []
    for candidate in candidates:
        print(f"Checking {candidate.device}: {candidate.description} ...")
        try:
            connection = serial.Serial(
                candidate.device,
                BAUD_RATE,
                timeout=0.05,
                write_timeout=0.5,
            )
        except SerialException as exc:
            errors.append(f"{candidate.device}: {exc}")
            continue

        try:
            if verify_robot(connection):
                connection.reset_input_buffer()
                return connection, candidate
            errors.append(f"{candidate.device}: robot firmware did not answer")
        except (SerialException, OSError) as exc:
            errors.append(f"{candidate.device}: {exc}")
        connection.close()

    details = "\n".join(errors)
    raise RuntimeError(f"Arduino robot was not found.\n{details}")


def motion_command(key: str, pwm: int) -> str:
    commands = {
        "w": f"F {pwm}",
        "s": f"B {pwm}",
        "a": f"L {pwm}",
        "d": f"R {pwm}",
    }
    return commands[key]


def print_controls() -> None:
    print(
        "\nControls (a motion remains active; holding the key is not required):\n"
        "  W  forward        S  backward\n"
        "  A  turn left      D  turn right\n"
        "  Space  stop       Q  stop and quit\n"
        "  + / -  change PWM by 10\n"
        "  E  encoders       I  status       R  reset encoders\n"
    )


def emergency_stop(connection: serial.Serial | None) -> None:
    if connection is None or not connection.is_open:
        return
    try:
        send_command(connection, "S")
        time.sleep(0.05)
    except (SerialException, OSError):
        pass


def run_controller(
    connection: serial.Serial,
    pwm: int,
    watchdog_ms: int,
    heartbeat: float,
) -> None:
    send_command(connection, "S")
    send_command(connection, f"T {watchdog_ms}")
    time.sleep(0.1)
    for line in read_lines(connection):
        print(f"Arduino: {line}")

    active_motion: str | None = None
    next_heartbeat = time.monotonic()
    print_controls()
    print(f"Connected safely: PWM={pwm}, watchdog={watchdog_ms} ms")

    with ConsoleKeyboard() as keyboard:
        while True:
            now = time.monotonic()
            key = keyboard.read_key()

            if key:
                key = key.lower()
                if key in ("q", "\x03"):
                    print("Stopping and closing controller.")
                    return
                if key == " ":
                    active_motion = None
                    send_command(connection, "S")
                    print("STOP")
                elif key in ("w", "s", "a", "d"):
                    active_motion = key
                    command = motion_command(active_motion, pwm)
                    send_command(connection, command)
                    next_heartbeat = now + heartbeat
                    print(f"Motion: {command}")
                elif key in ("+", "="):
                    pwm = min(255, pwm + 10)
                    print(f"PWM={pwm}")
                    if active_motion:
                        send_command(connection, motion_command(active_motion, pwm))
                        next_heartbeat = now + heartbeat
                elif key in ("-", "_"):
                    pwm = max(0, pwm - 10)
                    print(f"PWM={pwm}")
                    if active_motion:
                        send_command(connection, motion_command(active_motion, pwm))
                        next_heartbeat = now + heartbeat
                elif key == "e":
                    send_command(connection, "E")
                elif key == "i":
                    send_command(connection, "STATUS")
                elif key == "r":
                    send_command(connection, "RESET_E")

            if active_motion and now >= next_heartbeat:
                send_command(connection, motion_command(active_motion, pwm))
                next_heartbeat = now + heartbeat

            for line in read_lines(connection):
                if not line.startswith("OK M LEFT="):
                    print(f"Arduino: {line}")

            time.sleep(0.01)


def main() -> int:
    args = parse_args()
    ports = available_ports()
    if args.list:
        print_ports(ports)
        return 0

    connection: serial.Serial | None = None
    try:
        connection, port = connect_to_robot(args.port)
        print(f"Robot found on {port.device}: {port.description}")
        run_controller(
            connection,
            pwm=args.pwm,
            watchdog_ms=args.watchdog,
            heartbeat=args.heartbeat,
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
