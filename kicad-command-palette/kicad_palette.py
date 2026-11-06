"""Command palette for KiCad (Ctrl+P), similar to Obsidian.

Runs in the background (Windows only). When a KiCad window is focused, Ctrl+P
opens a fuzzy-search popup listing every menu command of that window together
with its shortcut. Selecting an entry triggers the menu item.
"""
import ctypes
import json
import os
import queue
import sys
import threading
from ctypes import wintypes

IS_WIN = sys.platform == "win32"

KICAD_PROCESSES = {
    "kicad.exe", "pcbnew.exe", "eeschema.exe", "gerbview.exe",
    "pl_editor.exe", "pcb_calculator.exe", "bitmap2component.exe",
}
RECENT_FILE = os.path.join(os.path.expanduser("~"), ".kicad_palette_recent.json")
MAX_RECENT = 50
LOG_FILE = os.path.join(os.environ.get("TEMP", os.path.expanduser("~")), "kicad_palette.log")
SEP = " › "


def log(msg):
    try:
        import time
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write("%s  %s\n" % (time.strftime("%H:%M:%S"), msg))
    except OSError:
        pass


# --------------------------------------------------------------------------
# Fuzzy search (token based, order independent, like Obsidian's quick switcher)
# --------------------------------------------------------------------------
_BOUNDARY = " -_/.:()›"


def _match_token(token, text):
    """Best subsequence match of token in text -> (score, [indices]) or None."""
    best = None
    first = token[0]
    for start in range(len(text)):
        if text[start] != first:
            continue
        idx = []
        pos = start
        ok = True
        for ch in token:
            pos = text.find(ch, pos)
            if pos < 0:
                ok = False
                break
            idx.append(pos)
            pos += 1
        if not ok:
            continue
        score = 0
        prev = -2
        for i in idx:
            score += 10
            if i == prev + 1:
                score += 15
            if i == 0 or text[i - 1] in _BOUNDARY:
                score += 20
            prev = i
        score -= min(idx[-1] - idx[0] - (len(idx) - 1), 30)
        if idx[0] == 0:
            score += 10
        if best is None or score > best[0]:
            best = (score, idx)
    return best


def fuzzy(query, label, path):
    """Return (score, label_match_indices) or None if not all tokens match."""
    tokens = query.lower().split()
    if not tokens:
        return 0, []
    low_label = label.lower()
    low_path = path.lower()
    total = 0
    hits = set()
    for tok in tokens:
        m = _match_token(tok, low_label)
        if m:
            total += m[0] * 2
            hits.update(m[1])
            continue
        m = _match_token(tok, low_path)
        if m:
            total += m[0]
            continue
        return None
    total -= len(label) // 4
    return total, sorted(hits)


