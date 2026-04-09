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
        self.screen1_text, self.screen1_frame = self._create_screen_frame(
            "1", SCREEN1_FILE, "ui.navigate_to_screen2", self._show_screen2
        )
        self.screen2_text, self.screen2_frame = self._create_screen_frame(
            "2", SCREEN2_FILE, "ui.navigate_to_screen1", self._show_screen1
        )

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

    def _create_screen_frame(
        self, screen_id: str, file_path: str, navigate_topic: str, show_target: Any
    ) -> tuple[tk.Text, tk.Frame]:
        frame = ttk.Frame(self.root, padding=20)
        ttk.Label(frame, text=f"屏幕 {screen_id}", style="Header.TLabel").pack(
            pady=(0, 15)
        )

        display_frame = ttk.LabelFrame(frame, text="内容显示", padding=10)
        display_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 15))

        text_widget = tk.Text(
            display_frame, wrap=tk.WORD, height=12, font=("Microsoft YaHei", 10)
        )
        scroll = ttk.Scrollbar(
            display_frame, orient=tk.VERTICAL, command=text_widget.yview
        )
        text_widget.configure(yscrollcommand=scroll.set)
        text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        btn_frame = ttk.Frame(frame)
        btn_frame.pack(fill=tk.X)

        words_map = {
            "1": [
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
            ],
            "2": [
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
            ],
        }

        ttk.Button(
            btn_frame,
            text="随机生成文本",
            command=lambda: self._screen_btn1(
                screen_id, file_path, text_widget, words_map[screen_id]
            ),
        ).pack(side=tk.LEFT, padx=2, expand=True)

        target_id = "2" if screen_id == "1" else "1"
        ttk.Button(
            btn_frame,
            text=f"跳转屏幕{target_id}",
            command=lambda: self._screen_btn2(
                screen_id, target_id, navigate_topic, show_target
            ),
        ).pack(side=tk.LEFT, padx=2, expand=True)

        ttk.Button(
            btn_frame,
            text="读取本地文件",
            command=lambda: self._screen_btn3(file_path, text_widget),
        ).pack(side=tk.LEFT, padx=2, expand=True)

        return text_widget, frame

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

    # --- Generic button handlers ---
    def _screen_btn1(
        self, screen_id: str, file_path: str, text_widget: tk.Text, words: list[str]
    ) -> None:
        """Generate random text, write to screen file."""
        text = f"【屏幕{screen_id}-随机生成】{time.strftime('%H:%M:%S')}\n"
        text += "".join(random.choices(words, k=random.randint(8, 20))) + "\n\n"
        text += f"生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        text += f"数据长度: {len(text)} 字符"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(text)
        except OSError:
            log.exception("UIApp: failed to write %s", file_path)
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, "写入失败，请检查磁盘/权限。")
            self._set_text_color(text_widget, "#D32F2F")
            return

        text_widget.delete(1.0, tk.END)
        text_widget.insert(tk.END, text)
        self._set_text_color(text_widget, "#2E7D32")

    def _screen_btn2(
        self, source_id: str, target_id: str, navigate_topic: str, show_target: Any
    ) -> None:
        """Navigate to target screen and pass message via bus."""
        msg = (
            f"来自屏幕{source_id}的消息 [{time.strftime('%H:%M:%S')}]: 我跳转到这里了！"
        )

        if self.bus:
            self.bus.publish(
                navigate_topic,
                payload={"message": msg, "source": f"screen{source_id}"},
                sender=f"screen{source_id}",
            )
        else:
            show_target()
            target_append = (
                self._append_screen2 if target_id == "2" else self._append_screen1
            )
            target_append(f"总线未连接，直接跳转\n\n{msg}")

    def _screen_btn3(self, file_path: str, text_widget: tk.Text) -> None:
        """Read screen file and display."""
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, content)
            self._set_text_color(text_widget, "#1565C0")
        except FileNotFoundError:
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, "本地文件不存在，请先生成文本。")
            self._set_text_color(text_widget, "#757575")
        except OSError:
            log.exception("UIApp: failed to read %s", file_path)
            text_widget.delete(1.0, tk.END)
            text_widget.insert(tk.END, "读取失败，请检查磁盘/权限。")
            self._set_text_color(text_widget, "#D32F2F")

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
