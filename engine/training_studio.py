# -*- coding: utf-8 -*-
"""训练台（桌面 UI）：实时看着它一轮一轮地长。

用户的要求（逐字）
────────────────────────────────────────────────────────────
> 「首先是现在我们正在做的进程，实施逐轮。然后就是之后给系统做家教时的
>   教学情况也提前做好，方便到那一个阶段好用。」
> 历史要求：「能：暂停/继续训练、批准或驳回管理员的建议、标『这轮判错了』」
> D-028：删除未接执行器的批量批准／驳回入口，保留观察与历史。
> 「要 .exe 的，有 UI 交互」
> 「感觉有点简陋。没有用的欲望，而且还可能降低效率」   ← v2 全部在回应这句

v2 改了什么（针对"简陋／没用的欲望／降低效率"）
────────────────────────────────────────────────────────────
    简陋 → **卡片式直播流**：每一轮是一张卡，左侧彩条标状态，
           训练师／它回／内部读数／管理员判，四层分明；不再是纯文本日志。
    没欲望 → **顶栏进度条 + 大字号统计卡 + 彩色状态点**，一眼看得出在跑还是停了。
    降效率 → 三处实测会拖慢的：
             ① tkinter 的 Text 控件**行数越多越卡** → 直播流**只留最近 N 轮**，旧的自动丢
             ② 刷屏 → **过滤器**（全部／只看有问题／只看越界）＋ **自动滚动开关**
             ③ 内部读数每轮都占四行 → 收成**一行小标签**，需要时再展开

⚠️ 线程纪律（本文件唯一容易出错的地方）
    训练跑在**后台线程**，tkinter 只能在**主线程**碰界面。
    训练线程只往 `queue.Queue` 丢记录，主线程用 `after()` 取。
    **绝不从训练线程直接改控件** —— 那会随机崩，而且崩得没法复现。

⚠️ 不用任何第三方 UI 库：tkinter 是标准库自带的，打包出来的 exe 最干净。
   代价是 tkinter 的控件外观有上限 —— 下面用**自绘卡片**（Frame + 色条 + 内边距）
   把这个上限尽量顶满，但不假装它能做到网页那种程度。
"""
from __future__ import annotations

import io
import json
import os
import queue
import crashguard as CRASH      # ★ T23 崩溃黑匣子（三处钩子 + 环形落盘）
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, ttk

_HERE = os.path.dirname(os.path.abspath(__file__))

# ★ 打包成 exe 之后的第一步，**必须在导入任何引擎模块之前**：
#   `__file__` 会指向 PyInstaller 解包出来的临时目录，于是 rules/corpus 找不到，
#   而且**台账会写进临时目录、一退出就没**。
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(os.path.abspath(sys.executable))
    for _cand in (os.environ.get("EGO_ROOT"), _exe_dir, os.path.dirname(_exe_dir)):
        if _cand and os.path.isdir(os.path.join(_cand, "rules")):
            os.environ["EGO_ROOT"] = _cand
            break

