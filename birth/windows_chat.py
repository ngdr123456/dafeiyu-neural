"""Windows grey-test shell. All brain operations run on one worker.

No engine imports; the existing birth pipeline and articulation validators remain
the authority. Real mode uses DeepSeek only, with explicit failure reporting.
"""
from __future__ import annotations

import argparse
import json
import queue
import threading
import tkinter as tk
from tkinter.scrolledtext import ScrolledText

from . import llm_deepseek, pipeline
from .input_sense import sense_input
from .articulate import set_llm_hook, set_stub_mode
from .memory import configure_memory, default_memory_path


class BackendUnavailable(RuntimeError):
    def __init__(self, code="validation"):
        self.code = code if code in BACKEND_MESSAGES else "backend"
        super().__init__(self.code)


BACKEND_MESSAGES = {
    "no_key": "未配置 DeepSeek 密钥。请按使用说明在本机安全配置。",
    "quota": "DeepSeek 额度不足（HTTP 402），本轮未交付。",
    "auth": "DeepSeek 身份验证失败，请检查本机凭证。",
    "http": "DeepSeek 服务请求失败，本轮未交付。",
    "network": "DeepSeek 网络连接失败或超时，本轮未交付。",
    "invalid_output": "DeepSeek 返回格式无效，本轮未交付。",
    "validation": "DeepSeek 输出未通过现有校验，本轮未交付。",
    "backend": "DeepSeek 后端失败，本轮未交付。",
}