# --------------------------------------------------------------------------
# Win32 helpers
# --------------------------------------------------------------------------
if IS_WIN:
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    LRESULT = ctypes.c_ssize_t
    HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

    user32.GetForegroundWindow.restype = ctypes.c_void_p
    user32.GetMenu.argtypes = [ctypes.c_void_p]
    user32.GetMenu.restype = ctypes.c_void_p
    user32.GetMenuItemCount.argtypes = [ctypes.c_void_p]
    user32.GetSubMenu.argtypes = [ctypes.c_void_p, ctypes.c_int]
    user32.GetSubMenu.restype = ctypes.c_void_p
    user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.DWORD)]
    user32.PostMessageW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
    user32.GetParent.argtypes = [ctypes.c_void_p]
    user32.GetParent.restype = ctypes.c_void_p
    user32.SetFocus.argtypes = [ctypes.c_void_p]
    user32.BringWindowToTop.argtypes = [ctypes.c_void_p]
    user32.AttachThreadInput.argtypes = [wintypes.DWORD, wintypes.DWORD, wintypes.BOOL]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    user32.GetWindowRect.argtypes = [ctypes.c_void_p, ctypes.POINTER(wintypes.RECT)]
    user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, ctypes.c_void_p, wintypes.DWORD]
    user32.SetWindowsHookExW.restype = ctypes.c_void_p
    user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = LRESULT
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = ctypes.c_void_p
    kernel32.QueryFullProcessImageNameW.argtypes = [
        ctypes.c_void_p, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.GetModuleHandleW.restype = ctypes.c_void_p

    class MENUITEMINFOW(ctypes.Structure):
        _fields_ = [
            ("cbSize", wintypes.UINT), ("fMask", wintypes.UINT), ("fType", wintypes.UINT),
            ("fState", wintypes.UINT), ("wID", wintypes.UINT), ("hSubMenu", ctypes.c_void_p),
            ("hbmpChecked", ctypes.c_void_p), ("hbmpUnchecked", ctypes.c_void_p),
            ("dwItemData", ctypes.c_size_t), ("dwTypeData", ctypes.c_void_p),
            ("cch", wintypes.UINT), ("hbmpItem", ctypes.c_void_p),
        ]

    class KBDLLHOOKSTRUCT(ctypes.Structure):
        _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                    ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.c_size_t)]

    user32.GetMenuItemInfoW.argtypes = [ctypes.c_void_p, wintypes.UINT, wintypes.BOOL,
                                        ctypes.POINTER(MENUITEMINFOW)]

    MIIM_STATE, MIIM_ID, MIIM_SUBMENU, MIIM_STRING, MIIM_FTYPE = 0x1, 0x2, 0x4, 0x40, 0x100
    MFT_SEPARATOR = 0x800
    WM_COMMAND, WM_KEYDOWN, WM_SYSKEYDOWN = 0x111, 0x100, 0x104
    VK_P, VK_SHIFT, VK_CONTROL, VK_MENU = 0x50, 0x10, 0x11, 0x12
    LLKHF_INJECTED = 0x10


def process_name(hwnd):
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    h = kernel32.OpenProcess(0x1000, False, pid.value)  # QUERY_LIMITED_INFORMATION
    if not h:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(520)
        size = wintypes.DWORD(520)
        if kernel32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(size)):
            return os.path.basename(buf.value).lower()
        return ""
    finally:
        kernel32.CloseHandle(h)


def kicad_window():
    """Foreground window handle if it is a KiCad window with a menu bar."""
    hwnd = user32.GetForegroundWindow()
    if not hwnd or process_name(hwnd) not in KICAD_PROCESSES:
        return None
    return hwnd if user32.GetMenu(hwnd) else None


def collect_commands(hwnd):
    """Walk the window's menu bar -> list of dicts(label, path, shortcut, id)."""
    out = []

    def walk(hmenu, path):
        for i in range(user32.GetMenuItemCount(hmenu)):
            mii = MENUITEMINFOW()
            mii.cbSize = ctypes.sizeof(mii)
            mii.fMask = MIIM_FTYPE | MIIM_ID | MIIM_SUBMENU | MIIM_STRING
            mii.dwTypeData = None
            if not user32.GetMenuItemInfoW(hmenu, i, True, ctypes.byref(mii)):
                continue
            if mii.fType & MFT_SEPARATOR:
                continue
            buf = ctypes.create_unicode_buffer(mii.cch + 1)
            mii.dwTypeData = ctypes.addressof(buf)
            mii.cch += 1
            user32.GetMenuItemInfoW(hmenu, i, True, ctypes.byref(mii))
            text, _, shortcut = buf.value.partition("\t")
            text = text.replace("&&", "\0").replace("&", "").replace("\0", "&").strip()
            if not text:
                continue
            if mii.hSubMenu:
                walk(mii.hSubMenu, path + [text])
            else:
                out.append({"label": text, "path": SEP.join(path),
                            "shortcut": shortcut.strip(), "id": mii.wID})

    bar = user32.GetMenu(hwnd)
    for i in range(user32.GetMenuItemCount(bar)):
        mii = MENUITEMINFOW()
        mii.cbSize = ctypes.sizeof(mii)
        mii.fMask = MIIM_STRING
        mii.dwTypeData = None
        user32.GetMenuItemInfoW(bar, i, True, ctypes.byref(mii))
        buf = ctypes.create_unicode_buffer(mii.cch + 1)
        mii.dwTypeData = ctypes.addressof(buf)
        mii.cch += 1
        user32.GetMenuItemInfoW(bar, i, True, ctypes.byref(mii))
        sub = user32.GetSubMenu(bar, i)
        if sub:
            walk(sub, [buf.value.replace("&", "").strip()])
    return out


