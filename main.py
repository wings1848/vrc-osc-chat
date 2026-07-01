#!/usr/bin/env python3
"""VRChat OSC Chatbox — 终端输入中文 + 系统状态监控持续显示在人物头顶。

用法:
  uv run main.py              # 交互模式，带系统状态监控
  uv run main.py "你好世界"   # 单条发送
  uv run main.py --no-monitor # 仅聊天，不开启监控
"""

import argparse
import subprocess
import sys
import threading
import time
from pythonosc import udp_client

VRC_HOST = "127.0.0.1"
VRC_PORT = 9000
CHATBOX_INPUT = "/chatbox/input"
CHATBOX_TYPING = "/chatbox/typing"

MONITOR_INTERVAL = 3.0       # 系统信息刷新间隔（秒）
USER_MSG_TTL = 12.0           # 用户消息在聊天框保留时长（秒）


# ──────────────────── 文件读取 ────────────────────

def read_file(path: str) -> str:
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError as e:
        print(f"[WARN] 读取失败 {path}: {e}", file=sys.stderr)
        return ""


# ──────────────────── 系统信息采集（不变部分缓存） ────────────────────

_SYS_PREFIX: str = ""


def _init_cached_info() -> None:
    """启动时一次性读取不会变的信息"""
    global _SYS_PREFIX

    try:
        # 系统名（取 PRETTY_NAME 或 ID）
        os_name = ""
        for line in read_file("/etc/os-release").splitlines():
            if line.startswith("PRETTY_NAME="):
                os_name = line.split("=", 1)[1].strip('"')
                break
        if not os_name:
            os_name = "--"

        # 简短内核版本：7.2.0-rc1-1-cachyos-rc → 7.2.0-rc1
        raw = read_file("/proc/sys/kernel/osrelease")
        parts = raw.split("-", 2)
        kernel = "-".join(parts[:2]) if len(parts) >= 2 else raw

        _SYS_PREFIX = f"{os_name} {kernel}"
    except Exception as e:
        print(f"[WARN] System info: {e}", file=sys.stderr)
        _SYS_PREFIX = "--"


def get_cpu_temp() -> str:
    """CPU 封装温度"""
    # 遍历 thermal_zone 查找 x86_pkg_temp
    for i in range(10):
        type_file = f"/sys/class/thermal/thermal_zone{i}/type"
        try:
            with open(type_file) as f:
                if f.read().strip() == "x86_pkg_temp":
                    t = read_file(f"/sys/class/thermal/thermal_zone{i}/temp")
                    if t:
                        return f"{int(t) / 1000:.0f}°C"
        except OSError:
            continue

    # 备选：遍历 hwmon 查找 coretemp
    for i in range(10):
        label_file = f"/sys/class/hwmon/hwmon{i}/temp1_label"
        try:
            with open(label_file) as f:
                if "core" in f.read().strip().lower():
                    t = read_file(f"/sys/class/hwmon/hwmon{i}/temp1_input")
                    if t:
                        return f"{int(t) / 1000:.0f}°C"
        except OSError:
            continue

    return "--"


def get_cpu_usage() -> str:
    """CPU 使用率 (采样 0.2s)"""
    try:
        with open("/proc/stat") as f:
            s1 = f.readline().split()
        if len(s1) < 5:
            return "--"
        total1 = sum(int(x) for x in s1[1:])
        idle1 = int(s1[4])
        time.sleep(0.2)
        with open("/proc/stat") as f:
            s2 = f.readline().split()
        total2 = sum(int(x) for x in s2[1:])
        idle2 = int(s2[4])
        delta_total = total2 - total1
        if delta_total == 0:
            return "--"
        return f"{(1 - (idle2 - idle1) / delta_total) * 100:.0f}%"
    except OSError as e:
        print(f"[WARN] CPU usage: {e}", file=sys.stderr)
        return "--"


def get_ram() -> str:
    """已用 / 总内存 (GB)"""
    try:
        total = avail = 0.0
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    total = int(line.split()[1]) / 1024 / 1024
                elif line.startswith("MemAvailable:"):
                    avail = int(line.split()[1]) / 1024 / 1024
                if total and avail:
                    break
        if total:
            return f"{total - avail:.1f}/{total:.1f}G"
        return "--"
    except OSError as e:
        print(f"[WARN] RAM: {e}", file=sys.stderr)
        return "--"


def get_gpu() -> tuple[str, str, str]:
    """返回 (温度, 使用率, 显存)"""
    try:
        out = subprocess.check_output(
            ["nvidia-smi",
             "--query-gpu=temperature.gpu,utilization.gpu,memory.used,memory.total",
             "--format=csv,noheader,nounits"],
            timeout=3, text=True
        ).strip()
        temp, util, vram_used, vram_total = out.split(", ")
        vram = f"{int(vram_used) / 1024:.1f}/{int(vram_total) / 1024:.1f}G"
        return f"{temp}°C", f"{util}%", vram
    except Exception as e:
        print(f"[WARN] GPU: {e}", file=sys.stderr)
        return "--", "--", "--"


def build_chatbox_text(user_text: str) -> str:
    """组合系统信息 + 硬件状态 + 用户消息"""
    gpu_temp, gpu_util, vram = get_gpu()
    hw_line = (
        f"{_SYS_PREFIX}  "
        f"GPU:{gpu_temp} {gpu_util}  "
        f"VRAM:{vram}  "
        f"RAM:{get_ram()}  "
        f"CPU:{get_cpu_temp()} {get_cpu_usage()}"
    )

    # 始终保留第二行，减少文本结构变化导致的闪烁
    return f"{hw_line}\n{user_text}"


