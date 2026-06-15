from __future__ import annotations

import json
import math
import queue
import socket
import struct
import threading
import time
import tkinter as tk
from dataclasses import asdict, dataclass
from pathlib import Path
from tkinter import messagebox, simpledialog
from typing import Optional, Tuple

APP_NAME = "FH6 G-Meter Overlay"
CONFIG_PATH = Path(__file__).with_name("config.json")


@dataclass
class AppConfig:
    udp_host: str = "127.0.0.1"
    udp_port: int = 1024
    forward_enabled: bool = False
    forward_host: str = "127.0.0.1"
    forward_port: int = 1025
    window_x: int = 80
    window_y: int = 80
    window_size: int = 260
    locked: bool = False
    always_on_top: bool = True
    opacity: float = 0.86
    max_g: float = 2.0
    smooth_factor: float = 0.22
    transparent_background: bool = True
    bg_color: str = "#010203"
    accent_color: str = "#48e1ff"
    dot_color: str = "#ff465f"
    packet_mode: str = "forza_dash"


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()

    try:
        raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return AppConfig()

    defaults = asdict(AppConfig())
    defaults.update({k: v for k, v in raw.items() if k in defaults})
    return AppConfig(**defaults)


def save_config(config: AppConfig) -> None:
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


@dataclass
class TelemetrySample:
    lateral_g: float = 0.0
    longitudinal_g: float = 0.0
    vertical_g: float = 0.0
    timestamp: float = 0.0
    packets: int = 0


class ForzaTelemetryParser:
    STANDARD_GRAVITY_MPS2 = 9.80665
    ACCELERATION_X_OFFSET = 20
    ACCELERATION_Y_OFFSET = 24
    ACCELERATION_Z_OFFSET = 28
    MIN_ACCELERATION_PACKET_SIZE = ACCELERATION_Z_OFFSET + 4

    def parse(self, packet: bytes, packet_count: int) -> Optional[TelemetrySample]:
        if len(packet) < self.MIN_ACCELERATION_PACKET_SIZE:
            return None

        try:
            accel_x = self.unpack_gravity_acceleration(packet, self.ACCELERATION_X_OFFSET)
            accel_y = self.unpack_gravity_acceleration(packet, self.ACCELERATION_Y_OFFSET)
            accel_z = self.unpack_gravity_acceleration(packet, self.ACCELERATION_Z_OFFSET)
        except struct.error:
            return None

        return TelemetrySample(
            lateral_g=accel_x,
            longitudinal_g=accel_z,
            vertical_g=accel_y,
            timestamp=time.time(),
            packets=packet_count,
        )

    def unpack_gravity_acceleration(self, packet: bytes, offset: int) -> float:
        return struct.unpack_from("<f", packet, offset)[0] / self.STANDARD_GRAVITY_MPS2


class UdpTelemetryReceiver:
    def __init__(self, config: AppConfig, output: queue.Queue[TelemetrySample]):
        self.config = config
        self.output = output
        self.parser = ForzaTelemetryParser()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._socket: Optional[socket.socket] = None
        self._forward_socket: Optional[socket.socket] = None
        self.error: Optional[str] = None
        self.packet_count = 0

    def start(self) -> None:
        self.stop()
        self.error = None
        self.packet_count = 0
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="udp-telemetry", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        sock = self._socket
        self._socket = None
        if sock is not None:
            try:
                sock.close()
            except OSError:
                pass
        forward_sock = self._forward_socket
        self._forward_socket = None
        if forward_sock is not None:
            try:
                forward_sock.close()
            except OSError:
                pass

    def _run(self) -> None:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.config.udp_host, int(self.config.udp_port)))
            sock.settimeout(0.25)
            self._socket = sock
        except OSError as exc:
            self.error = f"UDP {self.config.udp_host}:{self.config.udp_port} を開けません: {exc}"
            return

        forward_target = self.forward_target()
        if forward_target is not None:
            self._forward_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        while not self._stop.is_set():
            try:
                packet, _addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break

            self.forward_packet(packet, forward_target)
            self.packet_count += 1
            sample = self.parser.parse(packet, self.packet_count)
            if sample is not None:
                self.output.put(sample)

    def forward_target(self) -> Optional[Tuple[str, int]]:
        if not self.config.forward_enabled:
            return None
        host = self.config.forward_host.strip()
        port = int(self.config.forward_port)
        if not host or port <= 0:
            return None
        if port == int(self.config.udp_port) and host in {"127.0.0.1", "localhost", self.config.udp_host}:
            return None
        return host, port

    def forward_packet(self, packet: bytes, target: Optional[Tuple[str, int]]) -> None:
        if target is None or self._forward_socket is None:
            return
        try:
            self._forward_socket.sendto(packet, target)
        except OSError:
            pass