def force_foreground(hwnd):
    """Bring hwnd to the foreground and give it keyboard focus.

    Windows only allows this for the thread owning the foreground window, so
    attach our input queue to it temporarily.
    """
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    me = kernel32.GetCurrentThreadId()
    attached = fg_thread and fg_thread != me and user32.AttachThreadInput(me, fg_thread, True)
    try:
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
        user32.SetFocus(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(me, fg_thread, False)


def window_rect(hwnd):
    r = wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def install_hook(events):
    """Low-level keyboard hook: swallow Ctrl+P while KiCad is focused."""
    def proc(n_code, w_param, l_param):
        if n_code == 0 and w_param in (WM_KEYDOWN, WM_SYSKEYDOWN):
            kb = ctypes.cast(l_param, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
            if (kb.vkCode == VK_P and not kb.flags & LLKHF_INJECTED
                    and user32.GetAsyncKeyState(VK_CONTROL) & 0x8000
                    and not user32.GetAsyncKeyState(VK_SHIFT) & 0x8000
                    and not user32.GetAsyncKeyState(VK_MENU) & 0x8000):
                hwnd = kicad_window()
                fg = user32.GetForegroundWindow()
                log("Ctrl+P: foreground=%r menu=%s -> %s" % (
                    process_name(fg) if fg else None, bool(fg and user32.GetMenu(fg)),
                    "palette" if hwnd else "ignored"))
                if hwnd:
                    events.put(hwnd)
                    return 1
        return user32.CallNextHookEx(None, n_code, w_param, l_param)

    cb = HOOKPROC(proc)

    def run():
        hook = user32.SetWindowsHookExW(13, cb, kernel32.GetModuleHandleW(None), 0)
        if not hook:
            log("SetWindowsHookExW failed: %s" % ctypes.WinError(ctypes.get_last_error()))
            return
        log("keyboard hook installed")
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))

    threading.Thread(target=run, daemon=True).start()
    return cb  # keep reference alive


# --------------------------------------------------------------------------
# Recently used
# --------------------------------------------------------------------------
def load_recent():
    try:
        with open(RECENT_FILE, encoding="utf-8") as f:
            return list(json.load(f))
    except Exception:
        return []


def save_recent(recent, key):
    recent = [key] + [r for r in recent if r != key]
    try:
        with open(RECENT_FILE, "w", encoding="utf-8") as f:
            json.dump(recent[:MAX_RECENT], f)
    except OSError:
        pass
    return recent[:MAX_RECENT]