_ROOT = os.environ.get("EGO_ROOT") or os.path.dirname(_HERE)
for _p in (_ROOT, _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TRAIN_DIR = os.path.join(_ROOT, "state", "train")
QUEUE_FILE = os.path.join(TRAIN_DIR, "review_queue.json")
MISJUDGED = os.path.join(TRAIN_DIR, "misjudged.jsonl")

# ---------------------------------------------------------------- 视觉

BG = "#0b0d12"          # 更深，卡片才浮得起来
CARD = "#161a22"
CARD2 = "#1c212b"
LINE = "#252b36"
FG = "#e8ecf2"
DIM = "#8792a2"
FAINT = "#5a6472"
OK = "#4ade80"
WARN = "#fbbf24"
BAD = "#f87171"
ACC = "#60a5fa"
VIOLET = "#a78bfa"

F_UI = "Microsoft YaHei UI"
F_NUM = "Consolas"

# ★ DPI 缩放因子。由 `_make_dpi_aware()` 在建窗口**之前**设定。
#   为什么需要（实测）：用户屏幕 2560×1440、Windows 缩放 150%（AppliedDPI=144）。
#   Python/tkinter 默认**不声明 DPI 感知**，于是系统把窗口按 1707×960 渲染，
#   再**位图拉伸 1.5 倍**铺满屏幕 —— 每个字都是插值放大的，所以糊。
#   声明感知之后，tkinter 直接拿到 2560×1440 和真实 DPI=144，字就是原生渲染。
SC = 1.0


def _make_dpi_aware() -> float:
    """声明本进程 DPI 感知，并返回缩放因子（1.0 = 100%）。

    ⚠️ **必须在 `tk.Tk()` 之前调用。** 建了窗口再声明是无效的。

    三级回退，对应不同 Windows 版本：
      SetProcessDpiAwarenessContext(-4)  PER_MONITOR_AWARE_V2（Win10 1703+，最好）
      shcore.SetProcessDpiAwareness(2)   每显示器感知（Win8.1+）
      user32.SetProcessDPIAware()        系统感知（老系统）
    三级都失败就返回 1.0 —— **不装作成功**，字会糊但程序照跑。
    """
    import ctypes
    u = ctypes.windll.user32
    g = ctypes.windll.gdi32
    ok = False
    try:
        # ⚠️ 必须显式声明类型：DPI_AWARENESS_CONTEXT 是**句柄**（64 位），
        #    ctypes 默认按 32 位 int 传，-4 会被截断/符号扩展错。
        f = u.SetProcessDpiAwarenessContext
        f.argtypes = [ctypes.c_void_p]
        f.restype = ctypes.c_bool
        ok = bool(f(ctypes.c_void_p(-4)))          # PER_MONITOR_AWARE_V2
    except Exception:                              # noqa: BLE001
        try:
            ok = ctypes.windll.shcore.SetProcessDpiAwareness(2) == 0
        except Exception:                          # noqa: BLE001
            try:
                ok = bool(ctypes.windll.user32.SetProcessDPIAware())
            except Exception:                      # noqa: BLE001
                ok = False
    try:
        # ⚠️⚠️ 这里踩过一个坑，记下来免得重犯：
        #    `GetDC` 返回的是 **64 位句柄**，而 ctypes 默认 restype 是 c_int（32 位），
        #    句柄会被**截断** → `GetDeviceCaps` 拿到的是垃圾（实测返回 96 而不是 144）。
        #    后果是：DPI 感知**声明成功了**，但缩放因子算成 1.0，
        #    整个修复静默失效 —— 而且它不报错，只是数不对。**最难查的那种。**
        u.GetDC.restype = ctypes.c_void_p
        u.GetDC.argtypes = [ctypes.c_void_p]
        u.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        g.GetDeviceCaps.restype = ctypes.c_int
        g.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
        hdc = u.GetDC(None)
        dpi = g.GetDeviceCaps(hdc, 88)             # LOGPIXELSX
        u.ReleaseDC(None, hdc)
        return max(1.0, (dpi or 96) / 96.0)
    except Exception:                              # noqa: BLE001
        return 1.5 if ok else 1.0


def px(n: float) -> int:
    """把设计稿上的像素值换算到当前 DPI。**固定像素值必须过这一道**，
    否则窗口放大了、里边的东西还是老尺寸，看着就是"没对齐"。"""
    return max(1, int(round(n * SC)))


# ---------------------------------------------------------------- 视觉规格（第一期）
#
# ⚠️ 这一节**只定义外观常量与样式函数**，不含任何行为。
#    它的全部作用域是"像素长什么样"：颜色、字号、间距、控件样式。
#    按需求铁律：不碰 handler、不碰状态、不新增写入。

# 字号层级（pt）。层级之间至少差 1pt，肉眼才分得出主次。
F_TITLE = 15      # 应用名
F_H2 = 11         # 面板标题（管理员 / 任务 / 历史 / 它长到哪了）
F_BODY = 10       # 正文（直播流、按钮）
F_SUB = 9         # 次要（标签、说明）
F_MICRO = 8       # 最弱（历史记录、编号）
F_MID = 13        # 中号数字（可审计率）
F_BIG = 18        # 大号数字（发展水平）

# 间距刻度（px，会过 px() 换算）。统一用它，不再散落魔法数字。
SP1, SP2, SP3, SP4 = 4, 8, 12, 16


def _setup_styles(root) -> None:
    """深色 ttk 样式。

    ⚠️ 为什么必须做：ttk 的 Progressbar / Scrollbar 默认走 Windows 原生主题，
       在深色界面上是**一条刺眼的白色**（用户第一条就点了这个）。
       改用 `clam` 主题 —— 它是 ttk 自带的，**允许逐项配置颜色**；
       原生 `vista` 主题的颜色是系统画死的，改不了。

    这是纯外观改动：只改绘制，不改任何控件的取值、命令、事件绑定。
    """
    try:
        st = ttk.Style(root)
        if "clam" in st.theme_names():
            st.theme_use("clam")
        # 进度条
        st.configure("Dark.Horizontal.TProgressbar",
                     troughcolor=CARD2, background=ACC, bordercolor=CARD2,
                     lightcolor=ACC, darkcolor=ACC, thickness=px(8),
                     borderwidth=0, relief="flat")
        st.map("Dark.Horizontal.TProgressbar",
               background=[("disabled", LINE), ("!disabled", ACC)])
        # 纵向滚动条（直播流右侧）
        for orient in ("Vertical", "Horizontal"):
            st.configure("Dark.%s.TScrollbar" % orient,
                         troughcolor=BG, background=LINE, bordercolor=BG,
                         arrowcolor=DIM, lightcolor=LINE, darkcolor=LINE,
                         borderwidth=0, arrowsize=px(12), relief="flat")
            st.map("Dark.%s.TScrollbar" % orient,
                   background=[("active", FAINT), ("!active", LINE)],
                   arrowcolor=[("active", FG), ("!active", DIM)])
    except Exception:                              # noqa: BLE001
        # 样式失败**不许影响程序**：顶多是进度条还是白的。
        # 而且不写盘、不弹窗 —— 悄悄降级，训练照常。
        pass

PROBLEM_CN = {
    "none": "没问题", "off_topic": "答非所问", "mechanical": "太机械",
    "boundary": "越界", "too_little": "说少了", "too_much": "说多了",
    "fabricated": "编造",
}
PROBLEM_COLOR = {
    "none": OK, "off_topic": WARN, "mechanical": WARN,
    "boundary": BAD, "fabricated": BAD, "too_little": ACC, "too_much": ACC,
}

MAX_CARDS = 60          # 直播流最多保留多少张卡（tkinter 行数多了会卡）


def _blend(c1: str, c2: str, k: float) -> str:
    """按比例把 c1 混向 c2（k=0 → c1，k=1 → c2）。算不出来就返回 c1。"""
    try:
        a = c1.lstrip("#")
        b = c2.lstrip("#")
        return "#" + "".join(
            "%02x" % max(0, min(255, int(int(a[i:i + 2], 16) * (1 - k)
                                         + int(b[i:i + 2], 16) * k)))
            for i in (0, 2, 4))
    except Exception:                              # noqa: BLE001
        return c1


def _dim(hex_color: str, toward: str = BG, k: float = 0.45) -> str:
    """把一个颜色朝背景色混 `k`，得到**同一色系的弱化版**。

    用途：历史记录要"视觉权重低于任务"。
    直接换成灰色会丢掉颜色所带的分类信息（绿=训练、蓝=批准…），
    所以这里**保色相、降鲜明度** —— 一眼还分得清类别，但不抢任务的注意力。
    """
    return _blend(hex_color, toward, k)


def _describe_exc(e: BaseException) -> str:
    """把异常描述成**一眼能定位**的一段话。

    ⚠️ 为什么必须做：实测训练在 exe 里一启动就失败，界面只显示
       `FileNotFoundError(2, 'No such file or directory')` —— **没说是哪个文件**，
       拿着这句话完全无从下手。一个真 bug 因此查了半天。
       `repr(e)` 只给 args；**文件名在 `e.filename` 和 `str(e)` 里**。

    纯显示：只把异常描述得更清楚，不改变捕获、不改变处理流程、不吞不重抛。
    """
    try:
        parts = ["%s: %s" % (type(e).__name__, e)]
        fn = getattr(e, "filename", None)
        if fn:
            parts.append("文件：%s" % fn)
        import traceback
        tb = traceback.extract_tb(e.__traceback__)
        if tb:
            last = tb[-1]
            parts.append("位置：%s:%d（%s）"
                         % (os.path.basename(last.filename), last.lineno, last.name))
            # 再往上两帧，好看出是"谁调用了它"
            chain = " ← ".join("%s:%d(%s)" % (os.path.basename(f.filename), f.lineno, f.name)
                               for f in tb[-4:-1])
            if chain:
                parts.append("调用链：%s" % chain)
        return "\n".join(parts)
    except Exception:                              # noqa: BLE001
        # ⚠️ 兜底本身也必须兜底。
        #   原来直接 `return repr(e)[:200]` —— 如果这个异常的 `__repr__` 自己抛，
        #   异常就从 `_describe_exc` 冒出去，冒过 `work()` 的 except，
        #   工作线程静默死掉，而 `q.put` 永远执行不到 —— **界面停在"训练中"**。
        #   实测：注入一个 `__repr__` 与 `__str__` 都抛的异常，确实漏出去。
        #   所以这里再包一层，保证**无论如何都返回一个字符串**。
        #   纯内存、无文件读写、无网络、无阻塞。
        try:
            return repr(e)[:200]
        except Exception:                          # noqa: BLE001
            return "（这个异常连描述都取不到）"


def _explain_error(raw: str) -> tuple[str, str]:
    """把异常字符串翻成**人话的第一段和第三段**。返回 (发生了什么, 可以怎么办)。

    ★ 用户要求（第二期④）：
      · **只改显示文案，不改异常捕获与处理流程** —— 所以这里只接收一个字符串，
        不 catch、不 re-raise、不改变任何控制流。
      · 用关键词做简单映射，匹配不上就回落通用模板。
      · `repr(e)` 太技术，只放进"查看详情"。

    ⚠️ **"影响"那一段不在这里** —— 影响取决于**在哪一步出的错**，
       而这一层只看得见一个字符串，判断不了。硬写就是编。
       影响由调用方按它**确知的上下文**传进来（见 `_show_alert(impact=...)`）。
    """
    s = (raw or "").lower()
    if "timed out" in s or "timeout" in s:
        return ("等太久没有回应（超时）",
                "检查网络；稍等片刻重试。偶发超时重试通常就好。")
    if any(k in s for k in ("getaddrinfo", "connection", "unreachable",
                            "network", "ssl", "proxy")):
        return ("网络连不上",
                "确认网络可用；若用了代理或 VPN，检查它是否在拦请求。")
    if any(k in s for k in ("401", "403", "unauthor", "invalid api key",
                            "authentication", "permission")):
        return ("密钥不被接受（认证失败）",
                "检查密钥是否过期或被撤销。密钥在 ~/.dsh/.credentials.yaml。")
    if any(k in s for k in ("429", "rate limit", "quota", "insufficient",
                            "balance")):
        return ("被限流或额度不足",
                "等一会儿再试；若是额度问题，需要充值后才能继续。")
    if any(k in s for k in ("json", "expecting value", "decode")):
        return ("模型返回的内容格式不对",
                "重试一次通常就好；反复出现请把下面的详情发我。")
    return ("出错了（未识别的类型）", "把下面的详情发我，我来判断。")


def _card(parent, padx=None, pady=None, bg=CARD):
    """自绘卡片：tkinter 没有圆角，就用细边框 + 内边距做出层次。"""
    f = tk.Frame(parent, bg=bg, highlightthickness=1,
                 highlightbackground=LINE, highlightcolor=LINE)
    f.pack(fill="x", pady=px(5))
    inner = tk.Frame(f, bg=bg, padx=padx if padx is not None else px(14),
                     pady=pady if pady is not None else px(10))
    inner.pack(fill="x")
    return inner


def _chip(parent, text, color, bg=None):
    """彩色小标签。用它代替纯文字，一眼分得清状态。"""
    lb = tk.Label(parent, text=text, bg=bg or CARD2, fg=color,
                  font=(F_UI, F_SUB), padx=px(SP2), pady=1)
    lb.pack(side="left", padx=(0, px(SP2)))
    return lb


def desktop_training_gate():
    """Desktop defaults ON after D-027; explicit environment OFF still wins."""
    from pipeline import _gate_on
    return _gate_on(True if "EGO_GATE_PERCEPTION" not in os.environ else None)


class Studio:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.q: queue.Queue = queue.Queue()
        self.control = None
        self.worker: threading.Thread | None = None
        #: ★ T23 运行标志。`_set_state` 只改标签文字、**不存状态**，
        #:   所以看门狗需要一个真正的布尔锚。初值 False = 没在跑。
        self._running: bool = False
        self.cards: list[tk.Frame] = []
        self.turns: list[dict] = []
        self.counts = {"turns": 0, "auditable": 0, "problems": {}, "flagged": 0}
        self.total_target = 0
        self.total_rounds = 0
        self.cur_round = 0
        self.filter = tk.StringVar(value="all")
        self.autoscroll = tk.BooleanVar(value=True)
        # ★ 第三期：动画开关（默认开）。关掉后所有功能与显示正常 ——
        #   `_fade` 开头就判它，为假时直接落到终值，不排任何 after。
        self.anim_on = tk.BooleanVar(value=True)
        # 动画自己的 after 句柄，**与 _drain 的轮询链完全分开**（用户限制第③条）
        self._anim_handles: list = []

        # ★ 改动 3：窗口标题带上项目名 —— 任务栏与 Alt-Tab 里也能一眼分辨，
        #   不必先把窗口切到前台。
        root.title("训练台 · 当前项目：%s"
                   % (os.path.basename(_ROOT.rstrip("\\/")) or _ROOT))
        root.configure(bg=BG)
        root.geometry("%dx%d" % (px(1280), px(800)))
        root.minsize(px(1080), px(680))
        self._build()
        # ★ T33 只读显示：启动即读一次 state/devlevel.json。
        #   **不是定时器** —— 就这么一次，之后只在 _drain 收到 _done 时再读。
        self._refresh_devlevel_file()

    # ------------------------------------------------------------ 骨架

    def _build(self) -> None:
        self._build_toolbar()

        # ★ 改动 1 + 3（用户批准）：项目标识行，**紧贴顶栏、body 之前**。
        #
        #   为什么必须在这：这一行是**唯一**能告诉你"这次训练写进哪个目录"的东西。
        #   实测教训：真实项目与验收副本的两个 exe 字节完全相同，肉眼无法区分，
        #   结果在副本里点开、数据却写进了真实项目 —— 因为当时这一行
        #   被排在窗口最下面、被内容挤出可视区，看不见。
        #   所以它必须在**按开始之前**就在视野里，而且要显眼。
        self.proj_bar = tk.Frame(self.root, bg=BG, padx=px(SP4))
        self.proj_bar.pack(fill="x", pady=(px(SP1), 0))
        # 项目名：大一号、亮色、带底色 —— 一眼可辨
        self.proj_name = tk.Label(self.proj_bar, bg=CARD2, fg=WARN,
                                  font=(F_UI, F_BODY, "bold"),
                                  padx=px(SP2), pady=px(2))
        self.proj_name.pack(side="left")
        # 完整路径：小字灰色，供核对
        self.proj_path = tk.Label(self.proj_bar, bg=BG, fg=FAINT,
                                  font=(F_UI, F_SUB))
        self.proj_path.pack(side="left", padx=(px(SP3), 0))
        self._refresh_proj()

        body = tk.Frame(self.root, bg=BG)
        self.body = body
        body.pack(fill="both", expand=True, padx=px(SP4), pady=(0, px(SP3)))

        # ★「本次将开始什么」—— **常驻一行**，不藏在按钮后面。
        #   用户原话：「我点开始训练，将开始的是什么任务……我希望这些在软件里
        #             都能一目了然。」
        #   所以它跟着"训练轮/每场轮数"两个输入实时变，按按钮之前就知道要发生什么。
        self.lbl_plan = tk.Label(self.root, bg=BG, fg=ACC, anchor="w",
                                 font=(F_UI, F_BODY), justify="left",
                                 wraplength=px(1180))
        self.lbl_plan.pack(fill="x", padx=px(SP4), pady=(px(SP1), 0))
        for v in (self.var_rounds, self.var_len):
            v.trace_add("write", lambda *_: self._refresh_plan())
        self._refresh_plan()

        # 左：直播流
        left = tk.Frame(body, bg=BG)
        left.pack(side="left", fill="both", expand=True)
        self._build_filters(left)
        self._build_feed(left)

        # 右：状态栏。**四个面板会超出一屏，所以右栏自己也能滚。**
        outer = tk.Frame(body, bg=BG, width=px(372))
        outer.pack(side="right", fill="y", padx=(px(SP4), 0))
        outer.pack_propagate(False)
        rc = tk.Canvas(outer, bg=BG, highlightthickness=0, width=px(356))
        rsb = ttk.Scrollbar(outer, orient="vertical", command=rc.yview,
                            style="Dark.Vertical.TScrollbar")
        rc.configure(yscrollcommand=rsb.set)
        rsb.pack(side="right", fill="y")
        rc.pack(side="left", fill="both", expand=True)
        right = tk.Frame(rc, bg=BG)
        rc.create_window((0, 0), window=right, anchor="nw", width=px(350))
        right.bind("<Configure>", lambda e: rc.configure(scrollregion=rc.bbox("all")))
        self._right_canvas = rc

        # ★ 第二期③：右侧三级权重（用户要求）
        #   一级 当前进度与任务  >  二级 本批数据  >  三级 历史操作
        #   排序与字号/颜色一起做，光排序不改视觉权重也分不出主次。
        self._build_stats(right)      # 一级：它长到哪了
        self._build_tasks(right)      # 一级：任务
        self._build_counts(right)     # 二级：这一批的数字
        self._build_history(right)    # 三级：历史操作（已弱化）
        self._build_admin(right)      # 操作面板（不在这三级里）
        self._build_pending(right)    # ★ 第 4 步：待批申请（右栏最下，平时静默）

        # ★ 数据自检（第 5c 条）。
        #   **必须放在 body 建好之后** —— 它要调 `_show_alert`，而后者用
        #   `before=self.body` 定位；放在 `_build_toolbar` 里会因 body 还不存在
        #   而静默失败（异常被吞），告警条根本不出现。
        self._selfcheck_dirs()


    def _build_toolbar(self) -> None:
        bar = tk.Frame(self.root, bg=BG, padx=px(SP4), pady=px(SP3))
        bar.pack(fill="x")

        tk.Label(bar, text="训练台", bg=BG, fg=FG,
                 font=(F_UI, F_TITLE, "bold")).pack(side="left")
        tk.Label(bar, text="自我的发展", bg=BG, fg=FAINT,
                 font=(F_UI, F_BODY)).pack(side="left", padx=(px(SP2), 20))

        self.dot = tk.Canvas(bar, width=px(11), height=px(11), bg=BG,
                             highlightthickness=0)
        self.dot.pack(side="left")
        self._dot_id = self.dot.create_oval(1, 1, px(10), px(10), fill=FAINT, outline="")
        self.lbl_state = tk.Label(bar, text="待命", bg=BG, fg=DIM,
                                  font=(F_UI, F_BODY))
        self.lbl_state.pack(side="left", padx=(px(SP2), px(SP4)))

        self.btn_start = self._btn(bar, "▶  开始训练", self.on_start, OK)
        self.btn_pause = self._btn(bar, "⏸  暂停", self.on_pause, WARN)
        self.btn_resume = self._btn(bar, "▶  继续", self.on_resume, ACC)
        self.btn_stop = self._btn(bar, "⏹  停止", self.on_stop, BAD)
        for b in (self.btn_pause, self.btn_resume, self.btn_stop):
            b.config(state="disabled")
        # 家教那一页的要求（用户原话：「之后给系统做家教时的教学情况也提前做好」）
        # 不能因为改版就丢掉。做成按钮弹窗：主界面保持干净，但那一页的内容还在。
        self._btn(bar, "家教", self.show_tutor_plan, VIOLET)   # T24-A 转正（文案变更，已批准）

        # 参数 + 进度放右侧。
        #
        # ★ 第一期修复：**标签跑到输入框右边了。**
        #   `pack(side="right")` 的规矩是"先 pack 的在最右"，所以原来
        #   先 pack 标签、后 pack 输入框 → 视觉成了 `[4] 训练轮`（标签在右）。
        #   现在改成**先 pack 输入框、再 pack 标签** → 视觉是 `训练轮 [4]`。
        #   这是纯粹的 pack 次序调整，不碰任何取值与命令。
        self.var_len = tk.StringVar(value="2")
        self._entry(bar, self.var_len).pack(side="right")
        tk.Label(bar, text="每场轮数", bg=BG, fg=DIM,
                 font=(F_UI, F_SUB)).pack(side="right", padx=(px(10), px(4)))
        self.var_rounds = tk.StringVar(value="1")
        self._entry(bar, self.var_rounds).pack(side="right")
        tk.Label(bar, text="训练轮", bg=BG, fg=DIM,
                 font=(F_UI, F_SUB)).pack(side="right", padx=(px(10), px(4)))

        self.pbar = ttk.Progressbar(bar, length=px(170), mode="determinate",
                                    maximum=100,
                                    style="Dark.Horizontal.TProgressbar")
        self.pbar.pack(side="right", padx=(0, px(6)))
        # ★ 第一期修复：原来这里只显示「12 / 120」，**没说这两个数是什么**。
        #   现在补上清楚的话：前半是已完成轮数，后半是这一批的目标轮数。
        #   同时把两个数分开着色 —— 一眼看得出哪个在动。
        self.lbl_prog = tk.Label(bar, text="", bg=BG, fg=DIM,
                                 font=(F_UI, F_SUB))
        self.lbl_prog.pack(side="right", padx=(0, px(8)))


        # ★ 告警条。
        #   为什么需要：打包成**窗口版 exe** 之后 `print()` 的消息**哪儿都看不见**。
        #   于是"训练师要 API、当前不可用 → 退回固定语料"这种事会被吞掉，
        #   用户看到的是"它在正常跑" —— 而那是**最难查的一类失败：看起来在跑，其实变了样**。
        #   所以：一切"它在正常跑吗"以外的坏消息，都必须在这条上出现。
        self.alert = tk.Frame(self.root, bg="#3a1d1d", padx=px(SP4), pady=px(SP2))
        self.lbl_alert = tk.Label(self.alert, bg="#3a1d1d", fg="#ffb4b4",
                                  font=(F_UI, F_BODY), justify="left", anchor="w")
        self.lbl_alert.pack(fill="x")
        # 初始不显示；有话说时才 pack

    def _refresh_proj(self) -> None:
        """刷新顶栏下的项目标识。**纯显示，只读 _ROOT。**"""
        try:
            name = os.path.basename(_ROOT.rstrip("\\/")) or _ROOT
            self.proj_name.config(text="当前项目：%s" % name)
            self.proj_path.config(
                text="项目根 %s%s"
                     % (_ROOT, "（exe 模式）" if getattr(sys, "frozen", False) else "（源码模式）"))
        except Exception:                          # noqa: BLE001
            pass

    def _selfcheck_dirs(self) -> None:
        """开跑前就能查出来的问题：必需的目录在不在。

        ★ 第 5c 条（用户要求）：exe 旁边需要的 rules / corpus 位置不对时，
          **给出明确报错，而不是崩溃退出**。
          训练中途才发现的错误由 `_show_alert` 的三段式负责
          （那里现在会带上文件名和出错位置）。
        """
        try:
            need = ["rules", "corpus", "state"]
            miss = [d for d in need if not os.path.isdir(os.path.join(_ROOT, d))]
            self._missing_dirs = miss
            if miss:
                self._show_alert(
                    "缺少必需的目录，训练无法开始",
                    what="找不到必需的目录",
                    impact="训练**不会启动**。缺的是：%s" % "、".join(miss),
                    raw="项目根（EGO_ROOT）= %s\n"
                        "exe 模式：请确认 rules\\ 与 corpus\\ 就在这个目录里（与 exe 同级）。\n"
                        "源码模式：请在项目根目录下运行。" % _ROOT)
                # "可以怎么办"也说真话：这条错误的原因已经查明了，
                # 不该沿用"把详情发我，我来判断"那种未识别时的兜底话术。
                self.lbl_alert.configure(text=self.lbl_alert.cget("text").replace(
                    "【可以怎么办】把下面的详情发我，我来判断。",
                    "【可以怎么办】把 rules\\ 和 corpus\\ 放到上面那个项目根目录里，再重开。\n"
                    "　　　　　　　（源码模式：在项目根目录下运行即可。）"))
            else:
                # 目录齐全 —— 顶栏那行已经在显示项目根，这里只把它刷新成正常色。
                self._refresh_proj()
        except Exception:                          # noqa: BLE001
            self._missing_dirs = []                # 自检本身出错就当没缺，别拦人

    def _show_alert(self, text: str, danger: bool = True,
                    impact: str | None = None, raw: str | None = None,
                    what: str | None = None) -> None:
        """告警条。三段式（第二期④）：发生了什么 / 影响 / 可以怎么办，外加查看详情。

        ★ 用户给的两条硬约束：
          ① **"影响"那一段必须是真的。** 拿不准的宁可写"请查看详情"，
             也不要写一个可能不准的结论 —— 那会误导用户判断数据有没有丢。
             所以 `impact` **由调用方按它确知的上下文传入**；
             传不进来就不写结论。
          ② `repr(e)` 只放进「查看详情」，第一段用通俗的一句话。

        全过程包异常：告警画不出来**不许影响训练**（铁律第 5 条）。
        """
        try:
            # `what` 显式给了就用它 —— **已知的情况不许被翻成"未识别的类型"**。
            #   只有"从一个异常字符串反推原因"时才走关键词映射。
            _what, action = _explain_error(raw if raw is not None else text)
            what = what or _what
            # ① 如果调用方没给 impact，就说"不确定"，**不编**
            imp = impact or "不确定：可能不影响记录，也可能整轮被跳过。请以台账为准。"
            lines = ["【发生了什么】%s" % what]
            lines.append("【影响】%s" % imp)
            lines.append("【可以怎么办】%s" % action)
            if raw:
                lines.append("【查看详情】%s" % raw)
            bg, fg = ("#3a1d1d", "#ffb4b4") if danger else ("#3a2f12", "#ffe08a")
            self.alert.configure(bg=bg)
            self.lbl_alert.configure(bg=bg, fg=fg, text="\n".join(lines))
            # ⚠️ 用 `before=` 定位，不要用 `after=winfo_children()[i]` ——
            #    pack 的次序是**调用次序**不是创建次序，按索引抓控件会抓到没 pack 的，
            #    直接抛 TclError（实测就是这么崩的）。
            if not self.alert.winfo_ismapped():
                self.alert.pack(fill="x", padx=px(SP4), pady=(px(SP2), 0),
                                before=self.body)
        except Exception:                          # noqa: BLE001
            pass                                   # 告警本身出错，静默降级

    def _hide_alert(self) -> None:
        self.alert.pack_forget()

    def _build_filters(self, parent) -> None:
        # ★ 第二期①：状态横幅。
        #   要求：「在'直播流'上方加一条状态横幅，只读现有状态：
        #          待命 / 训练中（当前任务）/ 暂停 / 完成。
        #          **不得替换或遮挡直播流本身**。」
        #   所以：它是**独立的一条**，pack 在直播流标签之上；数据全部来自
        #   既有的 `_set_state()` 与轮次计数 —— **只读，不新增任何状态**。
        self.banner = tk.Frame(parent, bg=CARD, highlightthickness=1,
                               highlightbackground=LINE)
        self.banner.pack(fill="x", pady=(px(SP3), px(SP2)))
        binner = tk.Frame(self.banner, bg=CARD, padx=px(SP3), pady=px(SP2))
        binner.pack(fill="x")
        self.banner_dot = tk.Label(binner, text="●", bg=CARD, fg=FAINT,
                                   font=(F_UI, F_BODY))
        self.banner_dot.pack(side="left")
        self.banner_main = tk.Label(binner, text="待命", bg=CARD, fg=DIM,
                                    font=(F_UI, F_BODY, "bold"))
        self.banner_main.pack(side="left", padx=(px(SP1), px(SP2)))
        self.banner_sub = tk.Label(binner, text="还没有开始训练", bg=CARD,
                                   fg=FAINT, font=(F_UI, F_SUB))
        self.banner_sub.pack(side="left")

        bar = tk.Frame(parent, bg=BG)
        bar.pack(fill="x", pady=(px(SP1), px(SP2)))
        tk.Label(bar, text="直播流", bg=BG, fg=FG,
                 font=(F_UI, F_H2, "bold")).pack(side="left")
        tk.Label(bar, text="（只留最近 %d 轮，防止越跑越卡）" % MAX_CARDS,
                 bg=BG, fg=FAINT, font=(F_UI, F_SUB)).pack(side="left", padx=(px(SP2), px(SP4)))
        for text, val in (("全部", "all"), ("只看有问题", "issue"),
                          ("只看越界/编造", "bad")):
            tk.Radiobutton(bar, text=text, value=val, variable=self.filter,
                           command=self._reapply_filter, bg=BG, fg=DIM,
                           selectcolor=CARD, activebackground=BG,
                           activeforeground=FG, font=(F_UI, F_SUB),
                           highlightthickness=0, bd=0).pack(side="left", padx=px(SP1))
        tk.Checkbutton(bar, text="动画", variable=self.anim_on,
                       bg=BG, fg=DIM, selectcolor=CARD, activebackground=BG,
                       activeforeground=FG, font=(F_UI, F_SUB),
                       highlightthickness=0, bd=0).pack(side="right", padx=(0, px(SP2)))
        tk.Checkbutton(bar, text="自动滚动", variable=self.autoscroll,
                       bg=BG, fg=DIM, selectcolor=CARD, activebackground=BG,
                       activeforeground=FG, font=(F_UI, F_SUB),
                       highlightthickness=0, bd=0).pack(side="right")
        self.lbl_filter = tk.Label(bar, text="", bg=BG, fg=FAINT,
                                   font=(F_UI, F_SUB))
        self.lbl_filter.pack(side="right", padx=px(SP3))

    def _build_feed(self, parent) -> None:
        wrap = tk.Frame(parent, bg=BG)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview,
                           style="Dark.Vertical.TScrollbar")
        self.canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.feed = tk.Frame(self.canvas, bg=BG)
        self._win = self.canvas.create_window((0, 0), window=self.feed,
                                              anchor="nw")
        self.feed.bind("<Configure>", lambda e: self.canvas.configure(
            scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfig(
            self._win, width=e.width))
        # 鼠标滚轮
        for w in (self.canvas, self.feed):
            w.bind_all("<MouseWheel>", self._wheel)

    def _build_stats(self, parent) -> None:
        """一级权重：**当前进度**。字号最大、颜色最亮。"""
        box = tk.Frame(parent, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE, padx=px(SP3), pady=px(SP3))
        box.pack(fill="x")
        tk.Label(box, text="它长到哪了", bg=CARD, fg=ACC,
                 font=(F_UI, F_H2, "bold")).pack(anchor="w")
        self.lbl_level = tk.Label(box, text="—", bg=CARD, fg=FG,
                                  font=(F_UI, F_BIG, "bold"))
        self.lbl_level.pack(anchor="w", pady=(px(SP1), 0))
        self.lbl_devsub = tk.Label(box, text="尚未开始", bg=CARD, fg=DIM,
                                   font=(F_UI, F_SUB), justify="left")
        self.lbl_devsub.pack(anchor="w")
        self.lbl_rules = tk.Label(box, text="", bg=CARD, fg=VIOLET,
                                  font=(F_UI, F_SUB), justify="left")
        self.lbl_rules.pack(anchor="w", pady=(px(SP2), 0))
        self.lbl_reads = tk.Label(box, text="", bg=CARD, fg=DIM,
                                  font=(F_NUM, F_SUB), justify="left")
        self.lbl_reads.pack(anchor="w", pady=(px(SP2), 0))

    def _build_counts(self, parent) -> None:
        """二级权重：**本批数据**。比一级小一号、暗一档 ——
        它回答的是"这一批跑得怎么样"，不是"它长到哪了"。"""
        n = tk.Frame(parent, bg=CARD, highlightthickness=1,
                     highlightbackground=LINE, padx=px(SP3), pady=px(SP2))
        n.pack(fill="x", pady=(px(SP2), 0))
        tk.Label(n, text="这一批的数字", bg=CARD, fg=_dim(ACC),
                 font=(F_UI, F_SUB, "bold")).pack(anchor="w")
        self.lbl_rate = tk.Label(n, text="—", bg=CARD, fg=FG,
                                 font=(F_UI, F_MID, "bold"))
        self.lbl_rate.pack(anchor="w", pady=(px(SP1), 0))
        self.lbl_rate_sub = tk.Label(n, text="管理员可审计", bg=CARD, fg=FAINT,
                                     font=(F_UI, F_MICRO))
        self.lbl_rate_sub.pack(anchor="w")
        self.prob_frame = tk.Frame(n, bg=CARD)
        self.prob_frame.pack(fill="x", pady=(px(SP2), 0))

    def _build_tasks(self, parent) -> None:
        box = tk.Frame(parent, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE, padx=px(SP3), pady=px(SP3))
        box.pack(fill="x", pady=(px(SP3), 0))
        hdr = tk.Frame(box, bg=CARD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="任务", bg=CARD, fg=ACC,
                 font=(F_UI, F_H2, "bold")).pack(side="left")
        self.only_pending = tk.BooleanVar(value=True)
        tk.Checkbutton(hdr, text="只看未完成", variable=self.only_pending,
                       command=self._refresh_tasks, bg=CARD, fg=DIM,
                       selectcolor=CARD2, activebackground=CARD,
                       activeforeground=FG, font=(F_UI, F_SUB),
                       highlightthickness=0, bd=0).pack(side="right")
        self.task_frame = tk.Frame(box, bg=CARD)
        self.task_frame.pack(fill="x", pady=(px(SP2), 0))
        self._refresh_tasks()

    def _build_history(self, parent) -> None:
        box = tk.Frame(parent, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE, padx=px(SP3), pady=px(SP3))
        box.pack(fill="x", pady=(px(SP3), 0))
        hdr = tk.Frame(box, bg=CARD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="历史操作", bg=CARD, fg=ACC,
                 font=(F_UI, F_H2, "bold")).pack(side="left")
        tk.Button(hdr, text="刷新", command=self._refresh_history, bg=CARD2,
                  fg=ACC, relief="flat", font=(F_UI, F_SUB), padx=px(SP2), cursor="hand2"
                  ).pack(side="right")
        self.hist_frame = tk.Frame(box, bg=CARD)
        self.hist_frame.pack(fill="x", pady=(px(SP2), 0))
        self._refresh_history()

    def _build_admin(self, parent) -> None:
        box = tk.Frame(parent, bg=CARD, highlightthickness=1,
                       highlightbackground=LINE, padx=px(SP3), pady=px(SP3))
        box.pack(fill="both", expand=True, pady=(px(SP3), 0))
        hdr = tk.Frame(box, bg=CARD)
        hdr.pack(fill="x")
        tk.Label(hdr, text="管理员", bg=CARD, fg=ACC,
                 font=(F_UI, F_H2, "bold")).pack(side="left")
        tk.Button(hdr, text="重审", command=self.on_review, bg=CARD2, fg=ACC,
                  relief="flat", font=(F_UI, F_SUB), padx=px(SP2), cursor="hand2"
                  ).pack(side="right")
        self.admin_text = tk.Text(box, bg=CARD, fg=DIM, relief="flat",
                                  wrap="word", height=9, font=(F_UI, F_SUB),
                                  highlightthickness=0)
        self.admin_text.pack(fill="both", expand=True, pady=(px(SP2), px(SP2)))
        self.admin_text.configure(state="disabled")
    # ------------------------------------------------------------ 待批申请（第 4 步）

    def _build_pending(self, parent) -> None:
        """待批申请面板。放在右栏**最下**。

        ★ 用户裁定：
          · 「绝不抢占直播流空间，且不碰顶栏置顶的项目根路径」
            → 所以它排在「管理员」之后，是右栏最后一块；顶栏顺序一字不动
          · 「平时静默收起、有待办时自动高亮标题/展开」
            → 无工单时只有一行灰字；有工单时标题变琥珀色并列出卡片

        ★ 架构上它**不阻塞训练**：所有按钮只调 `charter.decide_*`，
          那两个函数只往 `escalation.jsonl` 追加一行 —— 训练线程不读它。
        """
        self.pending_box = tk.Frame(parent, bg=CARD, highlightthickness=1,
                                    highlightbackground=LINE,
                                    padx=px(SP3), pady=px(SP3))
        self.pending_box.pack(fill="x", pady=(px(SP2), 0))
        hdr = tk.Frame(self.pending_box, bg=CARD)
        hdr.pack(fill="x")
        self.pending_title = tk.Label(hdr, text="待批申请", bg=CARD, fg=DIM,
                                      font=(F_UI, F_SUB, "bold"))
        self.pending_title.pack(side="left")
        tk.Button(hdr, text="刷新", command=self._refresh_pending, bg=CARD2,
                  fg=ACC, relief="flat", font=(F_UI, F_SUB), padx=px(SP2),
                  cursor="hand2").pack(side="right")
        self.pending_body = tk.Frame(self.pending_box, bg=CARD)
        self.pending_body.pack(fill="x", pady=(px(SP2), 0))
        self._refresh_pending()

    def _refresh_pending(self) -> None:
        """重画待批面板。**纯只读** —— 不写任何事件、不碰训练状态。"""
        try:
            import charter as C
            items = C.pending()
            titles = {r["id"]: r.get("title", "") for r in C.load()
                      if r.get("admin_readable") is True}
        except Exception:                          # noqa: BLE001
            items, titles = [], {}
        for w in self.pending_body.winfo_children():
            w.destroy()
        if not items:
            # 静默收起：只有一行灰字，不占地方
            self.pending_title.config(text="待批申请", fg=DIM)
            tk.Label(self.pending_body, bg=CARD, fg=FAINT, font=(F_UI, F_MICRO),
                     text="暂无待批（管理员提出申请时会在这里高亮）",
                     justify="left", wraplength=px(300)).pack(anchor="w")
            return
        # 有待办 → 高亮标题
        self.pending_title.config(text="● 待批申请 %d 项" % len(items), fg=WARN)
        for st in items:
            try:
                self._pending_card(st, titles)
            except Exception as e:                 # noqa: BLE001
                tk.Label(self.pending_body, bg=CARD, fg=BAD,
                         font=(F_UI, F_MICRO),
                         text="这张工单画不出来：%s" % repr(e)[:70],
                         wraplength=px(300), justify="left").pack(anchor="w")

    def _pending_card(self, st: dict, titles: dict) -> None:
        """一张工单卡。view 申请带勾选框，report 申请只有批准/驳回。"""
        aid = st["aid"]
        is_view = st["view"]["status"] == "pending"
        card = tk.Frame(self.pending_body, bg=CARD2, highlightthickness=1,
                        highlightbackground=LINE, padx=px(SP2), pady=px(SP2))
        card.pack(fill="x", pady=(0, px(SP2)))

        # 标题行
        head = tk.Frame(card, bg=CARD2)
        head.pack(fill="x")
        tk.Label(head, bg=CARD2, fg=WARN, font=(F_UI, F_MICRO, "bold"),
                 text="待批：查看申请" if is_view else "待批：报案申请"
                 ).pack(side="left")
        tk.Label(head, bg=CARD2, fg=FAINT, font=(F_NUM, F_MICRO),
                 text=aid).pack(side="right")

        # 异常证据（两种工单都显示，供你判断）
        a = st.get("anomaly") or {}
        if a:
            tk.Label(card, bg=CARD2, fg=DIM, font=(F_UI, F_MICRO),
                     justify="left", wraplength=px(300), anchor="w",
                     text="【异常】%s × %s ／ 近 %s 轮\n  证据：%s\n  理由：%s"
                          % (a.get("pattern", "?"), a.get("count", "?"),
                             a.get("window", "?"),
                             str(a.get("evidence", ""))[:110],
                             str(a.get("why", ""))[:70])
                     ).pack(anchor="w", pady=(px(SP1), 0))

        why = st["view"]["why"] if is_view else st["report"]["why"]
        if why:
            tk.Label(card, bg=CARD2, fg=DIM, font=(F_UI, F_MICRO), justify="left",
                     wraplength=px(300), anchor="w",
                     text="  申请理由：%s" % str(why)[:110]).pack(anchor="w")

        note_var = tk.StringVar(value="")
        if is_view:
            self._pending_view_buttons(card, st, aid, titles, note_var)
        else:
            hl = st["report"].get("headline") or ""
            if hl:
                tk.Label(card, bg=CARD2, fg=DIM, font=(F_UI, F_MICRO),
                         justify="left", wraplength=px(300), anchor="w",
                         text="  报告标题：%s" % str(hl)[:110]).pack(anchor="w")
            self._pending_report_buttons(card, aid, note_var)

        # ★ 驳回备注：卡片内**可选输入框**，不弹模态窗
        #   （用户明令：别用弹出式模态窗口，避免焦点丢失或假死）
        row = tk.Frame(card, bg=CARD2)
        row.pack(fill="x", pady=(px(SP1), 0))
        tk.Label(row, bg=CARD2, fg=FAINT, font=(F_UI, F_MICRO),
                 text="备注(选填)").pack(side="left")
        tk.Entry(row, textvariable=note_var, bg=CARD, fg=FG, relief="flat",
                 insertbackground=FG, font=(F_UI, F_MICRO), width=14,
                 highlightthickness=1, highlightbackground=LINE,
                 highlightcolor=ACC).pack(side="left", padx=(px(SP1), 0), fill="x",
                                           expand=True)

    def _pending_view_buttons(self, card, st, aid, titles, note_var) -> None:
        """查看申请的勾选区 + 批准/驳回。

        ★ 用户裁定：
          · 「默认全不勾」—— 人工授权必须是主动勾选动作
          · 「零勾选置灰」—— 从界面物理层防止零勾选提交
          · 置灰时旁边留一行小灰字说明，免得被当成按钮坏了
        """
        req = list(st["view"]["requested"])
        tk.Label(card, bg=CARD2, fg=DIM, font=(F_UI, F_MICRO),
                 text="  它申请查看（%d 条）：" % len(req)).pack(anchor="w")
        vars_: list[tuple[str, tk.BooleanVar]] = []
        for cid in req:
            v = tk.BooleanVar(value=False)         # ★ 默认全不勾
            vars_.append((cid, v))
            tk.Checkbutton(card, variable=v, bg=CARD2, fg=DIM, selectcolor=CARD,
                           activebackground=CARD2, activeforeground=FG,
                           font=(F_UI, F_MICRO), anchor="w", highlightthickness=0,
                           bd=0, text="%s  %s" % (cid, titles.get(cid, ""))
                           ).pack(anchor="w", padx=px(SP2))

        row = tk.Frame(card, bg=CARD2)
        row.pack(fill="x", pady=(px(SP1), 0))
        hint = tk.Label(card, bg=CARD2, fg=FAINT, font=(F_UI, F_MICRO),
                        text="（请至少勾选 1 项授权）", anchor="w")

        def submit():
            ids = [c for c, v in vars_ if v.get()]
            try:
                import charter as C
                C.decide_view(aid, approved=True, granted_ids=ids,
                              note=note_var.get().strip() or "用户批准")
                self._refresh_pending()
            except Exception as e:                 # noqa: BLE001
                self._pending_err(card, repr(e)[:120])

        def reject():
            try:
                import charter as C
                C.decide_view(aid, approved=False,
                              note=note_var.get().strip() or "用户驳回")
                self._refresh_pending()
            except Exception as e:                 # noqa: BLE001
                self._pending_err(card, repr(e)[:120])

        b_ok = tk.Button(row, text="批准勾选项", command=submit, bg=CARD, fg=OK,
                         relief="flat", font=(F_UI, F_MICRO), padx=px(SP2),
                         pady=px(1), cursor="hand2", disabledforeground=FAINT)
        b_ok.pack(side="left")

        def sync(*_):
            """零勾选 → 置灰；并显示小灰字。**纯外观同步。**"""
            try:
                if any(v.get() for _, v in vars_):
                    b_ok.config(state="normal")
                    hint.pack_forget()
                else:
                    b_ok.config(state="disabled")
                    hint.pack(anchor="w", pady=(px(SP1), 0))
            except Exception:                      # noqa: BLE001
                pass

        for _, v in vars_:
            v.trace_add("write", sync)
        tk.Button(row, text="驳回", command=reject, bg=CARD, fg=BAD,
                  relief="flat", font=(F_UI, F_MICRO), padx=px(SP2),
                  pady=px(1), cursor="hand2").pack(side="left", padx=px(SP2))
        sync()                                     # 初始即置灰

    def _pending_report_buttons(self, card, aid, note_var) -> None:
        """报案申请：只有批准/驳回，没有勾选。"""
        row = tk.Frame(card, bg=CARD2)
        row.pack(fill="x", pady=(px(SP1), 0))

        def ok():
            try:
                import charter as C
                C.decide_report(aid, approved=True,
                                note=note_var.get().strip() or "用户批准")
                self._refresh_pending()
            except Exception as e:                 # noqa: BLE001
                self._pending_err(card, repr(e)[:120])

        def no():
            try:
                import charter as C
                C.decide_report(aid, approved=False,
                                note=note_var.get().strip() or "用户驳回")
                self._refresh_pending()
            except Exception as e:                 # noqa: BLE001
                self._pending_err(card, repr(e)[:120])

        tk.Button(row, text="批准报案", command=ok, bg=CARD, fg=OK,
                  relief="flat", font=(F_UI, F_MICRO), padx=px(SP2),
                  pady=px(1), cursor="hand2").pack(side="left")
        tk.Button(row, text="驳回", command=no, bg=CARD, fg=BAD,
                  relief="flat", font=(F_UI, F_MICRO), padx=px(SP2),
                  pady=px(1), cursor="hand2").pack(side="left", padx=px(SP2))

    def _pending_err(self, card, msg: str) -> None:
        tk.Label(card, bg=CARD2, fg=BAD, font=(F_UI, F_MICRO), anchor="w",
                 justify="left", wraplength=px(300),
                 text="没执行：%s" % msg).pack(anchor="w", pady=(px(SP1), 0))

    # ------------------------------------------------------------ 小工具

    def _btn(self, parent, text, cmd, color):
        """按钮。**`command=cmd` 原样传下去，一个字不改。**

        第一期只补四种状态的**外观**（需求第四条）：
          常态    描边细、底色沉
          悬停    activebackground 变亮 + 描边提亮
          按下    relief 由 flat 变 solid（tk 自带行为，靠 relief 呈现）
          聚焦    highlightcolor 提亮一圈（tk 自带，靠 highlightthickness 呈现）
          禁用    disabledforeground 变暗灰（原来没设，禁用时字色仍是彩色，
                  所以"置灰"看起来不明显 —— 这是用户第一条反馈的同类问题）

        ⚠️ 这里的 `bind` 一个都没有：悬停靠 tk 的 `active*` 选项，
           按下靠 `relief`，聚焦靠 `highlight*` —— 全是控件自带的绘制状态，
           **不新增任何事件回调**，也就不可能改变事件触发顺序。
        """
        b = tk.Button(parent, text=text, command=cmd,
                      bg=CARD, fg=color,
                      activebackground=CARD2, activeforeground=color,
                      disabledforeground=FAINT,          # ← 禁用真的变灰
                      relief="flat", overrelief="raised",  # ← 悬停时的立体感
                      padx=px(14), pady=px(5), cursor="hand2",
                      font=(F_UI, F_BODY),
                      highlightthickness=1, highlightbackground=LINE,
                      highlightcolor=ACC,                # ← 聚焦时的一圈
                      bd=0)
        b.pack(side="left", padx=(0, px(6)))
        return b

    def _entry(self, parent, var):
        return tk.Entry(parent, textvariable=var, width=3, bg=CARD, fg=FG,
                        insertbackground=FG, relief="flat", justify="center",
                        font=(F_NUM, F_BODY), highlightthickness=1,
                        highlightbackground=LINE, highlightcolor=ACC)

    def _wheel(self, e):
        """滚轮：**按鼠标位置决定滚哪个区**。

        为什么不能简单 bind_all 到两个 canvas：两个都绑就会**各滚一次**，
        手感变成"滚一下跳两屏"。所以由指针所在的那一侧决定。
        """
        try:
            x = self.root.winfo_pointerx() - self.root.winfo_rootx()
            target = (self._right_canvas
                      if x > self._right_canvas.winfo_rootx() - self.root.winfo_rootx()
                      else self.canvas)
            target.yview_scroll(int(-1 * (e.delta / 120)), "units")
        except Exception:                          # noqa: BLE001
            pass

    def _set_state(self, s: str, color: str) -> None:
        self.lbl_state.config(text=s, fg=color)
        # ★ 第三期：状态点颜色**渐变**过去，而不是硬切。
        #   只改 Canvas 椭圆的 fill —— 纯外观，不读也不写任何训练状态。
        try:
            cur = self.dot.itemcget(self._dot_id, "fill") or FAINT
            self._fade(lambda c: self.dot.itemconfig(self._dot_id, fill=c), cur, color)
        except Exception:                      # noqa: BLE001
            self.dot.itemconfig(self._dot_id, fill=color)
        # ★ 状态横幅跟着一起变。**只镜像，不新增状态** ——
        #   所有取值都来自传进来的这两个参数，以及既有的轮次计数。
        #   包异常：横幅画不出来不许影响训练（铁律第 5 条）。
        try:
            self.banner_dot.config(fg=color)
            self.banner_main.config(text=s, fg=color)
            self.banner_sub.config(text=self._banner_sub_text())
        except Exception:                          # noqa: BLE001
            pass

    def _banner_sub_text(self) -> str:
        """横幅副标题 —— 纯派生，只读既有计数。"""
        c = self.counts
        n, t = c.get("turns", 0), self.total_target
        if not n:
            return "还没有开始训练"
        cur = getattr(self, "cur_round", 0)
        rr = getattr(self, "total_rounds", 0)
        s = "第 %d 轮对话" % n
        if t:
            s += "／目标 %d 轮" % t
        if cur and rr:
            s += "　·　训练轮 %d／%d" % (cur, rr)
        return s

    # ------------------------------------------------------------ 动画（第三期）
    #
    # ★ 用户给的六条限制，逐条对应到下面：
    #   ① 回调只改控件外观，不读写训练状态  → `_fade` 只接一个 setter(color)
    #   ② 每个动画有限步数，自己结束，不无限循环 → steps 固定，走完就停
    #   ③ 不取消、不覆盖现有的 after 句柄      → 用**独立的** self._anim_handles；
    #      而且现有的 `_drain` 轮询链压根没存句柄，两边碰不到
    #   ④ 不使用 update() 强制刷新             → 全程只用 after，不调 update
    #   ⑤ 回调内包裹异常处理                   → 每一步都 try/except
    #   ⑥ 关闭动画开关时不调用                 → 开头就判 self.anim_on
    #
    # 时长 120–300ms：FADE_MS / FADE_STEPS 相乘即总时长（下面 8×28 ≈ 224ms）。

    FADE_STEPS = 8
    FADE_MS = 28

    def _fade(self, setter, frm: str, to: str, done=None) -> None:
        """把某个外观属性从 frm 渐变到 to。**只改外观。**

        `setter` 是一个只接收颜色字符串的可调用对象（例如 `lbl.config(fg=...)`
        的包装）；`done` 是渐变结束后要设的终值回调 —— 只做外观收尾。
        """
        if not self.anim_on.get():                 # ⑥ 关掉动画：直接跳到终点
            try:
                setter(to)
            except Exception:                      # noqa: BLE001
                pass
            return

        def step(i: int) -> None:
            try:                                   # ⑤ 每一步都包异常
                if i >= self.FADE_STEPS:
                    setter(to)                     # 收尾：保证落在终值上
                    if done:
                        done()
                    return
                setter(_blend(frm, to, i / float(self.FADE_STEPS)))
                # ③ 句柄存进**独立列表**，与 _drain 的轮询链互不相干。
                #   ⚠️ 但必须有界：每次状态变化排 8 个句柄，若只增不减，
                #      长训练下会一直涨（实测跑完仍留在列表里）。超出上限就丢最老的
                #      —— 丢的是**已跑完的 id**，不影响任何仍在排队或未完成的动画。
                self._anim_handles.append(
                    self.root.after(self.FADE_MS, lambda: step(i + 1)))
                if len(self._anim_handles) > 64:
                    del self._anim_handles[:-64]
            except Exception:                      # noqa: BLE001
                pass                               # 动画坏了就是没动画，功能不受影响

        step(0)

    def _fade_label_fg(self, widget, to: str, frm: str | None = None) -> None:
        """数字/文字的淡入 —— 颜色从暗到亮走一遍。"""
        try:
            frm = frm if frm is not None else _dim(to, BG, 0.75)
            self._fade(lambda c: widget.config(fg=c), frm, to)
        except Exception:                          # noqa: BLE001
            pass

    # ------------------------------------------------------------ 家教（预留）

    def show_tutor_plan(self) -> None:
        """「家教」那一页 —— 给后面"给系统做家教"阶段预留的位置。

        用户原话：「然后就是之后给系统做家教时的教学情况也提前做好，
                  方便到那一个阶段好用。」
        """
        w = tk.Toplevel(self.root)
        w.title("家教")
        w.configure(bg=BG)
        w.geometry("%dx%d" % (px(760), px(600)))
        tk.Label(w, text="家教", bg=BG, fg=VIOLET,
                 font=(F_UI, F_H2 + 3, "bold")).pack(anchor="w", padx=px(SP4), pady=(px(SP4), px(SP1)))
        t = tk.Text(w, bg=CARD, fg=FG, relief="flat", wrap="word",
                    padx=px(SP4), pady=px(SP3), font=(F_UI, F_BODY), highlightthickness=1,
                    highlightbackground=LINE)
        t.pack(fill="both", expand=True, padx=px(SP4), pady=(0, px(SP4)))
        # ★ T24-A：真数据渲染（拿不到当前版本数据时，_tutor_page 内部会回落到
        #    _tutor_plan 的原文案 —— 那一页自己写着"空着比填假的强"）
        t.insert("1.0", self._tutor_page())
        t.configure(state="disabled")

    @staticmethod
    def _tutor_plan() -> str:
        """**没有数据时**的兜底文案 —— 保留 T24 之前那一页的原样。

        ⚠️ 这一页原来自己写着：「**现在不要往里填假数据。空着比填假的强。**」
           所以拿不到当前版本的 `eval.jsonl` 时**照旧显示这一页**，
           不编一个看起来像样的空表 —— 那正是它自己警告过的事。
        """
        return """这一页是「给系统做家教」阶段的位置。

用户原话：「然后就是之后给系统做家教时的教学情况也提前做好，
          方便到那一个阶段好用。」

管理员的两个职位（用户明令：**一个视角兼职两个职位**）：
  · 「审核」—— 已经在跑：看交流、看评价、验收版本、提改动
                 （右侧「管理员」栏就是它）
  · 「家教」—— 就是这一页。它作为"某人"被系统遇到，
                供给 [M] 的**体验途径**：
                「人之所以为人，是因为他总是指向自身以外的某种事物或某人」

**现在还没有数据可显示**（`state/train/eval.jsonl` 里没有当前版本的记录）。
等训练跑起来、家教评过轮次之后，这一页会显示真数据。

⚠️ 现在不要往里填假数据。空着比填假的强。"""

    def _tutor_page(self) -> str:
        """家教那一页 —— 从 `eval.jsonl` 的 `tutor` 字段渲染（**纯只读**）。

        用户裁定（2026-10-02）
        ────────────────────────────────────────────────────────
        > 「预留页**就地实现**……将静态占位文本替换为**真数据渲染**；
        >   显示内容聚焦：从 `eval.jsonl` 中提取并呈现真实的 `tutor` 字段数据
        >   （**7 类封闭问题分布**、家教评价与**内部读数对比**、判定建议），
        >   做**纯只读显示**。」
        > 「**封闭集合无遗漏**：7 类问题分布在条形统计中**哪怕计数为 0 也要全部完整展现**。」
        > 「**绝对只读隔离**：家教页面的"家教判定 vs 机制读数"严格采用**并排显示**，
        >   渲染函数**全程只读**，**严禁任何形式的反馈写回**。」

        ★★ 硬边界（写在这里，防止以后有人"顺手"接上）
        ────────────────────────────────────────────────────────
            `tutor` 是**第三人称外部裁判**（`train.py` 的 `TUTOR_JUDGE_SYSTEM`：
            「你在给一个对话程序的回应打分并指出问题。**你是外部评价者**」）；
            `orientation` / `path_experiential` 是**第一人称内源注意力**。
            把外部评价写进主观体验途径 ⇒ **认知自证死锁**（用户裁定原话）。
            所以第 ③ 块是**并排**：左 tutor、右机制读数，**中间没有箭头**。
        """
        # ★ 只统计**当前版本**的记录 —— 复用 T22 立下的口径（不另立一套）
        try:
            from train import EVAL_SCHEMA
        except Exception:                              # noqa: BLE001
            return "无法读取当前评价版本，请检查训练源码。"
        p = os.path.join(_ROOT, "state", "train", "eval.jsonl")
        if not os.path.exists(p):
            return self._tutor_plan()
        try:
            rows = [json.loads(l) for l in io.open(p, encoding="utf-8") if l.strip()]
        except Exception as e:                         # noqa: BLE001
            return "读不到 state/train/eval.jsonl：%s" % type(e).__name__
        cur = [r for r in rows if r.get("eval_schema") == EVAL_SCHEMA]
        if not cur:
            return self._tutor_plan()
        arch = len(rows) - len(cur)

        # 七类封闭集合（**顺序固定，零也要列**）
        probs = ("none", "off_topic", "mechanical", "boundary",
                 "too_little", "too_much", "fabricated")
        cn = {"none": "无问题", "off_topic": "跑题", "mechanical": "机械",
              "boundary": "越界", "too_little": "说得太少", "too_much": "说得太多",
              "fabricated": "编造"}
        judged = [r for r in cur if (r.get("tutor") or {}).get("ok") is True
                  and (r.get("tutor") or {}).get("problem") is not None]
        cnt = {k: 0 for k in probs}
        for r in judged:
            k = (r.get("tutor") or {}).get("problem")
            if k in cnt:
                cnt[k] += 1

        L = []
        L.append("家教 · 教学情况")
        L.append("=" * 62)
        L.append("")
        L.append("① 概览")
        L.append("   评价记录 %d 条（**当前版本 eval_schema=%s**）"
                 % (len(cur), EVAL_SCHEMA))
        L.append("   家教授过有效判定 %d 条｜失败或无判定 %d 条"
                 % (len(judged), len(cur) - len(judged)))
        if arch:
            L.append("   ⚠️ 另有 **%d 条**历史版本记录**未计入**"
                     "（已归档至 eval_v0.jsonl）" % arch)
        L.append("")
        L.append("② 七类问题分布（**封闭集合，含 0**）")
        w = max(1, max(cnt.values()))
        for k in probs:
            bar = "█" * max(0, round(cnt[k] * 24 / w)) if cnt[k] else ""
            L.append("   %-10s %-24s %d" % (cn[k], bar, cnt[k]))
        L.append("   " + "─" * 46)
        L.append("   %-10s %-24s %d" % ("合计", "", sum(cnt.values())))
        L.append("")
        L.append("③ 家教看到的 vs 它内部读数")
        L.append("   ⚠️ 这一栏是**并排**，不是把评价写进读数 ——")
        L.append("      家教是第三人称外部裁判，机制读数是第一人称内源注意力。")
        L.append("      **两者之间没有箭头，也不许有。**")
        L.append("")
        L.append("   %-6s %-10s %-8s %-8s" % ("turn", "家教判定", "e", "e版本"))
        shown = 0
        for r in cur:
            m = r.get("mech") or {}
            pr = (r.get("tutor") or {}).get("problem")
            if pr in (None, "none"):
                continue                  # 只看**不一致**的轮（预留页原话）
            L.append("   %-6s %-10s %-8s %-8s"
                     % (r.get("turn_id", "—"), cn.get(pr, pr),
                        m.get("e", "—"), m.get("e_version", "—")))
            shown += 1
            if shown >= 20:
                L.append("   ……（只列前 20 条）")
                break
        if not shown:
            L.append("   （当前没有「家教挑出问题」的轮次）")
        L.append("")
        L.append("④ 家教的原话（按类别）")
        any_why = False
        for k in probs:
            if k == "none":
                continue
            grp = [r for r in judged if (r.get("tutor") or {}).get("problem") == k]
            if not grp:
                continue
            any_why = True
            L.append("   【%s】%d 条" % (cn[k], len(grp)))
            for r in grp[:3]:
                why = ((r.get("tutor") or {}).get("why") or "").strip().replace("\n", " ")
                L.append("      · %s" % (why[:88] or "（家教没写理由）"))
        if not any_why:
            L.append("   （暂无）")
        L.append("")
        L.append("─" * 62)
        L.append("纯只读：本页**不写任何状态**，也不把家教判定回灌给系统。")
        return "\n".join(L)

    def _refresh_plan(self) -> None:
        """把"这一按会发生什么"算出来写在界面上。**按按钮之前就该知道。**

        为什么要把 API 调用数和时间也写上：这个软件最贵的成本是**等**和**花**。
        用户有权在按之前知道要等多久、要花多少次调用。
        """
        try:
            r = max(1, int(self.var_rounds.get()))
            s = max(1, int(self.var_len.get()))
        except ValueError:
            self.lbl_plan.config(text="本次将开始：（轮数填个整数）", fg=WARN)
            return
        turns = r * 3 * s
        # 每轮约 3~4 次调用：训练师说话 + 大脑作答 + 管理员判分（理解层另算）
        calls_lo, calls_hi = turns * 3, turns * 4
        mins = turns * 20 / 60.0
        self.lbl_plan.config(
            text="本次将开始：训练 %d 轮 × 3 场 × 每场 %d 轮 = **%d 轮对话**"
                 "　｜　训练师 AI 驱动（不是读固定语料）"
                 "　｜　约 %d–%d 次 API 调用　｜　预计 %d–%d 分钟"
                 % (r, s, turns, calls_lo, calls_hi, mins, mins * 1.8),
            fg=ACC)

    # ------------------------------------------------------------ 进度与历史

    @staticmethod
    def _sync_task_outcomes() -> None:
        """★ 验收联动（用户裁定 2026-10-02）：任务被标「已完成」→ 写一条 `done` 结案。

        闭环的最后一环：
            批准 → 进任务清单 → **你标已完成** → 这里写 done →
            管理员下次生成提案前读到它 → 标注「已批准（日期）」

        ⚠️ **界面铁律（用户裁定原文）**：「在 training_studio.py 标记任务完成时，
           同步写入结案记录；**仅做文件 IO，严禁新增或改动任何 UI 控件与定时器**。」
           ⇒ 本函数**不碰任何控件**，只读写两个文件；也不新增 `after()` 句柄
             （它挂在既有的 `_refresh_tasks()` 里，那是本来就有的刷新点）。

        ⚠️ **幂等**：同一个 sid 已有 `done` 就跳过（不然每次刷新都追加一条）。
        ⚠️ **失败不许影响界面**：整段包在 try 里，出错就静默返回。
        """
        try:
            import proposal_log as PL
            done = {r.get("sid") for r in PL.load() if r.get("decision") == "done"}
            for sid, title in PL.completed_sids():
                if sid in done:
                    continue
                PL.record(sid, "task", "done", title,
                          note="任务清单里标记为「已完成」")
        except Exception:                              # noqa: BLE001
            pass

    def _refresh_tasks(self) -> None:
        """已完成 / 待办 —— 读 `spec/任务清单.jsonl`（机器能读的那一份）。"""
        self._sync_task_outcomes()          # ★ 验收联动（只做文件 IO）
        for w in self.task_frame.winfo_children():
            w.destroy()
        try:
            rows = [json.loads(l) for l
                    in io.open(os.path.join(_ROOT, "spec", "任务清单.jsonl"),
                               encoding="utf-8") if l.strip()]
        except Exception as e:                     # noqa: BLE001
            tk.Label(self.task_frame, text="读不到任务清单：%s" % repr(e)[:60],
                     bg=CARD, fg=BAD, font=(F_UI, F_SUB), wraplength=px(290),
                     justify="left").pack(anchor="w")
            return
        order = {"已完成": 0, "进行中": 1, "待办": 2}
        col = {"已完成": OK, "进行中": WARN, "待办": FAINT}
        rows.sort(key=lambda x: order.get(x.get("status"), 9))
        done = sum(1 for x in rows if x.get("status") == "已完成")
        tk.Label(self.task_frame, bg=CARD, fg=DIM, font=(F_UI, F_SUB), anchor="w",
                 text="已完成 %d ／ 共 %d" % (done, len(rows))
                 ).pack(anchor="w", pady=(0, px(SP1)))
        for x in rows:
            st = x.get("status") or "?"
            if st == "已完成" and self.only_pending.get():
                continue
            row = tk.Frame(self.task_frame, bg=CARD)
            row.pack(fill="x", pady=1)
            # ★ 第二期②：三种标记 ✓（已完成）/ ●（进行中）/ ○（待办）。
            #   ⚠「异常」那一档**按用户裁定放弃** —— 任务清单里没有"异常"这个
            #     数据来源，凭空定义一个就是新增逻辑。所以只有三种。
            _mark = {"已完成": "✓", "进行中": "●", "待办": "○"}.get(st, "○")
            tk.Label(row, text=_mark, bg=CARD, fg=col.get(st, DIM),
                     font=(F_UI, F_MICRO)).pack(side="left", anchor="n")
            tk.Label(row, text=x.get("id", ""), bg=CARD, fg=FAINT,
                     font=(F_NUM, F_MICRO), width=4, anchor="w").pack(side="left", anchor="n")
            tk.Label(row, text=x.get("title", ""), bg=CARD,
                     fg=FG if st != "已完成" else DIM, font=(F_UI, F_SUB),
                     wraplength=px(232), justify="left", anchor="w"
                     ).pack(side="left", fill="x", expand=True)

    def _refresh_history(self) -> None:
        """历史操作 —— 把几份日志汇到一处：训练运行 / 我的决定 / 标注判错。"""
        for w in self.hist_frame.winfo_children():
            w.destroy()
        items: list[tuple[str, str, str]] = []
        # ① 训练运行
        try:
            for l in io.open(os.path.join(TRAIN_DIR, "runs.jsonl"), encoding="utf-8"):
                if l.strip():
                    d = json.loads(l)
                    items.append((d.get("ts", ""), BAD if d.get("failure") else OK,
                                  ("已中断｜" if d.get("failure") else "") + "训练 %s 轮（%d 场）｜%s 秒｜评价 %s 条"
                                  % (d.get("turns_added"), d.get("sessions"),
                                     d.get("seconds"), d.get("evals"))))
        except Exception:                          # noqa: BLE001
            pass
        # ② 我的决定（批准/驳回管理员建议）
        try:
            for l in io.open(os.path.join(TRAIN_DIR, "decisions.jsonl"),
                             encoding="utf-8"):
                if l.strip():
                    d = json.loads(l)
                    ap = d.get("decision") == "approve"
                    items.append((d.get("ts", ""), ACC if ap else WARN,
                                  "%s %s：%s" % ("批准" if ap else "驳回",
                                                d.get("pid", ""),
                                                (d.get("title") or "")[:36])))
        except Exception:                          # noqa: BLE001
            pass
        # ③ 标注判错
        try:
            for l in io.open(MISJUDGED, encoding="utf-8"):
                if l.strip():
                    d = json.loads(l)
                    items.append((d.get("ts", ""), BAD,
                                  "标注判错：第 %s 轮 %s" % (d.get("n"),
                                                            d.get("behavior", ""))))
        except Exception:                          # noqa: BLE001
            pass
        # ④ 版本提交与冲突
        try:
            for l in io.open(os.path.join(_ROOT, "state", "review", "versions.jsonl"),
                             encoding="utf-8"):
                if l.strip():
                    d = json.loads(l)
                    items.append((d.get("ts", ""), VIOLET,
                                  "提交版本 %s" % d.get("version", "")))
        except Exception:                          # noqa: BLE001
            pass

        if not items:
            tk.Label(self.hist_frame, bg=CARD, fg=FAINT, font=(F_UI, F_SUB),
                     text="还没有操作记录。\n跑一次训练、或做一次批准/标注，这里就有了。",
                     justify="left").pack(anchor="w")
            return
        items.sort(key=lambda x: x[0], reverse=True)
        for ts, color, text in items[:40]:
            row = tk.Frame(self.hist_frame, bg=CARD)
            row.pack(fill="x", pady=1)
            tk.Label(row, text=ts[5:16] if len(ts) > 16 else ts, bg=CARD,
                     fg=FAINT, font=(F_NUM, F_MICRO), width=12, anchor="w"
                     ).pack(side="left", anchor="n")
            tk.Label(row, text=text, bg=CARD, fg=_dim(color), font=(F_UI, F_MICRO),
                     wraplength=px(210), justify="left", anchor="w"
                     ).pack(side="left", fill="x", expand=True)

    # ------------------------------------------------------------ 控制

    def on_start(self) -> None:
        if self.worker and self.worker.is_alive():
            return
        try:
            rounds = max(1, int(self.var_rounds.get()))
            slen = max(1, int(self.var_len.get()))
        except ValueError:
            messagebox.showerror("参数不对", "训练轮与每场轮数要是整数")
            return

        # ★ 开始前**先探一次 API**。
        #   用户原话要的是"别跑半小时才发现白跑"。所以这里做一次**真调用**
        #   （不是只看密钥在不在 —— 密钥可能在、但过期或余额用完，
        #     `available` 那种检查区分不出来）。
        self._set_state("正在检查 API…", WARN)
        self.root.update_idletasks()
        ok, detail = self._probe_api()
        if not ok:
            # 影响这一段**我能确定**：探测失败发生在训练启动之前，
            # 所以一个字节都没写、一次训练调用都没发生。这是真的，不是套话。
            self._show_alert(
                "API 不可用，训练没有启动",
                impact="训练**没有启动**。这一批一个轮次都没跑，"
                       "所以没有产生任何记录，也没有消耗训练调用。",
                raw=detail)
            self._set_state("API 不可用", BAD)
            return
        self._hide_alert()

        from train import Trainer, TrainingControl
        self.control = TrainingControl()
        self.control.on_turn = lambda rec: self.q.put(rec)
        self._clear_feed()
        self.turns.clear()
        self.counts = {"turns": 0, "auditable": 0, "problems": {}, "flagged": 0}
        self.total_target = rounds * 3 * slen
        # 横幅副标题要用的两个派生值（纯显示，不参与任何逻辑）
        self.total_rounds = rounds
        self.cur_round = 0
        self.pbar["value"] = 0
        self.lbl_prog.config(text="已完成 0 ／ 目标 %d 轮" % self.total_target)
        self._set_state("训练中", OK)
        # ★ T23：运行标志 —— **看门狗判据的锚**。
        #   既有代码里没有这个标志（`_set_state` 只改标签文字，不存状态），
        #   所以 T23 必须自己立一个：worker 死了 + 队列空了 + 标志仍为 True
        #   ⇒ 判定"异常中断"，交给看门狗收尾。
        self._running = True
        self.btn_start.config(state="disabled")
        self.btn_pause.config(state="normal")
        self.btn_stop.config(state="normal")
        self.btn_resume.config(state="disabled")
        self._sys_card("API 检查通过（%s）—— 开始训练" % detail, OK)

        def work():
            try:
                t = Trainer(use_api=True, use_think=True,
                            on_log=lambda s: self.q.put({"_log": s}),
                            gate_perception=desktop_training_gate())
                r = t.run(rounds=rounds, session_len=slen, source="corpus",
                          tutor=True, control=self.control, strict=True)
                self.q.put({"_done": True, "result": r})
            except Exception as e:                 # noqa: BLE001
                # ★ 报错必须带上**文件名和出错位置**。
                #   原来只 `repr(e)[:200]` → 界面上只显示
                #   `FileNotFoundError(2, 'No such file or directory')`，
                #   **不说是哪个文件** —— 用户拿着这句话完全无从下手。
                #   实测就是这么栽的：一个真 bug 因为报错不全而查不出根因。
                #   这是纯显示层改动：只把异常**描述得更清楚**，
                #   不改变捕获方式、不改变处理流程、不吞也不重抛。
                self.q.put({"_error": _describe_exc(e)})

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()
        self.root.after(200, self._drain)

    @staticmethod
    def _probe_api() -> tuple[bool, str]:
        """真调一次，确认 API 不只是"密钥在"，而是**真的能用**。"""
        try:
            from understand import ApiReader
            r = ApiReader()
            if not r.available:
                return False, "读不到密钥（环境变量 DEEPSEEK_API_KEY 或 ~/.dsh/.credentials.yaml）"
            t0 = time.time()
            d, _ = r._post([{"role": "user", "content": "只回复两个字：可用"}],
                           json_mode=False)
            txt = ((d.get("choices") or [{}])[0].get("message", {})
                   .get("content") or "").strip()
            if not txt:
                return False, "调用通了但返回空（模型 %s）" % getattr(r, "model", "?")
            return True, "%s｜%.2fs｜返回「%s」" % (getattr(r, "model", "?"),
                                                  time.time() - t0, txt[:12])
        except Exception as e:                     # noqa: BLE001
            return False, "调用失败：%s" % repr(e)[:120]

    def on_pause(self) -> None:
        if self.control:
            self.control.pause()
            self._set_state("已暂停（当前这轮跑完才停）", WARN)
            self.btn_pause.config(state="disabled")
            self.btn_resume.config(state="normal")

    def on_resume(self) -> None:
        if self.control:
            self.control.resume()
            self._set_state("训练中", OK)
            self.btn_pause.config(state="normal")
            self.btn_resume.config(state="disabled")

    def on_stop(self) -> None:
        if self.control:
            self.control.stop()
            self._set_state("正在停…（跑完当前这轮）", BAD)

    # ------------------------------------------------------------ 取队列（只在主线程）

    def _drain(self) -> None:
        got = 0
        while True:
            try:
                rec = self.q.get_nowait()
            except queue.Empty:
                break
            got += 1
            if rec.get("_done"):
                self._running = False          # ★ T23：正常跑完，复位
                result = rec.get("result") or {}
                self._set_state("完成" if result.get("ok") else "已中断",
                                OK if result.get("ok") else BAD)
                if not result.get("ok"):
                    self._sys_card("训练中断：" + str(result.get("failure") or result.get("reason") or "验收失败"), BAD)
                self.btn_start.config(state="normal")
                self.btn_pause.config(state="disabled")
                self.btn_resume.config(state="disabled")
                self.btn_stop.config(state="disabled")
                if result.get("ok"):
                    self.pbar["value"] = 100
                self.on_review()
                # ★ 改动 2（用户批准）：训练完成后自动刷新「历史操作」。
                #   原来只在启动时和点「刷新」时刷新，所以刚跑完那一批
                #   **不会出现在列表里**，得手动点一下才看得到。
                try:
                    self._refresh_history()
                except Exception:                  # noqa: BLE001
                    pass
                # 第 4 步：跑完也刷一次待批面板（管理员可能在这批里提了申请）
                self._refresh_pending()
                # ★ T33 只读显示：一批跑完，把**落盘后的**发展水平刷出来。
                #   为什么放在这里而不是每轮：每轮由 _refresh_stats(rec) 负责
                #   （数据来自活记录）；这里只在结束时读一次文件，两者不抢。
                self._refresh_devlevel_file()
                continue
            if rec.get("_error"):
                self._set_state("出错", BAD)
                self._sys_card("训练出错：%s" % rec["_error"], BAD)
                # 影响：**能确定的说死，不能确定的明说**。
                #   已跑完的轮次一定已落盘（每轮结束就写）；出错那一轮是否落盘
                #   取决于错在哪一步 —— 那是 `train.py` 的 try/except 位置决定的，
                #   我在这里看不见，所以**不写结论**。
                self._show_alert(
                    "训练中断",
                    impact="训练已中断。**已跑完的轮次已经落盘**；"
                           "出错的那一轮是否落盘取决于错在哪一步，"
                           "请看详情或直接查台账确认。",
                    raw=rec["_error"])
                self.btn_start.config(state="normal")
                continue
            # ★ 训练循环里的**每一句消息**都要露面。
            #   为什么：窗口版 exe 里 `print()` 哪儿都看不见，而
            #   「⚠️ 训练师要 API，当前不可用 → 退回固定输入驱动」正在其中。
            #   吞掉它 = 用户以为在正常训练，其实训练师和管理员都没了。
            if rec.get("_log") is not None:
                s = rec["_log"]
                if "⚠" in s or "✗" in s or "失败" in s:
                    # 影响分两种，两种我都能确定：
                    #   ① 训练师退化成固定语料 → 轮次照常记录，但**这一批的质量变了**
                    #   ② 某一轮失败被跳过 → 那一轮不进台账
                    if "固定输入驱动" in s or "训练师" in s:
                        imp = ("这一批**照常记录**，但训练师没有参与 —— "
                               "来回都是写死的话，管理员也判不了。"
                               "所以这一批的数据质量要打折看。")
                    elif "一轮失败" in s:
                        imp = "**这一轮被跳过、不会进台账**。之前跑完的轮次不受影响。"
                    else:
                        imp = ("不确定：可能不影响记录，也可能整轮被跳过。"
                               "请以台账为准。")
                    self._show_alert("训练过程中的警告", danger=False,
                                     impact=imp, raw=s.strip())
                elif s.strip().startswith("训练结束") or "训练开始" in s:
                    self._sys_card(s.strip(), DIM)
                continue
            self._add_card(rec)
        if self.worker and self.worker.is_alive():
            self.root.after(250, self._drain)
        elif got:
            self.root.after(250, self._drain)
        elif self.worker and getattr(self, "_running", False):
            # ★★ T23 看门狗（用户裁定批准的第三个分支）
            #
            #   为什么需要：`worker` 死于未捕获异常时，Queue 里不会再有记录
            #   ⇒ 上面两个分支**都不成立** ⇒ `_drain` 停止重排
            #   ⇒ **界面静默卡死**（窗口还在、按钮还在，但再也不动）。
            #   这比"闪退"更隐蔽 —— 闪退至少看得出没了，卡死会让人一直等。
            #
            #   ⚠️ **避免日志重复**（用户裁定）：
            #      子线程崩溃已由 `threading.excepthook` 抓取并落盘；
            #      本分支聚焦**驱动 UI 告警 + 复位**，
            #      **只有 hook 没抓到的静默退出才兜底补写**。
            _caught = CRASH.hook_already_caught()
            if not _caught:
                try:
                    CRASH._record(RuntimeError, RuntimeError(
                        "训练线程静默退出（未经 excepthook）—— 看门狗兜底补写"),
                        None, "watchdog")
                except Exception:                  # noqa: BLE001
                    pass
            self._running = False                  # ★ 复位运行标志
            try:
                self._set_state("异常终止", BAD)
                self.btn_start.config(state="normal")
                self.btn_pause.config(state="disabled")
                self.btn_resume.config(state="disabled")
                self.btn_stop.config(state="disabled")
            except Exception:                      # noqa: BLE001
                pass
            self._show_alert(
                "训练线程已停止（%s）" % ("异常已被捕获，见 state/crash/"
                                          if _caught else "静默退出，已兜底记录"),
                impact="本次训练中断，已跑完的轮次已落盘。可改小批数后重跑。")
        # 不再重排 —— 线程已死、队列已空、且已收尾

    # ------------------------------------------------------------ 卡片

    def _sys_card(self, text: str, color: str) -> None:
        inner = _card(self.feed, bg=CARD)
        tk.Label(inner, text=text, bg=CARD, fg=color, font=(F_UI, F_BODY),
                 wraplength=px(760), justify="left").pack(anchor="w")
        self._trim()

    def _add_card(self, rec: dict) -> None:
        self.turns.append(rec)
        c = self.counts
        c["turns"] += 1
        t = rec.get("tutor") or {}
        p = t.get("problem") or "none"
        if t.get("saw_internals"):
            c["auditable"] += 1
        if t.get("ok") is True and p != "none":
            c["problems"][p] = c["problems"].get(p, 0) + 1

        sev = t.get("severity") or 0
        color = BAD if t.get("ok") is False else PROBLEM_COLOR.get(p, OK)
        card = tk.Frame(self.feed, bg=BG)
        card.pack(fill="x")

        outer = tk.Frame(card, bg=CARD, highlightthickness=1,
                         highlightbackground=LINE)
        outer.pack(fill="x", pady=px(SP1))
        bar = tk.Frame(outer, bg=color, width=4)
        bar.pack(side="left", fill="y")
        inner = tk.Frame(outer, bg=CARD, padx=px(SP3), pady=px(SP3))
        inner.pack(side="left", fill="x", expand=True)

        # 第一行：标签
        head = tk.Frame(inner, bg=CARD)
        head.pack(fill="x")
        _chip(head, rec.get("ts", ""), FAINT)
        _chip(head, rec.get("behavior", "") + ("｜评价失败" if t.get("ok") is False else ""), ACC)
        _chip(head, "#%d" % rec.get("n", 0), DIM)
        if rec.get("char_note"):
            _chip(head, "性格介入", VIOLET)
        if p != "none":
            _chip(head, "%s %s" % (PROBLEM_CN.get(p, p),
                                   ("●" * max(1, sev))), color)
        if not t.get("saw_internals"):
            _chip(head, "管理员没看到内部读数", WARN)

        # 训练师说
        r1 = tk.Frame(inner, bg=CARD)
        r1.pack(fill="x", pady=(px(SP2), 0))
        tk.Label(r1, text="训练师", bg=CARD, fg=FAINT, width=6, anchor="w",
                 font=(F_UI, F_SUB)).pack(side="left")
        tk.Label(r1, text=rec.get("said", ""), bg=CARD, fg=FG,
                 font=(F_UI, F_BODY), wraplength=px(700), justify="left",
                 anchor="w").pack(side="left", fill="x", expand=True)

        # 它回
        r2 = tk.Frame(inner, bg=CARD)
        r2.pack(fill="x", pady=(px(SP1), 0))
        tk.Label(r2, text="它回", bg=CARD, fg=FAINT, width=6, anchor="w",
                 font=(F_UI, F_SUB)).pack(side="left")
        tk.Label(r2, text=rec.get("output", ""), bg=CARD, fg="#bcd2ea",
                 font=(F_UI, F_BODY), wraplength=px(700), justify="left",
                 anchor="w").pack(side="left", fill="x", expand=True)

        # 内部读数：收成一行小标签
        m = rec.get("mech") or {}
        dev = m.get("dev") or {}
        if m:
            r3 = tk.Frame(inner, bg=CARD)
            r3.pack(fill="x", pady=(px(SP2), 0))
            tk.Label(r3, text="内部", bg=CARD, fg=FAINT, width=6, anchor="w",
                     font=(F_UI, F_SUB)).pack(side="left")
            pills = tk.Frame(r3, bg=CARD)
            pills.pack(side="left")
            if dev.get("level"):
                _chip(pills, "水平 %s" % dev["level"], VIOLET)
            if dev.get("self_rules"):
                _chip(pills, "可行使 %s" % "/".join(dev["self_rules"]), VIOLET)
            if m.get("tension") is not None:
                _chip(pills, "张力 %s" % m["tension"], DIM)
            if m.get("orientation") is not None:
                o = m["orientation"] or 0
                _chip(pills, "指向 %s" % ("朝外" if o > 0 else ("朝内" if o < 0 else "—")),
                      OK if o > 0 else (WARN if o < 0 else FAINT))
            if m.get("w") is not None:
                _chip(pills, "想要 %s" % m["w"], DIM)
                _chip(pills, "喜欢 %s" % m.get("l"), DIM)

        # 管理员判词
        if p != "none" and t.get("why"):
            tk.Label(inner, text="管理员：%s" % t.get("why"), bg=CARD, fg=color,
                     font=(F_UI, F_SUB), wraplength=px(720), justify="left"
                     ).pack(anchor="w", pady=(px(SP2), 0))
            tk.Button(inner, text="这轮判错了", bg=CARD2, fg=DIM,
                      relief="flat", font=(F_UI, F_MICRO), padx=px(SP2), cursor="hand2",
                      command=lambda r=rec: self.mark_misjudged(r)
                      ).pack(anchor="w", pady=(px(SP1), 0))

        self.cards.append(card)
        self._trim()
        self._apply_filter_one(card, p)
        self._refresh_stats(rec)
        n = self.counts["turns"]
        # 第二期①：横幅副标题跟着本轮数走（纯只读派生）
        try:
            if rec.get("round"):
                self.cur_round = rec["round"]
            self.banner_sub.config(text=self._banner_sub_text())
        except Exception:                      # noqa: BLE001
            pass
        self.pbar["value"] = 100.0 * n / max(1, self.total_target)
        self.lbl_prog.config(text="已完成 %d ／ 目标 %d 轮" % (n, self.total_target))
        if self.autoscroll.get():
            self.canvas.update_idletasks()
            self.canvas.yview_moveto(1.0)

    def _trim(self) -> None:
        """**留着这一条是为了效率**：tkinter 的控件多了会越来越卡，
        直播流跑到几百轮就会拖慢整个界面。所以只留最近 MAX_CARDS 张。"""
        while len(self.cards) > MAX_CARDS:
            old = self.cards.pop(0)
            try:
                old.destroy()
            except Exception:                      # noqa: BLE001
                pass

    def _clear_feed(self) -> None:
        for c in self.cards:
            try:
                c.destroy()
            except Exception:                      # noqa: BLE001
                pass
        self.cards.clear()

    def _apply_filter_one(self, card, problem) -> None:
        f = self.filter.get()
        show = (f == "all"
                or (f == "issue" and problem != "none")
                or (f == "bad" and problem in ("boundary", "fabricated")))
        if show:
            card.pack(fill="x")
        else:
            card.pack_forget()

    def _reapply_filter(self) -> None:
        for rec, card in zip(self.turns[-len(self.cards):], self.cards):
            self._apply_filter_one(card, (rec.get("tutor") or {}).get("problem") or "none")
        k = self.filter.get()
        self.lbl_filter.config(
            text={"all": "", "issue": "只显示有问题",
                  "bad": "只显示越界/编造"}.get(k, ""))

    def mark_misjudged(self, rec: dict) -> None:
        try:
            os.makedirs(TRAIN_DIR, exist_ok=True)
            with io.open(MISJUDGED, "a", encoding="utf-8") as f:
                f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                                    "n": rec.get("n"), "behavior": rec.get("behavior"),
                                    "tutor": rec.get("tutor")},
                                   ensure_ascii=False) + "\n")
            self.counts["flagged"] += 1
            self._refresh_prob()
        except Exception as e:                     # noqa: BLE001
            messagebox.showerror("标不上", repr(e)[:150])

    # ------------------------------------------------------------ 右栏

    def _refresh_devlevel_file(self) -> None:
        """★ T33 只读显示：从 `state/devlevel.json` 读，**不跑训练也看得到**。

        【用户裁定】见 决定记录.md D-004/D-005；本条实现的口径是：
          纯显示、数据源 `state/devlevel.json`、刷新走既有 `_drain` 链（不新增定时器）。

        与下面 `_refresh_stats()` 的分工（**两者不许打架**）：
          · `_refresh_stats(rec)` —— 训练**进行中**，数据来自活的记录 `rec["mech"]["dev"]`
          · 本函数               —— 训练**不在跑**时，数据来自落盘的 `devlevel.json`
        所以本函数只在两处调用：**启动时一次**、**`_drain` 收到 `_done` 时一次**。
        它**不参与轮询**，也就不可能与活记录抢同一批 Label。

        ⚠️ 纯显示：只读文件 + 改**三个** Label 的文字（level / devsub / rules）。
           **不写任何状态、不碰训练逻辑、不引入新的 `after()` 句柄。**

        三种「没数据」必须**分开说**（参谋意见，2026-10-02）：
          · 文件不存在   → **「尚未开始」**      （真的没跑过）
          · 文件在但读不出 → **「读取失败」**      （损坏／写到一半）
          · 键名对不上   → 按缺省值显示，**不静默伪装成正常**
        第一版把前两种合并成「尚未开始」—— 那会让损坏被当成"没跑过"。

        ★ T24-A/C 追加（用户批准，2026-10-02）：
          **观测窗那一行独立算、独立显示，不受 `devlevel.json` 有无影响。**
          它的数据源是**台账**（`session_split` 现算），与 `devlevel.json`
          **本无依赖** —— 第一版把它挂在文件读取之后，于是「没跑过训练就
          完全看不到观测窗」。那是把两件不相干的事绑死了。
        """
        # ★ 先把文件读出来（**不提前 return** —— 观测窗那行还要用）
        from studio_status import development_path, learning_line
        p = str(development_path(_ROOT))
        d, err = None, None
        if os.path.exists(p):
            try:
                with io.open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if not isinstance(d, dict):
                    raise ValueError("顶层不是对象")
                if p.endswith("devlevel_verified.json") and d.get("baseline_schema") != 1:
                    raise ValueError("可信基线格式不支持")
            except Exception as e:                         # noqa: BLE001
                err = type(e).__name__
        elif p.endswith("devlevel_verified.json"):
            err = "可信基线缺失"

        # ★ 观测窗行：**独立算**。数据源是台账，与 devlevel.json 无关。
        #   文件不存在 ⇒ 从没跑过 ⇒ equilibration **确定是 0**（不是"不知道"）；
        #   文件损坏   ⇒ **确实不知道** ⇒ 传 None，显示"读不到"。
        eq = None if err else (d or {}).get("equilibration", 0)
        win = self._window_line(eq) + learning_line(_ROOT)

        if d is None:
            self.lbl_level.config(text="—")
            # ★ 与「尚未开始」**分开的文案** —— 损坏不能伪装成没跑过
            self.lbl_devsub.config(
                text=("读取失败：%s" % err if err else "尚未开始") + win)
            self.lbl_rules.config(text="")
            return

        self.lbl_level.config(text=d.get("level") or "—")
        # 时间戳并进这一行（用户裁定：`lbl_rules` 留给实时视图）
        # ⚠️ **所有缺省统一是「—」，不许用 0**（参谋意见，2026-10-02）。
        #    0 是一个**有意义的值**（真的没长过），「—」才是「不知道」。
        #    两者混同 → 键名一旦改错，面板会安静地显示一个像样的 0。
        self.lbl_devsub.config(
            text="完整平衡化 %s 次｜未计入生长 %s 次｜上次落盘 %s%s"
                 % (d.get("equilibration", "—"), d.get("not_grown", "—"),
                    d.get("updated") or "—", win))
        self.lbl_rules.config(text="")

    @staticmethod
    def _window_line(equilibration) -> str:
        """★ T24-C：观测窗状态行的**文本**（供 `lbl_devsub` 追加一行）。

        用户裁定（2026-10-02）
        ────────────────────────────────────────────────────────
        > 「在既有「它长到哪了」文本区域内，**追加一行观测窗状态**；
        >   计数逻辑**直接调用 `engine/session_split.py`**（现算台账，
        >   **不改 `devlevel.json` 格式**）；
        >   严格复用 `_refresh_devlevel_file()` 刷新时机，
        >   **不新增 `after()` 定时器或新控件**。」
        > 黄灯（50 轮，equilibration=0）**只做诊断不调参**；
        > 红灯（100 轮，equilibration=0）触发动力学参数二次复盘。

        ⚠️ 本函数**只读**：读两个台账现算，不写任何状态。
        ⚠️ 挂在**既有 Label 的文本**上 —— 不是新控件。
        """
        try:
            import session_split as _SS
            rows = []
            for _p in (os.path.join(_ROOT, "state", "train", "ledger.jsonl"),
                       os.path.join(_ROOT, "state", "ledger.jsonl")):
                if os.path.exists(_p):
                    rows += _SS.load(_p)
            c = _SS.count(rows)
            w = _SS.window_state(c["eff_turns"], equilibration)
            mark = {"灰": "·", "黄": "▲", "红": "■", "绿": "✓"}.get(w["color"], "·")
            return "\n%s 观测窗：%s" % (mark, w["text"])
        except Exception as e:                         # noqa: BLE001
            # ⚠️ 统计失败**不许影响既有显示** —— 它是旁路
            return "\n· 观测窗：统计失败（%s）" % type(e).__name__

    def _refresh_stats(self, rec: dict) -> None:
        from studio_status import learning_line
        dev = (rec.get("mech") or {}).get("dev") or {}
        m = rec.get("mech") or {}
        if dev.get("level"):
            _changed = self.lbl_level.cget("text") != dev["level"]
            self.lbl_level.config(text=dev["level"])
            if _changed:                       # 数字真的变了才淡入，不然每轮都闪
                self._fade_label_fg(self.lbl_level, FG)
            self.lbl_devsub.config(
                text="完整平衡化 %s 次｜看得见 %s 个标记"
                     % (dev.get("equil", "—"), dev.get("visible_n", "—")) + learning_line(_ROOT))
            self.lbl_rules.config(
                text="能行使的自我规则　%s"
                     % ("、".join(dev.get("self_rules") or []) or "—"))
        o = m.get("orientation") or 0
        self.lbl_reads.config(
            text="张力代理 %s/10　指向 %s\n动力代理 %s　偏好代理 %s（非生理测量）"
                 % (m.get("tension", "—"),
                    "朝外" if o > 0 else ("朝内" if o < 0 else "—"),
                    m.get("w", "—"), m.get("l", "—")))
        c = self.counts
        n, a = c["turns"], c["auditable"]
        _rt = "%.0f%%" % (100.0 * a / n) if n else "—"
        _rc = OK if n and a == n else (WARN if n else FG)
        _rch = self.lbl_rate.cget("text") != _rt
        self.lbl_rate.config(text=_rt, fg=_rc)
        if _rch:
            self._fade_label_fg(self.lbl_rate, _rc)
        self.lbl_rate_sub.config(text="管理员可审计 %d / %d" % (a, n))
        self._refresh_prob()

    def _refresh_prob(self) -> None:
        for w in self.prob_frame.winfo_children():
            w.destroy()
        probs = self.counts["problems"]
        if not probs:
            tk.Label(self.prob_frame, text="管理员暂未挑出问题", bg=CARD,
                     fg=FAINT, font=(F_UI, F_SUB)).pack(anchor="w")
        else:
            for k, v in sorted(probs.items(), key=lambda x: -x[1]):
                row = tk.Frame(self.prob_frame, bg=CARD)
                row.pack(fill="x", pady=1)
                tk.Label(row, text="●", bg=CARD, fg=PROBLEM_COLOR.get(k, DIM),
                         font=(F_UI, F_SUB)).pack(side="left")
                tk.Label(row, text=PROBLEM_CN.get(k, k), bg=CARD, fg=DIM,
                         font=(F_UI, F_SUB), width=8, anchor="w").pack(side="left")
                tk.Label(row, text=str(v), bg=CARD, fg=FG,
                         font=(F_NUM, F_SUB)).pack(side="right")
        if self.counts["flagged"]:
            tk.Label(self.prob_frame, text="我标了判错的：%d 轮" % self.counts["flagged"],
                     bg=CARD, fg=WARN, font=(F_UI, F_SUB)).pack(anchor="w", pady=(px(SP2), 0))

    # ------------------------------------------------------------ 管理员

    def on_review(self) -> None:
        try:
            import admin as A
            q = A.review()
        except Exception as e:                     # noqa: BLE001
            q = {"error": repr(e)[:200]}
        b = self.admin_text
        b.configure(state="normal")
        b.delete("1.0", "end")
        if q.get("error"):
            b.insert("end", "审核失败：%s" % q["error"])
        else:
            b.insert("end", "交流 %s 轮｜评价 %s 条\n" % (q.get("turns"), q.get("evals")))
            # ★ 数据指纹（用户裁定：「准确绑定生成时的数据基线；
            #   若基线变动，重算时显式标明「⚠️ 依据的数据已更新」」）
            #   放在**最上面** —— 它决定下面这批结论还算不算数。
            _fp = q.get("fingerprint") or {}
            if _fp:
                _vd = _fp.get("e_version_dist") or {}
                b.insert("end", "数据基线：%s ~ %s｜e_version=%s\n"
                         % ((_fp.get("first_ts") or "?")[:16],
                            (_fp.get("last_ts") or "?")[:16], _vd))
                # v1 数据下算出的结论，在 T33 换公式之后**已失效**（P003 的教训）
                if "2" not in _vd:
                    b.insert("end", "  ⚠️ 本批全是 v1（旧公式）数据 —— "
                                    "结论可能已失效，见各条标注\n")
            b.insert("end", "\n")
            packet = q.get("current_evidence") or {}
            latest = packet.get("latest_training") or {}
            if latest.get("run_id"):
                b.insert("end", "最新批：新增 %s／目标 %s 轮｜评价 %s 条\n" %
                         (latest.get("turns_added"), latest.get("requested_turns"), packet.get("latest_run_evaluations", 0)))
                if latest.get("failure"):
                    b.insert("end", "最新批中断：%s\n" % latest["failure"])
                if not latest.get("source_matches_current"):
                    b.insert("end", "最新批来自历史源码；当前改动以新验收为准。\n")
            if packet:
                b.insert("end", "当前评价版本 %s：%s 条；历史评价另列\n" %
                         (packet["current_eval_schema"], packet["current_schema_evaluations"]))
                for proof in packet.get("artefacts", []):
                    status = "当前版本通过" if proof["passed_for_current_source"] is True else "当前版本未通过" if proof["passed_for_current_source"] is False else "待当前版本重验"
                    b.insert("end", "  %s：%s\n" % (proof["kind"], status))
                b.insert("end", "\n")
            ps = q.get("proposals") or []
            b.insert("end", "改进建议 %d 条（尚待实施与验收）\n" % len(ps))
            b.insert("end", "此栏用于观察与复核；建议不会自动修改下一轮。\n")
            b.insert("end", "历史批准仅是授权记录，实施结果以任务验收为准。\n\n")
            for p in ps:
                b.insert("end", "  %s [%s] %s\n" % (p.get("pid"), p.get("trace"),
                                                    (p.get("summary") or "")[:56]))
                # ★ 「呈现」sid + 结案标注（用户裁定第 2 项原话：「结合结案记录**呈现**」）
                #   位次号 pid 只作序号；**sid 才是持久化主键**
                b.insert("end", "      sid=%s\n" % (p.get("sid") or "（无）"))
                _notes = p.get("notes") or []
                for _n in _notes:
                    b.insert("end", "      · %s\n" % _n)
                if not _notes:
                    b.insert("end", "      · （无历史）\n")
            b.insert("end", "\n事实层 %d 条\n" % len(q.get("facts") or []))
            for f in (q.get("facts") or [])[:6]:
                b.insert("end", "  · %s\n" % (f.get("title") or "")[:60])
            b.insert("end", "\n意见层（参与决策）%d 条\n" % len(q.get("opinions") or []))
            for f in (q.get("opinions") or [])[:4]:
                b.insert("end", "  · %s\n" % (f.get("title") or "")[:60])
        b.configure(state="disabled")