class SettingsDialog(simpledialog.Dialog):
    def __init__(self, parent: tk.Tk, config: AppConfig):
        self.config = config
        self.result_config: Optional[AppConfig] = None
        super().__init__(parent, "設定")

    def body(self, master: tk.Frame) -> tk.Widget:
        self.entries: dict[str, tk.Entry] = {}

        fields = [
            ("UDP受信IP", "udp_host", self.config.udp_host),
            ("UDPポート", "udp_port", str(self.config.udp_port)),
            ("転送先IP", "forward_host", self.config.forward_host),
            ("転送先ポート", "forward_port", str(self.config.forward_port)),
            ("サイズ(px)", "window_size", str(self.config.window_size)),
            ("最大G", "max_g", str(self.config.max_g)),
            ("不透明度(0.2-1.0)", "opacity", str(self.config.opacity)),
            ("スムージング(0.01-1.0)", "smooth_factor", str(self.config.smooth_factor)),
        ]

        for row, (label, key, value) in enumerate(fields):
            tk.Label(master, text=label, anchor="w").grid(row=row, column=0, sticky="w", padx=8, pady=5)
            entry = tk.Entry(master, width=16)
            entry.insert(0, value)
            entry.grid(row=row, column=1, sticky="ew", padx=8, pady=5)
            self.entries[key] = entry

        self.top_var = tk.BooleanVar(value=self.config.always_on_top)
        self.transparent_var = tk.BooleanVar(value=self.config.transparent_background)
        self.forward_var = tk.BooleanVar(value=self.config.forward_enabled)
        tk.Checkbutton(master, text="Data Outを転送", variable=self.forward_var).grid(
            row=len(fields), column=0, columnspan=2, sticky="w", padx=8, pady=5
        )
        tk.Checkbutton(master, text="常に最前面", variable=self.top_var).grid(
            row=len(fields) + 1, column=0, columnspan=2, sticky="w", padx=8, pady=5
        )
        tk.Checkbutton(master, text="背景を透過", variable=self.transparent_var).grid(
            row=len(fields) + 2, column=0, columnspan=2, sticky="w", padx=8, pady=5
        )
        return self.entries["udp_port"]

    def _read_values(self) -> dict[str, object]:
        udp_host = self.entries["udp_host"].get().strip()
        forward_host = self.entries["forward_host"].get().strip()
        udp_port = int(self.entries["udp_port"].get())
        forward_port = int(self.entries["forward_port"].get())
        window_size = int(self.entries["window_size"].get())
        max_g = float(self.entries["max_g"].get())
        opacity = float(self.entries["opacity"].get())
        smooth_factor = float(self.entries["smooth_factor"].get())
        if not udp_host:
            raise ValueError("udp_host")
        if not (1 <= udp_port <= 65535) or not (1 <= forward_port <= 65535):
            raise ValueError("port")
        if self.forward_var.get() and not forward_host:
            raise ValueError("forward_host")
        return {
            "udp_host": udp_host,
            "udp_port": udp_port,
            "forward_host": forward_host,
            "forward_port": forward_port,
            "window_size": window_size,
            "max_g": max_g,
            "opacity": opacity,
            "smooth_factor": smooth_factor,
        }

    def validate(self) -> bool:
        try:
            self._read_values()
        except ValueError:
            messagebox.showerror("設定エラー", "数値の入力を確認してください。")
            return False
        return True

    def apply(self) -> None:
        values = self._read_values()
        window_size = int(values["window_size"])
        max_g = float(values["max_g"])
        opacity = float(values["opacity"])
        smooth_factor = float(values["smooth_factor"])
        opacity = min(1.0, max(0.2, opacity))
        smooth_factor = min(1.0, max(0.01, smooth_factor))
        window_size = min(640, max(120, window_size))
        max_g = min(5.0, max(0.5, max_g))

        updated = AppConfig(**asdict(self.config))
        updated.udp_host = str(values["udp_host"])
        updated.udp_port = int(values["udp_port"])
        updated.forward_enabled = self.forward_var.get()
        updated.forward_host = str(values["forward_host"])
        updated.forward_port = int(values["forward_port"])
        updated.window_size = window_size
        updated.max_g = max_g
        updated.opacity = opacity
        updated.smooth_factor = smooth_factor
        updated.always_on_top = self.top_var.get()
        updated.transparent_background = self.transparent_var.get()
        self.result_config = updated


