"""Windows grey-test shell. All brain operations run on one worker.

No engine imports; the existing birth pipeline and articulation validators remain
the authority. DeepSeek is deliberately disabled for this grey test (known 402).
"""
from __future__ import annotations

import argparse
import json
import queue
import shutil
import threading
import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

from . import llm_opencode, pipeline
from .articulate import set_llm_hook, set_stub_mode
from .memory import configure_memory, default_memory_path


class BackendUnavailable(RuntimeError):
    pass


class ChatSession:
    def __init__(self, *, memory_path=None, offline=False):
        from pathlib import Path
        path = Path(memory_path).expanduser() if memory_path else default_memory_path()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not (isinstance(raw, list) or isinstance(raw, dict) and isinstance(raw.get("sessions"), list)):
                raise ValueError("Invalid memory file; refusing overwrite")
        self.offline = offline
        self.model = llm_opencode.DEFAULT_MODEL
        configure_memory(enabled=True, path=memory_path)
        set_stub_mode(offline)
        # Use the existing extension point, never the DeepSeek cascade.
        set_llm_hook(None if offline else llm_opencode.generate_utterance)
        pipeline._persist_and_reset_session()

    def send(self, text, display):
        if not self.offline and (
            not shutil.which("opencode") or "deepseek" in self.model.lower()
        ):
            raise BackendUnavailable()

        def confirmed(result):
            if not self.offline and result.articulate_source != "hook":
                # Raising here prevents fallback templates becoming spoken facts.
                raise BackendUnavailable()
            display(result)

        return pipeline.turn(text, stub=self.offline, sense=False, output=confirmed)

    def new(self):
        pipeline._persist_and_reset_session()

    def close(self):
        pipeline.end_session()


class Delivery:
    def __init__(self, result):
        self.result = result
        self.done = threading.Event()
        self.error = None

    def wait(self):
        self.done.wait()
        if self.error is not None:
            raise self.error


class ChatWindow:
    def __init__(self, root, *, memory_path=None, offline=False):
        self.root = root
        self.offline = offline
        self.events = queue.Queue()
        self.busy = True
        self.closing = False
        self.session = None
        root.title("第一期 · 聊天" + (" [离线模板验证]" if offline else ""))
        root.geometry("760x650")
        root.minsize(520, 420)
        frame = ttk.Frame(root, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="第一期 · 聊天", font=("Microsoft YaHei UI", 18)).pack(anchor="w")
        self.status = tk.StringVar(value="正在打开记忆…")
        ttk.Label(frame, textvariable=self.status, wraplength=700).pack(anchor="w", pady=(6, 12))
        self.history = ScrolledText(frame, wrap="word", state="disabled", font=("Microsoft YaHei UI", 11))
        self.history.pack(fill="both", expand=True)
        self.entry = tk.Text(frame, height=4, wrap="word", font=("Microsoft YaHei UI", 11))
        self.entry.pack(fill="x", pady=(12, 8))
        self.entry.bind("<Control-Return>", self.send)
        buttons = ttk.Frame(frame)
        buttons.pack(fill="x")
        self.send_button = ttk.Button(buttons, text="发送 (Ctrl+Enter)", command=self.send)
        self.send_button.pack(side="left")
        self.new_button = ttk.Button(buttons, text="结束本场 / 新场", command=self.new)
        self.new_button.pack(side="left", padx=8)
        ttk.Button(buttons, text="保存并退出", command=self.close).pack(side="right")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._controls()
        root.after(20, self._poll)

        def initialize():
            self.session = ChatSession(memory_path=memory_path, offline=offline)
        self._work("open", initialize)

    def _append(self, speaker, text):
        self.history.configure(state="normal")
        try:
            self.history.insert("end", f"{speaker}\n{text}\n\n")
            self.history.see("end")
        finally:
            self.history.configure(state="disabled")

    def _controls(self):
        state = "disabled" if self.busy or self.session is None else "normal"
        self.send_button.configure(state=state)
        self.new_button.configure(state=state)
        self.entry.configure(state=state)

    def _work(self, kind, operation):
        self.busy = True
        self._controls()

        def run():
            try:
                operation()
            except Exception as exc:
                # Never transfer backend exception strings (may contain credentials).
                self.events.put(("error", kind, isinstance(exc, BackendUnavailable)))
            else:
                self.events.put(("done", kind, None))
        threading.Thread(target=run, daemon=True).start()

    def _display(self, result):
        delivery = Delivery(result)
        self.events.put(("display", delivery, None))
        delivery.wait()

    def _render(self, delivery):
        if delivery.done.is_set():
            return
        try:
            if not self.root.winfo_viewable():
                raise RuntimeError("Window is not visible")
            self._append("对方" if not self.offline else "离线模板（非真实模型）", delivery.result.utterance)
            # Tk flushes geometry and drawing before acknowledging the worker.
            self.root.update_idletasks()
        except Exception as exc:
            delivery.error = exc
        finally:
            delivery.done.set()

    def _poll(self):
        try:
            while True:
                event, kind, extra = self.events.get_nowait()
                if event == "display":
                    self._render(kind)
                    continue
                self.busy = False
                self._controls()
                if event == "error":
                    self.closing = False
                    message = ("后端不可用或输出未通过校验；未交付模板。需本机 OpenCode 及非 DeepSeek 模型配置。"
                               if extra else "操作失败；内容保留，未完成保存或输出确认。请重试，检查本机文件权限。")
                    self.status.set(message)
                    try:
                        self._append("状态", message)
                    except Exception:
                        pass  # Keep polling and allow saving if the transcript failed.
                else:
                    if kind == "close":
                        self.root.destroy()
                        return
                    if kind == "send":
                        self.entry.delete("1.0", "end")
                    if kind == "new":
                        self._append("状态", "本场已保存，已开始新场。")
                    source = ("离线模板验证，未请求模型" if self.offline else
                              f"OpenCode · {llm_opencode.DEFAULT_MODEL}；DeepSeek 已停用；输入感知降级为原有规则")
                    self.status.set(source)
                    if self.closing:
                        self.close()
                self._controls()
        except queue.Empty:
            pass
        self.root.after(20, self._poll)

    def send(self, event=None):
        if self.busy or self.session is None:
            return "break"
        text = self.entry.get("1.0", "end").strip()
        if text:
            self._append("你", text)
            self.status.set("正在回应… 可移动窗口；退出将在本轮完成后保存。")
            self._work("send", lambda: self.session.send(text, self._display))
        return "break"

    def new(self):
        if not self.busy and self.session is not None:
            self.status.set("正在保存本场…")
            self._work("new", self.session.new)

    def close(self):
        if self.busy:
            self.closing = True
            self.status.set("等待当前操作完成，随后保存并退出…")
        elif self.session is None:
            self.root.destroy()
        else:
            self.closing = False
            self.status.set("正在保存…")
            self._work("close", self.session.close)


def main(argv=None):
    parser = argparse.ArgumentParser(description="第一期 Windows 灰测聊天")
    parser.add_argument("--offline", action="store_true", help="明确的离线模板验证，不请求模型")
    parser.add_argument("--memory-path", default=None)
    args = parser.parse_args(argv)
    root = tk.Tk()
    ChatWindow(root, memory_path=args.memory_path, offline=args.offline)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
