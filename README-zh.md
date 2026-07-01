# vrc-osc-chat

VRChat OSC Chatbox —— 终端输入中文 + 系统状态实时监控，持续显示在人物头顶。

## 功能

- 🖥️ **系统状态监控**：OS 信息、Proton 版本、CPU 温度/使用率、内存、GPU 温度/使用率/显存，定时刷新到 VRChat 聊天框
- 💬 **聊天**：终端输入中文/日文/emoji，直接发送到 VRChat 聊天框
- 🔒 **线程安全**：后台监控线程与用户输入互不阻塞

## 环境要求

- Python >= 3.10
- [python-osc](https://pypi.org/project/python-osc/) >= 1.10.2
- VRChat 需开启 OSC（Settings → OSC → Enabled）

## 安装

```bash
uv sync
```

## 使用

```bash
# 交互模式（带系统状态监控）
uv run main.py

# 交互模式（仅聊天，不显示系统状态）
uv run main.py --no-monitor

# 单条发送
uv run main.py "你好世界"

# 管道输入
echo "大家好" | uv run main.py

# 自定义 OSC 地址
uv run main.py --host 127.0.0.1 --port 9000
```

## 交互命令

| 命令 | 说明 |
|------|------|
| `/monitor off` | 关闭系统状态显示 |
| `/monitor on` | 开启系统状态显示 |
| `/clear` | 清空聊天框 |
| `/quit` | 退出程序 |