class ChatSession:
    def __init__(self, *, memory_path=None, offline=False):
        from pathlib import Path
        path = Path(memory_path).expanduser() if memory_path else default_memory_path()
        if path.exists():
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not (isinstance(raw, list) or isinstance(raw, dict) and isinstance(raw.get("sessions"), list)):
                raise ValueError("Invalid memory file; refusing overwrite")
        self.offline = offline
        self.model = llm_deepseek.resolve_model()
        self.backend_error = None
        configure_memory(enabled=True, path=memory_path)
        set_stub_mode(offline)
        set_llm_hook(None if offline else self._generate)
        self.resumed = pipeline.resume_open_session()
        if not self.resumed:
            pipeline._persist_and_reset_session()

    def _generate(self, brief, *, correction=""):
        # articulate catches hook exceptions; retain only a safe code so that its
        # template fallback can never conceal a transport failure at delivery.
        if self.backend_error:
            return None
        try:
            return llm_deepseek.generate_utterance(brief, correction=correction, strict=True)
        except llm_deepseek.DeepSeekUnavailable as exc:
            self.backend_error = BackendUnavailable(str(exc))
        except Exception:
            self.backend_error = BackendUnavailable("backend")
        return None

    def send(self, text, display):
        self.backend_error = None
        signal = None
        if not self.offline:
            signal = sense_input(text, context=pipeline.active_store().snapshot())
            reason = signal.reason if signal is not None else "invalid_output"
            if reason and reason != "low_confidence":
                code = ("quota" if reason == "http_402" else
                        "auth" if reason in ("http_401", "http_403") else
                        "http" if reason.startswith("http_") else
                        "network" if reason == "timeout" else
                        "invalid_output" if reason == "invalid_json" else reason)
                raise BackendUnavailable(code)

        def confirmed(result):
            if self.backend_error:
                raise self.backend_error
            if not self.offline and result.articulate_source != "hook":
                # Raising here prevents fallback templates becoming spoken facts.
                raise BackendUnavailable()
            display(result)

        return pipeline.turn(text, stub=self.offline, input_signal=signal, sense=False, output=confirmed)

    def new(self):
        pipeline._persist_and_reset_session()

    def close(self):
        pipeline.pause_session()


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
        root.geometry("1000x720")
        root.minsize(680, 500)
        root.configure(bg="#edf0ee")
        font = "Microsoft YaHei UI"
        sidebar = tk.Frame(root, bg="#203b38", width=210, padx=22, pady=26)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="●  BIRTH", bg="#203b38", fg="#b9d9cc",
                 font=(font, 10, "bold")).pack(anchor="w")
        tk.Label(sidebar, text="对话之间", bg="#203b38", fg="#ffffff",
                 font=(font, 20, "bold")).pack(anchor="w", pady=(22, 3))
        tk.Label(sidebar, text="给想法一点时间。", bg="#203b38", fg="#a8c4b8",
                 font=(font, 9)).pack(anchor="w")
        tk.Frame(sidebar, bg="#47615a", height=1).pack(fill="x", pady=26)
        tk.Label(sidebar, text="当前空间", bg="#203b38", fg="#9fbcb0",
                 font=(font, 9)).pack(anchor="w")
        tk.Label(sidebar, text="  ●   与你对话", bg="#34534b", fg="#ffffff",
                 font=(font, 10, "bold"), anchor="w", padx=10, pady=12).pack(fill="x", pady=(10, 0))
        bottom = tk.Frame(sidebar, bg="#203b38")
        bottom.pack(side="bottom", fill="x")
        tk.Label(bottom, text="记忆", bg="#203b38", fg="#d8e8df",
                 font=(font, 10, "bold")).pack(anchor="w")
        tk.Label(bottom, text="退出后可继续本场。\n结束本场才写成摘要，不是完整记录。",
                 bg="#203b38", fg="#a8c4b8", justify="left", wraplength=165,
                 font=(font, 9)).pack(anchor="w", pady=(6, 18))
        self.new_button = tk.Button(bottom, text="＋  结束本场 / 新场", command=self.new,
                                    bg="#34534b", fg="white", activebackground="#42665b",
                                    activeforeground="white", relief="flat", anchor="w",
                                    padx=10, pady=9, font=(font, 9), cursor="hand2")
        self.new_button.pack(fill="x")
        tk.Button(bottom, text="保存并退出  ↗", command=self.close, bg="#203b38",
                  fg="#c6ddd2", activebackground="#34534b", activeforeground="white",
                  relief="flat", anchor="w", padx=10, pady=9, font=(font, 9),
                  cursor="hand2").pack(fill="x", pady=(6, 0))

        main = tk.Frame(root, bg="#f7f8f5")
        main.pack(side="left", fill="both", expand=True)
        header = tk.Frame(main, bg="#f7f8f5", padx=30, pady=10)
        header.pack(fill="x")
        tk.Label(header, text="对话", bg="#f7f8f5", fg="#203b38",
                 font=(font, 17, "bold")).pack(anchor="w")
        self.status = tk.StringVar(value="正在打开记忆…")
        tk.Label(header, textvariable=self.status, bg="#f7f8f5", fg="#648078",
                 font=(font, 9), anchor="w", justify="left", wraplength=550).pack(fill="x", pady=(3, 0))
        tk.Frame(main, bg="#e1e8e1", height=1).pack(fill="x")
        conversation = tk.Frame(main, bg="#f7f8f5", padx=30, pady=8)
        self.history = ScrolledText(conversation, wrap="word", state="disabled",
                                    bg="#f7f8f5", fg="#263d38", relief="flat", bd=0,
                                    highlightthickness=0, font=(font, 11), padx=4, pady=4,
                                    spacing1=3, spacing3=4, insertbackground="#203b38")
        self.history.pack(fill="both", expand=True)
        self.history.tag_configure("speaker", foreground="#69857a", font=(font, 9, "bold"), spacing1=15)
        self.history.tag_configure("user", foreground="#2d6e5a", font=(font, 9, "bold"), spacing1=15)
        self.history.tag_configure("message", foreground="#263d38", lmargin1=0, lmargin2=0, spacing3=10)
        self.history.tag_configure("notice", foreground="#71867e", font=(font, 9), spacing1=10, spacing3=10)
        self._append("状态", "欢迎回来。在这里，慢慢说。")

        composer = tk.Frame(main, bg="#f7f8f5", padx=30, pady=8)
        # Reserve the composer first; the transcript receives the remaining height.
        composer.pack(side="bottom", fill="x")
        conversation.pack(fill="both", expand=True)
        card = tk.Frame(composer, bg="white", highlightbackground="#d7e2d9", highlightthickness=1)
        card.pack(fill="x")
        self.entry = tk.Text(card, height=3, wrap="word", font=(font, 11), bg="white",
                             fg="#263d38", insertbackground="#203b38", relief="flat", bd=0,
                             padx=14, pady=6, highlightthickness=0)
        self.entry.pack(fill="x")
        self.entry.bind("<Control-Return>", self.send)
        actions = tk.Frame(card, bg="white", padx=12, pady=9)
        actions.pack(fill="x")
        tk.Label(actions, text="Enter 换行  ·  Ctrl + Enter 发送", bg="white", fg="#8a9c94",
                 font=(font, 9)).pack(side="left")
        self.send_button = tk.Button(actions, text="发送  ↑", command=self.send,
                                     bg="#397a64", fg="white", activebackground="#2c6552",
                                     activeforeground="white", disabledforeground="#b9ccc1",
                                     relief="flat", padx=20, pady=7, font=(font, 10, "bold"),
                                     cursor="hand2")
        self.send_button.pack(side="right")
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._controls()
        root.after(20, self._poll)

        def initialize():
            self.session = ChatSession(memory_path=memory_path, offline=offline)
        self._work("open", initialize)

    def _append(self, speaker, text):
        self.history.configure(state="normal")
        try:
            if speaker == "状态":
                self.history.insert("end", f"{text}\n", "notice")
            else:
                self.history.insert("end", f"{speaker}\n", "user" if speaker == "你" else "speaker")
                self.history.insert("end", f"{text}\n", "message")
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
                self.events.put(("error", kind, exc.code if isinstance(exc, BackendUnavailable) else None))
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
                    message = (BACKEND_MESSAGES[extra]
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
                    if kind == "open" and self.session is not None and getattr(self.session, "resumed", False):
                        for item in pipeline.active_store().session_turns():
                            self._append("你", item["user_text"])
                            self._append("对方" if not self.offline else "离线模板（非真实模型）", item["utterance"])
                        self._append("状态", "已继续上场。")
                    if kind == "new":
                        self._append("状态", "本场已保存，已开始新场。")
                    source = ("离线模板验证，未请求模型" if self.offline else
                              "DeepSeek · 输入理解已启用；失败不会交付模板")
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
            self.status.set("正在回应… 可移动窗口；退出后可继续本场。")
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