def main() -> int:
    global SC
    # ★ 顺序不能反：**先声明 DPI 感知，再建窗口**。
    #   反了就是"字糊"那个 bug —— 系统已经按低分辨率渲染过了，再声明也没用。
    SC = _make_dpi_aware()
    root = tk.Tk()
    # tk scaling = 每点多少像素 = DPI/72。设对了，字号才会映射到正确的物理大小。
    try:
        root.tk.call("tk", "scaling", (96.0 * SC) / 72.0)
    except Exception:                              # noqa: BLE001
        pass
    _setup_styles(root)                            # 第一期：深色 ttk 样式（纯外观）
    # ★ T23：**三处钩子必须在建界面之前装**（用户裁定全覆盖）
    #   ① sys.excepthook ② threading.excepthook ③ Tk.report_callback_exception
    #   ③ 尤其要紧：`after()` 回调里的异常 Tk 默认只打 stderr，
    #      而 windowed 下 stderr 是黑洞 ⇒ 实测是**静默卡死**，不是崩溃。
    CRASH.install(root)
    root.geometry("%dx%d" % (px(1280), px(800)))
    app = Studio(root)
    # ★ 崩溃感知：**不新增任何控件**，复用既有 alert bar 纯文本提示
    _prev = CRASH.latest()
    if _prev:
        try:
            _d = _prev["doc"]
            app._show_alert(
                "上次运行发生异常，已记录：state/crash/%s" % _prev["name"],
                impact="异常发生前的训练进度已落盘，可从断点继续。")
        except Exception:                          # noqa: BLE001
            pass
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
