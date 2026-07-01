# vrc-osc-chat

VRChat OSC Chatbox — type messages from the terminal and display real-time system stats above your avatar.

## Features

- 🖥️ **System monitoring**: OS info, Proton version, CPU temp/usage, RAM, GPU temp/usage/VRAM — refreshed on a timer and shown in the VRChat chatbox
- 💬 **Chat**: type messages (Chinese, Japanese, emoji, anything) directly in the terminal and send them to VRChat
- 🔒 **Thread-safe**: background monitor thread never blocks user input

## Requirements

- Python >= 3.10
- [python-osc](https://pypi.org/project/python-osc/) >= 1.10.2
- VRChat with OSC enabled (Settings → OSC → Enabled)

## Installation

```bash
uv sync
```

## Usage

```bash
# Interactive mode with system monitor
uv run main.py

# Interactive mode, chat only (no system stats)
uv run main.py --no-monitor

# Send a single message
uv run main.py "Hello world"

# Pipe input
echo "hey everyone" | uv run main.py

# Custom OSC host/port
uv run main.py --host 127.0.0.1 --port 9000
```

## Interactive Commands

| Command | Description |
|---------|-------------|
| `/monitor off` | Hide system stats |
| `/monitor on` | Show system stats |
| `/clear` | Clear the chatbox |
| `/quit` | Exit |