# --------------------------------------------------------------------------
# UI
# --------------------------------------------------------------------------
def _build_ui_classes(wx):
    class ResultList(wx.VListBox):
        """Owner-drawn result list: highlighted label, dim menu path, right-aligned shortcut."""

        def __init__(self, parent, pal):
            super().__init__(parent, style=wx.BORDER_NONE)
            self.pal = pal
            self.SetBackgroundColour(pal.BG)
            self.f_norm = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Segoe UI")
            self.f_bold = wx.Font(11, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_BOLD, faceName="Segoe UI")
            self.f_small = wx.Font(9, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Segoe UI")
            self.f_key = wx.Font(9, wx.FONTFAMILY_TELETYPE, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Consolas")

        def OnMeasureItem(self, n):
            return self.FromDIP(30)

        def OnDrawBackground(self, dc, rect, n):
            dc.SetBrush(wx.Brush(self.pal.SEL if self.IsSelected(n) else self.pal.BG))
            dc.SetPen(wx.TRANSPARENT_PEN)
            dc.DrawRectangle(rect)

        def OnDrawItem(self, dc, rect, n):
            _, cmd, hits = self.pal.results[n]
            hits = set(hits)
            pad = self.FromDIP(12)
            x = rect.x + pad
            # right-aligned shortcut first, so the label never overlaps it
            right = rect.x + rect.width - pad
            if cmd["shortcut"]:
                dc.SetFont(self.f_key)
                dc.SetTextForeground(self.pal.DIM)
                w, h = dc.GetTextExtent(cmd["shortcut"])
                dc.DrawText(cmd["shortcut"], right - w, rect.y + (rect.height - h) // 2)
                right -= w + pad
            runs = []
            for i, ch in enumerate(cmd["label"]):
                is_hit = i in hits
                if runs and runs[-1][1] == is_hit:
                    runs[-1][0] += ch
                else:
                    runs.append([ch, is_hit])
            for text, is_hit in runs:
                dc.SetFont(self.f_bold if is_hit else self.f_norm)
                dc.SetTextForeground(self.pal.ACCENT if is_hit else self.pal.FG)
                w, h = dc.GetTextExtent(text)
                dc.DrawText(text, x, rect.y + (rect.height - h) // 2)
                x += w
            if cmd["path"] and x + pad < right:
                dc.SetFont(self.f_small)
                dc.SetTextForeground(self.pal.DIM)
                _, h = dc.GetTextExtent(cmd["path"])
                dc.SetClippingRegion(wx.Rect(x + pad, rect.y, max(right - x - pad, 1), rect.height))
                dc.DrawText(cmd["path"], x + pad, rect.y + (rect.height - h) // 2)
                dc.DestroyClippingRegion()

    class PaletteFrame(wx.Frame):
        def __init__(self, pal):
            super().__init__(None, style=wx.FRAME_NO_TASKBAR | wx.STAY_ON_TOP | wx.BORDER_NONE)
            self.pal = pal
            self.SetBackgroundColour(pal.ACCENT)  # 1px accent border
            inner = wx.Panel(self)
            inner.SetBackgroundColour(pal.BG)
            self.entry = wx.TextCtrl(inner, style=wx.TE_PROCESS_ENTER | wx.BORDER_NONE)
            self.entry.SetBackgroundColour(pal.BG)
            self.entry.SetForegroundColour(pal.FG)
            self.entry.SetFont(wx.Font(13, wx.FONTFAMILY_DEFAULT, wx.FONTSTYLE_NORMAL, wx.FONTWEIGHT_NORMAL, faceName="Segoe UI"))
            line = wx.Panel(inner, size=(-1, 1))
            line.SetBackgroundColour("#55555e")
            self.list = ResultList(inner, pal)
            box = wx.BoxSizer(wx.VERTICAL)
            box.Add(self.entry, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP | wx.BOTTOM, self.FromDIP(12))
            box.Add(line, 0, wx.EXPAND)
            box.Add(self.list, 1, wx.EXPAND)
            inner.SetSizer(box)
            outer = wx.BoxSizer(wx.VERTICAL)
            outer.Add(inner, 1, wx.EXPAND | wx.ALL, 1)
            self.SetSizer(outer)
            self.SetClientSize(self.FromDIP(wx.Size(pal.W, 50 + 30 * pal.ROWS)))
            self.SetTransparent(int(255 * pal.ALPHA))
            self.armed = False
            self.entry.Bind(wx.EVT_TEXT, lambda e: pal.refresh())
            self.entry.Bind(wx.EVT_KEY_DOWN, self.on_key)
            self.entry.Bind(wx.EVT_TEXT_ENTER, lambda e: pal.run())
            self.list.Bind(wx.EVT_LISTBOX, lambda e: pal.run() if self.armed else None)
            self.Bind(wx.EVT_ACTIVATE, self.on_activate)

        def on_key(self, e):
            k, ctrl = e.GetKeyCode(), e.ControlDown()
            pal = self.pal
            if k == wx.WXK_ESCAPE:
                pal.close()
            elif k in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
                pal.run()
            elif k == wx.WXK_DOWN or (ctrl and k in (ord("J"), ord("N"))):
                pal.move(1)
            elif k == wx.WXK_UP or (ctrl and k in (ord("K"), ord("P"))):
                pal.move(-1)
            elif k == wx.WXK_PAGEDOWN:
                pal.move(pal.ROWS)
            elif k == wx.WXK_PAGEUP:
                pal.move(-pal.ROWS)
            else:
                e.Skip()

        def on_activate(self, e):
            if not e.GetActive() and self.armed and self.IsShown():
                self.Hide()
            e.Skip()

    return PaletteFrame


class Palette:
    W, ROWS = 680, 12
    BG, FG, DIM = "#3a3a42", "#ececf0", "#a0a2ab"
    ACCENT, SEL = "#b9a3ff", "#55509a"
    ALPHA = 0.93

    def __init__(self, wx):
        self.wx = wx
        self.app = wx.App(False)
        self.frame = _build_ui_classes(wx)(self)
        self.hwnd = None
        self.commands = []
        self.results = []
        self.recent = load_recent()
        self.events = queue.Queue()
        self.timer = wx.Timer(self.frame)
        self.frame.Bind(wx.EVT_TIMER, self.poll, self.timer)
        self.timer.Start(25)

    def poll(self, _e=None):
        try:
            while True:
                self.open(self.events.get_nowait())
        except queue.Empty:
            pass

    def open(self, hwnd):
        wx, f = self.wx, self.frame
        if f.IsShown():
            return
        self.hwnd = hwnd
        self.commands = collect_commands(hwnd)
        rank = {k: i for i, k in enumerate(self.recent)}
        for c in self.commands:
            c["key"] = c["path"] + SEP + c["label"]
            c["rank"] = rank.get(c["key"], len(rank) + 1)
        f.armed = False
        f.entry.ChangeValue("")
        self.refresh()
        x, y, w, h = window_rect(hwnd)
        fw = f.GetSize().GetWidth()
        f.SetPosition(wx.Point(x + (w - fw) // 2, y + h // 6))
        f.Show()
        f.Raise()
        for delay in (0, 40, 120):
            wx.CallLater(delay, self.grab_focus)
        wx.CallLater(250, lambda: setattr(f, "armed", True))

    def grab_focus(self):
        if self.frame.IsShown():
            force_foreground(self.frame.GetHandle())
            self.frame.entry.SetFocus()

    def close(self):
        self.frame.Hide()
        if self.hwnd:
            user32.SetForegroundWindow(self.hwnd)

    def refresh(self):
        q = self.frame.entry.GetValue()
        res = []
        for c in self.commands:
            m = fuzzy(q, c["label"], c["path"])
            if m:
                res.append((m[0], c, m[1]))
        if q.strip():
            res.sort(key=lambda r: (-r[0], r[1]["rank"]))
        else:
            res.sort(key=lambda r: r[1]["rank"])
        self.results = res[:200]
        lst = self.frame.list
        lst.SetItemCount(len(self.results))
        lst.SetSelection(0 if self.results else self.wx.NOT_FOUND)
        lst.RefreshAll()

    def move(self, d):
        lst = self.frame.list
        if self.results:
            lst.SetSelection(max(0, min(len(self.results) - 1, lst.GetSelection() + d)))

    def run(self):
        sel = self.frame.list.GetSelection()
        if sel == self.wx.NOT_FOUND or sel >= len(self.results):
            return
        cmd = self.results[sel][1]
        self.recent = save_recent(self.recent, cmd["key"])
        hwnd = self.hwnd
        self.close()
        # give KiCad a moment to regain focus before triggering the command
        self.wx.CallLater(80, lambda: user32.PostMessageW(hwnd, WM_COMMAND, cmd["id"], 0))


def kicad_running():
    import subprocess
    try:
        out = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                             creationflags=0x08000000).stdout.lower()
    except Exception:
        return True
    return any('"%s"' % name in out for name in KICAD_PROCESSES)


def main():
    if not IS_WIN:
        sys.exit("kicad_palette läuft nur unter Windows.")
    # single instance
    kernel32.CreateMutexW.restype = ctypes.c_void_p
    _mutex = kernel32.CreateMutexW(None, False, "KiCadCommandPaletteSingleton")
    if ctypes.get_last_error() == 183:  # ERROR_ALREADY_EXISTS
        log("already running, exiting")
        return
    log("started (pid %d, %s)" % (os.getpid(), sys.executable))
    sys.excepthook = lambda *a: log("uncaught: %r" % (a[1],))
    import wx
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    pal = Palette(wx)
    _keep = install_hook(pal.events)
    if "--exit-with-kicad" in sys.argv:
        def watch():
            if not kicad_running():
                pal.app.ExitMainLoop()
                return
            wx.CallLater(10000, watch)
        wx.CallLater(60000, watch)
    pal.app.MainLoop()


if __name__ == "__main__":
    main()