# ──────────────────── OSC 发送 ────────────────────

def send_chatbox(client: udp_client.SimpleUDPClient, text: str,
                 typing: bool = True) -> None:
    if typing:
        client.send_message(CHATBOX_TYPING, True)
    client.send_message(CHATBOX_INPUT, [text, True])
    if typing:
        time.sleep(0.05)
        client.send_message(CHATBOX_TYPING, False)


# ──────────────────── 后台监控线程 ────────────────────

class ChatState:
    """线程安全的聊天状态"""

    def __init__(self):
        self._lock = threading.Lock()
        self._user_text = ""
        self._user_time = 0.0
        self._monitor_enabled = True
        self._running = True
        self._wakeup = threading.Event()

    # ── 用户消息 ──

    def set_user_text(self, text: str) -> None:
        with self._lock:
            self._user_text = text
            self._user_time = time.time()

    def get_user_text(self) -> str:
        with self._lock:
            if self._user_text and (time.time() - self._user_time) > USER_MSG_TTL:
                self._user_text = ""
            return self._user_text

    # ── 监控开关 ──

    @property
    def monitor_enabled(self) -> bool:
        with self._lock:
            return self._monitor_enabled

    @monitor_enabled.setter
    def monitor_enabled(self, value: bool) -> None:
        with self._lock:
            self._monitor_enabled = value
        if value:
            self._wakeup.set()  # 立即刷新

    # ── 生命周期 ──

    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    def stop(self) -> None:
        with self._lock:
            self._running = False
        self._wakeup.set()  # 唤醒 sleep，立即退出

    def wait(self, timeout: float) -> bool:
        """等待 timeout 秒，若被 stop/wake 则立即返回 True"""
        self._wakeup.clear()
        return self._wakeup.wait(timeout)


def monitor_loop(client: udp_client.SimpleUDPClient, state: ChatState) -> None:
    """后台线程：定时刷新系统状态 + 用户消息到聊天框"""
    while state.running:
        if state.monitor_enabled:
            try:
                text = build_chatbox_text(state.get_user_text())
                send_chatbox(client, text, typing=False)
            except Exception as e:
                print(f"[WARN] OSC 发送失败: {e}", file=sys.stderr)
        state.wait(MONITOR_INTERVAL)


# ──────────────────── 交互模式 ────────────────────

def _print_banner(monitor: bool = True) -> None:
    print("🟢 VRChat OSC Chatbox 已启动")
    if monitor:
        print("   系统状态持续显示在头顶，输入中文回车发送")
    print()
    print("   命令:")
    if monitor:
        print("     /monitor off  关闭系统状态显示")
        print("     /monitor on   开启系统状态显示")
    print("     /clear        清空聊天框")
    print("     /quit         退出")
    print()


def interactive(client: udp_client.SimpleUDPClient) -> None:
    state = ChatState()

    monitor = threading.Thread(target=monitor_loop, args=(client, state), daemon=True)
    monitor.start()

    _print_banner(monitor=True)

    try:
        while True:
            line = input("> ")
            cmd = line.strip()
            if cmd == "/quit":
                break
            if cmd == "/clear":
                state.set_user_text("")
                print("   ✅ 已清空")
            elif cmd == "/monitor off":
                state.monitor_enabled = False
                print("   🔇 系统状态已关闭")
            elif cmd == "/monitor on":
                state.monitor_enabled = True
                print("   🔊 系统状态已开启")
            elif cmd:
                state.set_user_text(cmd)
                print(f"   ✅ 已发送: {cmd}")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        state.stop()


def interactive_no_monitor(client: udp_client.SimpleUDPClient) -> None:
    state = ChatState()
    state.monitor_enabled = False

    monitor = threading.Thread(target=monitor_loop, args=(client, state), daemon=True)
    monitor.start()

    _print_banner(monitor=False)

    try:
        while True:
            line = input("> ")
            cmd = line.strip()
            if cmd == "/quit":
                break
            if cmd == "/clear":
                send_chatbox(client, "")
                print("   ✅ 已清空")
            elif cmd:
                send_chatbox(client, cmd)
                print(f"   ✅ 已发送: {cmd}")
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        state.stop()


# ──────────────────── 入口 ────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="VRChat OSC Chatbox")
    parser.add_argument("text", nargs="*", help="要发送的文字，留空进入交互模式")
    parser.add_argument("--host", default=VRC_HOST)
    parser.add_argument("--port", type=int, default=VRC_PORT)
    parser.add_argument("--no-monitor", action="store_true", help="不启动系统监控")

    args = parser.parse_args()
    client = udp_client.SimpleUDPClient(args.host, args.port)

    # 一次性初始化缓存信息（所有模式通用）
    _init_cached_info()

    # 单条发送
    if args.text:
        text = " ".join(args.text)
        send_chatbox(client, text)
        print(f"✅ 已发送: {text}")
        return

    # 管道输入
    if not sys.stdin.isatty():
        text = sys.stdin.read().strip()
        if text:
            send_chatbox(client, text)
            print(f"✅ 已发送: {text}")
        return

    # 交互模式
    if args.no_monitor:
        interactive_no_monitor(client)
    else:
        interactive(client)


if __name__ == "__main__":
    main()
