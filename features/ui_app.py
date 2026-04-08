"""Tkinter-based UI application managed by the framework's MessageBus."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
import random
import time
import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from framework.bus import MessageBus
    from framework.channels.base import Message

log = logging.getLogger(__name__)

# File paths for the two screens
SCREEN1_FILE = "screen1_data.txt"
SCREEN2_FILE = "screen2_data.txt"


class UIApp:
    """Main Tkinter application. Manages two screens that communicate via MessageBus."""

    def __init__(self, bus: Optional[MessageBus] = None) -> None:
        self.bus = bus
        self.root = tk.Tk()
        self.root.title("框架UI演示 - 双屏通信")
        self.root.geometry("600x500")
        self.root.minsize(500, 400)

        # Style
        style = ttk.Style()
        style.configure("TButton", padding=6)
        style.configure("Header.TLabel", font=("Microsoft YaHei", 14, "bold"))
        style.configure("Content.TLabel", font=("Microsoft YaHei", 11))

        # Screen frames
        self.current_frame: Optional[tk.Frame] = None
        self.screen1_frame = self._create_screen1_frame()
        self.screen2_frame = self._create_screen2_frame()

        # Subscribe to bus messages for cross-screen communication
        # Wrap handlers in root.after() to marshal Tkinter calls to the main thread
        if self.bus:
            self.bus.subscribe(
                "ui.navigate_to_screen1",
                lambda m: self.root.after(0, lambda: self._on_navigate_screen1(m)),
            )
            self.bus.subscribe(
                "ui.navigate_to_screen2",
                lambda m: self.root.after(0, lambda: self._on_navigate_screen2(m)),
            )
            self.bus.subscribe(
                "ui.screen1_message",
                lambda m: self.root.after(0, lambda: self._on_screen1_message(m)),
            )
            self.bus.subscribe(
                "ui.screen2_message",
                lambda m: self.root.after(0, lambda: self._on_screen2_message(m)),
            )

    def _create_screen1_frame(self) -> tk.Frame:
        frame = ttk.Frame(self.root, padding=20)

        # Header
        ttk.Label(frame, text="屏幕 1", style="Header.TLabel").pack(pady=(0, 15))

        # Display area
        display_frame = ttk.LabelFrame(frame, text="内容显示", padding=10)
        display_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.screen1_text = tk.Text(
            display_frame, wrap=tk.WORD, height=12, font=("Microsoft YaHei", 10)
        )
        self.screen1_scroll = ttk.Scrollbar(
            display_frame, orient=tk.VERTICAL, command=self.screen1_text.yview
        )
        self.screen1_text.configure(yscrollcommand=self.screen1_scroll.set)
        self.screen1_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.screen1_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Button area
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="随机生成文本", command=self._screen1_btn1).pack(
            side=tk.LEFT, padx=2, expand=True
        )
        ttk.Button(btn_frame, text="跳转屏幕2", command=self._screen1_btn2).pack(
            side=tk.LEFT, padx=2, expand=True
        )
        ttk.Button(btn_frame, text="读取本地文件", command=self._screen1_btn3).pack(
            side=tk.LEFT, padx=2, expand=True
        )

        return frame

    def _create_screen2_frame(self) -> tk.Frame:
        frame = ttk.Frame(self.root, padding=20)

        # Header
        ttk.Label(frame, text="屏幕 2", style="Header.TLabel").pack(pady=(0, 15))

        # Display area
        display_frame = ttk.LabelFrame(frame, text="内容显示", padding=10)
        display_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        self.screen2_text = tk.Text(
            display_frame, wrap=tk.WORD, height=12, font=("Microsoft YaHei", 10)
        )
        self.screen2_scroll = ttk.Scrollbar(
            display_frame, orient=tk.VERTICAL, command=self.screen2_text.yview
        )
        self.screen2_text.configure(yscrollcommand=self.screen2_scroll.set)
        self.screen2_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.screen2_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # Button area
        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        ttk.Button(btn_frame, text="随机生成文本", command=self._screen2_btn1).pack(
            side=tk.LEFT, padx=2, expand=True
        )
        ttk.Button(btn_frame, text="跳转屏幕1", command=self._screen2_btn2).pack(
            side=tk.LEFT, padx=2, expand=True
        )
        ttk.Button(btn_frame, text="读取本地文件", command=self._screen2_btn3).pack(
            side=tk.LEFT, padx=2, expand=True
        )

        return frame

    def _show_screen1(self) -> None:
        if self.current_frame:
            self.current_frame.pack_forget()
        self.current_frame = self.screen1_frame
        self.current_frame.pack(fill=tk.BOTH, expand=True)
        self.root.title("框架UI演示 - 屏幕1")

    def _show_screen2(self) -> None:
        if self.current_frame:
            self.current_frame.pack_forget()
        self.current_frame = self.screen2_frame
        self.current_frame.pack(fill=tk.BOTH, expand=True)
        self.root.title("框架UI演示 - 屏幕2")

    # --- Screen 1 button handlers ---
    def _screen1_btn1(self) -> None:
        """Generate random text, write to screen1 file."""
        words = [
            "数据",
            "信息",
            "消息",
            "内容",
            "通信",
            "框架",
            "组件",
            "通道",
            "缓存",
            "快照",
        ]
        text = f"【屏幕1-随机生成】{time.strftime('%H:%M:%S')}\n"
        text += "".join(random.choices(words, k=random.randint(8, 20))) + "\n\n"
        text += f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"数据长度: {len(text)} 字符"

        with open(SCREEN1_FILE, "w", encoding="utf-8") as f:
            f.write(text)

        self.screen1_text.delete(1.0, tk.END)
        self.screen1_text.insert(tk.END, text)
        self._set_text_color(self.screen1_text, "#2E7D32")

    def _screen1_btn2(self) -> None:
        """Navigate to screen 2 and pass message via bus."""
        msg = f"来自屏幕1的消息 [{time.strftime('%H:%M:%S')}]: 我跳转到这里了！"

        if self.bus:
            self.bus.publish(
                "ui.navigate_to_screen2",
                payload={"message": msg, "source": "screen1"},
                sender="screen1",
            )
        else:
            self._show_screen2()
            self._append_screen2(f"总线未连接，直接跳转\n\n{msg}")

    def _screen1_btn3(self) -> None:
        """Read screen1 file and display."""
        try:
            with open(SCREEN1_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            self.screen1_text.delete(1.0, tk.END)
            self.screen1_text.insert(tk.END, content)
            self._set_text_color(self.screen1_text, "#1565C0")
        except FileNotFoundError:
            self.screen1_text.delete(1.0, tk.END)
            self.screen1_text.insert(tk.END, "本地文件不存在，请先生成文本。")
            self._set_text_color(self.screen1_text, "#757575")

    # --- Screen 2 button handlers ---
    def _screen2_btn1(self) -> None:
        """Generate random text, write to screen2 file."""
        words = [
            "高速",
            "通道",
            "零拷贝",
            "环形缓冲",
            "消息总线",
            "发布订阅",
            "实例池",
            "缓存命中",
            "状态快照",
            "中断恢复",
        ]
        text = f"【屏幕2-随机生成】{time.strftime('%H:%M:%S')}\n"
        text += "".join(random.choices(words, k=random.randint(8, 20))) + "\n\n"
        text += f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"数据长度: {len(text)} 字符"

        with open(SCREEN2_FILE, "w", encoding="utf-8") as f:
            f.write(text)

        self.screen2_text.delete(1.0, tk.END)
        self.screen2_text.insert(tk.END, text)
        self._set_text_color(self.screen2_text, "#2E7D32")

    def _screen2_btn2(self) -> None:
        """Navigate to screen 1 and pass message via bus."""
        msg = f"来自屏幕2的消息 [{time.strftime('%H:%M:%S')}]: 我跳转到这里了！"

        if self.bus:
            self.bus.publish(
                "ui.navigate_to_screen1",
                payload={"message": msg, "source": "screen2"},
                sender="screen2",
            )
        else:
            self._show_screen1()
            self._append_screen1(f"总线未连接，直接跳转\n\n{msg}")

    def _screen2_btn3(self) -> None:
        """Read screen2 file and display."""
        try:
            with open(SCREEN2_FILE, "r", encoding="utf-8") as f:
                content = f.read()
            self.screen2_text.delete(1.0, tk.END)
            self.screen2_text.insert(tk.END, content)
            self._set_text_color(self.screen2_text, "#1565C0")
        except FileNotFoundError:
            self.screen2_text.delete(1.0, tk.END)
            self.screen2_text.insert(tk.END, "本地文件不存在，请先生成文本。")
            self._set_text_color(self.screen2_text, "#757575")

    # --- Bus message handlers ---
    def _on_navigate_screen1(self, message: Message) -> Any:
        payload = message.payload if isinstance(message.payload, dict) else {}
        nav_msg = payload.get("message", "来自屏幕2的导航消息")
        source = payload.get("source", "unknown")

        self._show_screen1()
        self._append_screen1(f"\n{'=' * 40}\n[{source}]\n{nav_msg}\n{'=' * 40}")
        return {"navigated": True}

    def _on_navigate_screen2(self, message: Message) -> Any:
        payload = message.payload if isinstance(message.payload, dict) else {}
        nav_msg = payload.get("message", "来自屏幕1的导航消息")
        source = payload.get("source", "unknown")

        self._show_screen2()
        self._append_screen2(f"\n{'=' * 40}\n[{source}]\n{nav_msg}\n{'=' * 40}")
        return {"navigated": True}

    def _on_screen1_message(self, message: Message) -> Any:
        if isinstance(message.payload, str):
            self.screen1_text.insert(tk.END, f"\n[总线消息] {message.payload}")
        return None

    def _on_screen2_message(self, message: Message) -> Any:
        if isinstance(message.payload, str):
            self.screen2_text.insert(tk.END, f"\n[总线消息] {message.payload}")
        return None

    # --- Helpers ---
    def _append_screen1(self, text: str) -> None:
        self.screen1_text.insert(tk.END, text)
        self._set_text_color(self.screen1_text, "#6A1B9A")

    def _append_screen2(self, text: str) -> None:
        self.screen2_text.insert(tk.END, text)
        self._set_text_color(self.screen2_text, "#6A1B9A")

    def _set_text_color(self, text_widget: tk.Text, color: str) -> None:
        text_widget.tag_configure("color", foreground=color)
        text_widget.tag_add("color", 1.0, tk.END)

    def run(self) -> None:
        """Start the application on screen 1."""
        self._show_screen1()
        self.root.mainloop()