class GmeterOverlay:
    def __init__(self) -> None:
        self.config = load_config()
        self.samples: queue.Queue[TelemetrySample] = queue.Queue()
        self.receiver = UdpTelemetryReceiver(self.config, self.samples)
        self.sample = TelemetrySample(timestamp=0.0)
        self.display_lateral = 0.0
        self.display_longitudinal = 0.0
        self.drag_start: Optional[Tuple[int, int]] = None

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.overrideredirect(True)
        self.root.geometry(f"{self.config.window_size}x{self.config.window_size}+{self.config.window_x}+{self.config.window_y}")
        self.root.configure(bg=self.config.bg_color)
        self.root.attributes("-topmost", self.config.always_on_top)
        self.root.attributes("-alpha", self.config.opacity)
        if self.config.transparent_background:
            self._apply_transparency()

        self.canvas = tk.Canvas(
            self.root,
            width=self.config.window_size,
            height=self.config.window_size,
            highlightthickness=0,
            bg=self.config.bg_color,
        )
        self.canvas.pack(fill="both", expand=True)

        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="位置を固定/解除", command=self.toggle_lock)
        self.menu.add_command(label="設定", command=self.open_settings)
        self.menu.add_separator()
        self.menu.add_command(label="終了", command=self.close)

        self.root.bind("<ButtonPress-1>", self.begin_drag)
        self.root.bind("<B1-Motion>", self.drag)
        self.root.bind("<ButtonRelease-1>", self.end_drag)
        self.root.bind("<Button-3>", self.show_menu)
        self.root.bind("<Escape>", lambda _event: self.close())
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _apply_transparency(self) -> None:
        try:
            self.root.attributes("-transparentcolor", self.config.bg_color)
        except tk.TclError:
            pass

    def run(self) -> None:
        self.receiver.start()
        self.root.after(16, self.tick)
        self.root.mainloop()

    def tick(self) -> None:
        latest = None
        while True:
            try:
                latest = self.samples.get_nowait()
            except queue.Empty:
                break
        if latest is not None:
            self.sample = latest

        factor = self.config.smooth_factor
        self.display_lateral += (self.sample.lateral_g - self.display_lateral) * factor
        self.display_longitudinal += (self.sample.longitudinal_g - self.display_longitudinal) * factor
        self.draw()
        self.root.after(16, self.tick)

    def draw(self) -> None:
        size = self.config.window_size
        center = size / 2
        outer = size * 0.42
        self.canvas.delete("all")

        grid_color = "#d9f9ff"
        dim_color = "#86a7ad"
        accent = self.config.accent_color
        dot = self.config.dot_color

        self.aa_oval(center - outer, center - outer, center + outer, center + outer, outline=grid_color, width=3)
        for ratio in (0.5,):
            radius = outer * ratio
            self.aa_oval(center - radius, center - radius, center + radius, center + radius, outline=dim_color, width=3)

        self.aa_line(center - outer, center, center + outer, center, fill=dim_color, width=3)
        self.aa_line(center, center - outer, center, center + outer, fill=dim_color, width=3)
        self.canvas.create_text(center, center - outer - 14, text=f"{self.config.max_g:.1f}G", fill=grid_color, font=("Segoe UI", 9, "bold"))

        max_g = max(self.config.max_g, 0.1)
        clamped_x = max(-max_g, min(max_g, self.display_lateral))
        clamped_y = max(-max_g, min(max_g, self.display_longitudinal))
        dot_x = center - (clamped_x / max_g) * outer
        dot_y = center + (clamped_y / max_g) * outer
        magnitude = math.hypot(self.display_lateral, self.display_longitudinal)

        self.aa_line(center, center, dot_x, dot_y, fill=accent, width=2)
        self.aa_oval(dot_x - 9, dot_y - 9, dot_x + 9, dot_y + 9, outline="#ffffff", width=3)
        self.aa_filled_oval(dot_x - 8, dot_y - 8, dot_x + 8, dot_y + 8, fill=dot)
        self.canvas.create_text(center, center + 6, text=f"{magnitude:.2f}G", fill="#ffffff", font=("Segoe UI", 20, "bold"))

        status = self.status_text()
        if status:
            self.canvas.create_text(center, size - 13, text=status, fill=dim_color, font=("Segoe UI", 10, "bold"))
        if self.config.locked:
            self.canvas.create_text(size - 18, 17, text="LOCK", fill=accent, font=("Segoe UI", 8, "bold"), anchor="e")

    def aa_line(self, *coords: float, fill: str, width: float) -> None:
        self.canvas.create_line(*coords, fill=self.aa_color(fill), width=width + 1.0)
        self.canvas.create_line(*coords, fill=fill, width=width)

    def aa_oval(self, x1: float, y1: float, x2: float, y2: float, outline: str, width: float) -> None:
        self.canvas.create_oval(x1, y1, x2, y2, outline=self.aa_color(outline), width=width + 1.0)
        self.canvas.create_oval(x1, y1, x2, y2, outline=outline, width=width)

    def aa_filled_oval(self, x1: float, y1: float, x2: float, y2: float, fill: str) -> None:
        fringe = self.aa_color(fill)
        self.canvas.create_oval(x1 - 1, y1 - 1, x2 + 1, y2 + 1, fill=fringe, outline=fringe, width=1)
        self.canvas.create_oval(x1, y1, x2, y2, fill=fill, outline=fill, width=1)

    @staticmethod
    def aa_color(color: str) -> str:
        color = color.lstrip("#")
        if len(color) != 6:
            return "#555555"
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)
        return f"#{int(r * 0.38):02x}{int(g * 0.38):02x}{int(b * 0.38):02x}"

    def status_text(self) -> str:
        if self.receiver.error:
            return self.receiver.error
        age = time.time() - self.sample.timestamp if self.sample.timestamp else 999.0
        if age > 2.0:
            return f"UDP :{self.config.udp_port} 待機中"
        return ""

    def begin_drag(self, event: tk.Event) -> None:
        if self.config.locked:
            return
        self.drag_start = (event.x_root - self.root.winfo_x(), event.y_root - self.root.winfo_y())

    def drag(self, event: tk.Event) -> None:
        if self.config.locked or self.drag_start is None:
            return
        offset_x, offset_y = self.drag_start
        x = event.x_root - offset_x
        y = event.y_root - offset_y
        self.root.geometry(f"+{x}+{y}")

    def end_drag(self, _event: tk.Event) -> None:
        self.drag_start = None
        self.persist_position()

    def persist_position(self) -> None:
        self.config.window_x = self.root.winfo_x()
        self.config.window_y = self.root.winfo_y()
        save_config(self.config)

    def show_menu(self, event: tk.Event) -> None:
        self.menu.tk_popup(event.x_root, event.y_root)

    def toggle_lock(self) -> None:
        self.config.locked = not self.config.locked
        self.persist_position()

    def open_settings(self) -> None:
        dialog = SettingsDialog(self.root, self.config)
        if dialog.result_config is None:
            return

        old_network_config = (
            self.config.udp_host,
            self.config.udp_port,
            self.config.forward_enabled,
            self.config.forward_host,
            self.config.forward_port,
        )
        self.config = dialog.result_config
        new_network_config = (
            self.config.udp_host,
            self.config.udp_port,
            self.config.forward_enabled,
            self.config.forward_host,
            self.config.forward_port,
        )
        self.persist_position()
        save_config(self.config)
        self.root.geometry(f"{self.config.window_size}x{self.config.window_size}+{self.config.window_x}+{self.config.window_y}")
        self.root.attributes("-topmost", self.config.always_on_top)
        self.root.attributes("-alpha", self.config.opacity)
        self.root.configure(bg=self.config.bg_color)
        self.canvas.configure(width=self.config.window_size, height=self.config.window_size, bg=self.config.bg_color)
        if self.config.transparent_background:
            self._apply_transparency()
        self.receiver.config = self.config
        if old_network_config != new_network_config:
            self.receiver.start()

    def close(self) -> None:
        self.persist_position()
        self.receiver.stop()
        self.root.destroy()


if __name__ == "__main__":
    GmeterOverlay().run()
