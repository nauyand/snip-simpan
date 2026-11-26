#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SnipSimpan — alat screenshot yang langsung menyimpan ke folder pilihan Anda.

Fitur
  • Layar penuh, pilih area (seperti Snipping Tool), ulangi area terakhir, jendela aktif
  • Hotkey global yang bisa diatur sendiri (tetap jalan walau jendela disembunyikan di tray)
  • Langsung tersimpan tanpa dialog: tekan berkali-kali, file terus bertambah di folder
  • Mode otomatis: screenshot berulang setiap N detik
  • Pola nama file: {tanggal} {jam} {nomor} {mode}
  • Kamera HP: buka alamat/QR di browser HP (Wi-Fi yang sama), foto langsung masuk ke folder PC

Kebutuhan : Python 3.9+, PySide6 dan segno  ->  pip install PySide6 segno
Jalankan  : python snipsimpan.py      (atau pythonw snipsimpan.py tanpa jendela konsol)

Hotkey global memakai Windows API (RegisterHotKey), jadi hanya aktif di Windows.
"""
from __future__ import annotations

import getpass
import hmac
import json
import math
import os
import random
import re
import secrets
import socket
import socketserver
import struct
import subprocess
import sys
import threading
import traceback
import wave
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, quote, urlsplit

from PySide6.QtCore import (
    QDir, QObject, QPoint, QPointF, QRect, QRectF, QSize, QStandardPaths, Qt, QTimer, QUrl, Signal,
)
from PySide6.QtGui import (
    QAction, QColor, QCursor, QDesktopServices, QFont, QGuiApplication, QIcon, QImage,
    QImageReader, QPainter, QPen, QPixmap, QRegion, QScreen,
)
from PySide6.QtNetwork import QAbstractSocket, QLocalServer, QLocalSocket, QNetworkInterface
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QGridLayout, QGroupBox,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
    QMessageBox, QPushButton, QSpinBox, QSystemTrayIcon, QTabWidget, QToolButton,
    QVBoxLayout, QWidget,
)

APP_NAME = "SnipSimpan"
IS_WINDOWS = sys.platform == "win32"

# ─────────────────────────────────────────────────────────────────────────────
# Windows API (hotkey global + jendela aktif)
# ─────────────────────────────────────────────────────────────────────────────
MOD_ALT, MOD_CONTROL, MOD_SHIFT, MOD_WIN, MOD_NOREPEAT = 0x0001, 0x0002, 0x0004, 0x0008, 0x4000
WM_QUIT, WM_HOTKEY, WM_USER = 0x0012, 0x0312, 0x0400
PM_NOREMOVE = 0x0000
ERROR_HOTKEY_ALREADY_REGISTERED = 1409
DWMWA_EXTENDED_FRAME_BOUNDS = 9

if IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _dwmapi = ctypes.WinDLL("dwmapi")

    _user32.RegisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT]
    _user32.RegisterHotKey.restype = wintypes.BOOL
    _user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.UnregisterHotKey.restype = wintypes.BOOL
    _user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
    _user32.GetMessageW.restype = wintypes.BOOL
    _user32.PeekMessageW.argtypes = [
        ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT, wintypes.UINT,
    ]
    _user32.PeekMessageW.restype = wintypes.BOOL
    _user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    _user32.PostThreadMessageW.restype = wintypes.BOOL
    _user32.GetForegroundWindow.argtypes = []
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.IsIconic.argtypes = [wintypes.HWND]
    _user32.IsIconic.restype = wintypes.BOOL
    _user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    _user32.GetWindowRect.restype = wintypes.BOOL
    _kernel32.GetCurrentThreadId.argtypes = []
    _kernel32.GetCurrentThreadId.restype = wintypes.DWORD
    _dwmapi.DwmGetWindowAttribute.argtypes = [wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD]
    _dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long


# ─────────────────────────────────────────────────────────────────────────────
# Model hotkey: modifier + virtual-key code Windows
# ─────────────────────────────────────────────────────────────────────────────
VK_SNAPSHOT, VK_PAUSE, VK_SCROLL = 0x2C, 0x13, 0x91

VK_NAMES: Dict[int, str] = {}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789":
    VK_NAMES[ord(_c)] = _c
for _i in range(1, 25):
    VK_NAMES[0x6F + _i] = f"F{_i}"
for _i in range(10):
    VK_NAMES[0x60 + _i] = f"Num{_i}"
VK_NAMES.update({
    VK_SNAPSHOT: "PrintScreen", VK_PAUSE: "Pause", VK_SCROLL: "ScrollLock",
    0x2D: "Insert", 0x2E: "Delete", 0x24: "Home", 0x23: "End", 0x21: "PageUp", 0x22: "PageDown",
    0x25: "Left", 0x26: "Up", 0x27: "Right", 0x28: "Down",
    0x20: "Space", 0x09: "Tab", 0x0D: "Enter", 0x08: "Backspace", 0x1B: "Esc",
    0x6A: "NumMultiply", 0x6B: "NumAdd", 0x6D: "NumSubtract", 0x6E: "NumDecimal", 0x6F: "NumDivide",
    0xBA: ";", 0xBB: "=", 0xBC: ",", 0xBD: "-", 0xBE: ".", 0xBF: "/", 0xC0: "`",
    0xDB: "[", 0xDC: "\\", 0xDD: "]", 0xDE: "'",
})
NAME_TO_VK = {name.lower(): vk for vk, name in VK_NAMES.items()}
SOLO_KEYS = {VK_SNAPSHOT, VK_PAUSE, VK_SCROLL, *range(0x70, 0x88)}   # boleh tanpa Ctrl/Alt
MOD_ORDER = ((MOD_CONTROL, "Ctrl"), (MOD_ALT, "Alt"), (MOD_SHIFT, "Shift"), (MOD_WIN, "Win"))
MOD_ALIASES = {"ctrl": MOD_CONTROL, "control": MOD_CONTROL, "alt": MOD_ALT, "shift": MOD_SHIFT,
               "win": MOD_WIN, "windows": MOD_WIN, "meta": MOD_WIN}


@dataclass(frozen=True)
class Hotkey:
    mods: int
    vk: int

    def __str__(self) -> str:
        parts = [name for bit, name in MOD_ORDER if self.mods & bit]
        parts.append(VK_NAMES.get(self.vk, f"VK{self.vk:02X}"))
        return "+".join(parts)

    @property
    def is_valid(self) -> bool:
        # Tanpa Ctrl/Alt/Win, tombol biasa akan "mencuri" ketikan, jadi hanya tombol khusus yang boleh.
        return bool(self.mods & (MOD_CONTROL | MOD_ALT | MOD_WIN)) or self.vk in SOLO_KEYS

    @staticmethod
    def parse(text: str) -> Optional["Hotkey"]:
        if not text or not text.strip():
            return None
        mods, vk = 0, None
        for part in (p.strip().lower() for p in text.split("+")):
            if not part:
                continue
            if part in MOD_ALIASES:
                mods |= MOD_ALIASES[part]
            elif vk is None and part in NAME_TO_VK:
                vk = NAME_TO_VK[part]
            else:
                return None
        return Hotkey(mods, vk) if vk is not None else None


def _iv(x) -> int:
    """Nilai int dari enum Qt (aman untuk berbagai versi PySide6)."""
    try:
        return int(x)
    except TypeError:
        return int(x.value)


K = Qt.Key
KEY_ESCAPE, KEY_BACKSPACE, KEY_DELETE = _iv(K.Key_Escape), _iv(K.Key_Backspace), _iv(K.Key_Delete)
KEY_PRINT, KEY_SYSREQ, KEY_F1 = _iv(K.Key_Print), _iv(K.Key_SysReq), _iv(K.Key_F1)
MODIFIER_KEYS = {_iv(k) for k in (K.Key_Shift, K.Key_Control, K.Key_Alt, K.Key_AltGr, K.Key_Meta,
                                  K.Key_Super_L, K.Key_Super_R, K.Key_CapsLock, K.Key_NumLock)}
_QT_TO_VK = {_iv(k): v for k, v in {
    K.Key_Print: VK_SNAPSHOT, K.Key_SysReq: VK_SNAPSHOT, K.Key_Pause: VK_PAUSE, K.Key_ScrollLock: VK_SCROLL,
    K.Key_Insert: 0x2D, K.Key_Delete: 0x2E, K.Key_Home: 0x24, K.Key_End: 0x23,
    K.Key_PageUp: 0x21, K.Key_PageDown: 0x22,
    K.Key_Left: 0x25, K.Key_Up: 0x26, K.Key_Right: 0x27, K.Key_Down: 0x28,
    K.Key_Space: 0x20, K.Key_Tab: 0x09, K.Key_Return: 0x0D, K.Key_Enter: 0x0D,
    K.Key_Backspace: 0x08, K.Key_Escape: 0x1B,
    K.Key_Semicolon: 0xBA, K.Key_Colon: 0xBA, K.Key_Equal: 0xBB, K.Key_Plus: 0xBB,
    K.Key_Comma: 0xBC, K.Key_Less: 0xBC, K.Key_Minus: 0xBD, K.Key_Underscore: 0xBD,
    K.Key_Period: 0xBE, K.Key_Greater: 0xBE, K.Key_Slash: 0xBF, K.Key_Question: 0xBF,
    K.Key_QuoteLeft: 0xC0, K.Key_AsciiTilde: 0xC0, K.Key_BracketLeft: 0xDB, K.Key_BraceLeft: 0xDB,
    K.Key_Backslash: 0xDC, K.Key_Bar: 0xDC, K.Key_BracketRight: 0xDD, K.Key_BraceRight: 0xDD,
    K.Key_Apostrophe: 0xDE, K.Key_QuoteDbl: 0xDE,
    # Shift + angka dilaporkan Qt sebagai simbolnya (layout US) -> kembalikan ke tombol angka
    K.Key_Exclam: 0x31, K.Key_At: 0x32, K.Key_NumberSign: 0x33, K.Key_Dollar: 0x34,
    K.Key_Percent: 0x35, K.Key_AsciiCircum: 0x36, K.Key_Ampersand: 0x37, K.Key_Asterisk: 0x38,
    K.Key_ParenLeft: 0x39, K.Key_ParenRight: 0x30,
}.items()}
_KEYPAD_TO_VK = {_iv(k): v for k, v in {
    K.Key_Asterisk: 0x6A, K.Key_Plus: 0x6B, K.Key_Minus: 0x6D, K.Key_Period: 0x6E,
    K.Key_Slash: 0x6F, K.Key_Enter: 0x0D,
}.items()}


def qt_key_to_vk(key: int, keypad: bool) -> Optional[int]:
    if keypad and key in _KEYPAD_TO_VK:
        return _KEYPAD_TO_VK[key]
    if 0x41 <= key <= 0x5A:                       # A–Z: kode Qt = kode VK
        return key
    if 0x30 <= key <= 0x39:                       # 0–9
        return 0x60 + key - 0x30 if keypad else key
    if KEY_F1 <= key < KEY_F1 + 24:
        return 0x70 + key - KEY_F1
    return _QT_TO_VK.get(key)


def qt_mods_to_win(mods) -> int:
    out = 0
    if mods & Qt.KeyboardModifier.ControlModifier:
        out |= MOD_CONTROL
    if mods & Qt.KeyboardModifier.AltModifier:
        out |= MOD_ALT
    if mods & Qt.KeyboardModifier.ShiftModifier:
        out |= MOD_SHIFT
    if mods & Qt.KeyboardModifier.MetaModifier:
        out |= MOD_WIN
    return out


def event_vk(event) -> Optional[int]:
    if IS_WINDOWS:
        vk = int(event.nativeVirtualKey())        # di Windows ini langsung kode VK, tidak terpengaruh Shift
        if vk in VK_NAMES:
            return vk
    keypad = bool(event.modifiers() & Qt.KeyboardModifier.KeypadModifier)
    return qt_key_to_vk(_iv(event.key()), keypad)


# ─────────────────────────────────────────────────────────────────────────────
# Pengaturan (disimpan sebagai JSON)
# ─────────────────────────────────────────────────────────────────────────────
ACTIONS = [
    ("full", "Layar penuh"),
    ("region", "Pilih area"),
    ("repeat", "Ulangi area terakhir"),
    ("window", "Jendela aktif"),
    ("auto", "Mulai / stop otomatis"),
]
ACTION_LABEL = dict(ACTIONS)
MODE_TOKEN = {"full": "layar", "region": "area", "repeat": "area", "window": "jendela", "camera": "kamera"}
FULL_TARGETS = [("cursor", "Monitor tempat kursor berada"), ("all", "Semua monitor (digabung)"),
                ("primary", "Monitor utama")]
AUTO_MODES = [("full", "Layar penuh"), ("repeat", "Area terakhir"), ("window", "Jendela aktif")]
DEFAULT_HOTKEYS = {"full": "Ctrl+Alt+1", "region": "Ctrl+Alt+2", "repeat": "Ctrl+Alt+3",
                   "window": "Ctrl+Alt+4", "auto": "Ctrl+Alt+5"}


def default_folder() -> str:
    pics = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.PicturesLocation)
    return QDir.toNativeSeparators(str(Path(pics or Path.home()) / APP_NAME))


def make_defaults() -> dict:
    return {
        "folder": default_folder(),
        "template": "Screenshot_{tanggal}_{jam}",
        "format": "PNG",
        "jpg_quality": 90,
        "date_subfolder": False,
        "counter": 1,
        "fullscreen_target": "cursor",
        "delay": 0,
        "auto_interval": 5,
        "auto_mode": "full",
        "hide_window": True,
        "copy_clipboard": False,
        "notify": True,
        "sound": True,
        "close_to_tray": True,
        "start_hidden": False,
        "last_region": None,
        "hotkeys": dict(DEFAULT_HOTKEYS),
        "camera_port": 8765,
        "camera_token": "",
        "camera_ip": "",
        "camera_autostart": False,
        "camera_template": "Foto_{tanggal}_{jam}",
    }


class Config(dict):
    def __init__(self, path: Path):
        super().__init__(make_defaults())
        self.path = path
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if key == "hotkeys" and isinstance(value, dict):
                for action, text in value.items():
                    if action in self["hotkeys"] and isinstance(text, str):
                        self["hotkeys"][action] = text
            elif key == "last_region":
                self[key] = value if isinstance(value, dict) else None
            elif key in self and type(value) is type(self[key]):
                self[key] = value

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self, indent=2, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, self.path)
        except OSError:
            pass


_INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def render_name(template: str, now: datetime, counter: int, mode: str) -> str:
    name = (template or "").strip() or "Screenshot_{tanggal}_{jam}"
    name = (name.replace("{tanggal}", now.strftime("%Y-%m-%d"))
                .replace("{jam}", now.strftime("%H-%M-%S"))
                .replace("{nomor}", f"{counter:04d}")
                .replace("{mode}", mode))
    name = _INVALID_CHARS.sub("_", name).strip(" .")
    return name or "Screenshot"


class CaptureError(Exception):
    """Kesalahan yang pesannya aman ditampilkan ke pengguna."""


# ─────────────────────────────────────────────────────────────────────────────
# Pengambilan gambar layar
# ─────────────────────────────────────────────────────────────────────────────
def grab_screen(screen: QScreen) -> QImage:
    img = screen.grabWindow(0).toImage().convertToFormat(QImage.Format.Format_RGB32)
    img.setDevicePixelRatio(1.0)
    return img


def screen_under_cursor() -> QScreen:
    return QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()


def grab_virtual_desktop() -> Tuple[QImage, QPoint]:
    """Gabungan semua monitor dalam piksel fisik. Mengembalikan (gambar, titik asal desktop)."""
    parts = []
    for screen in QGuiApplication.screens():
        img = grab_screen(screen)
        # Di Qt 6 / Windows, pojok kiri-atas QScreen.geometry() sama dengan koordinat fisiknya.
        parts.append((QRect(screen.geometry().topLeft(), img.size()), img))
    bounds = QRect()
    for rect, _ in parts:
        bounds = bounds.united(rect)
    canvas = QImage(bounds.size(), QImage.Format.Format_RGB32)
    canvas.fill(QColor("black"))
    painter = QPainter(canvas)
    for rect, img in parts:
        painter.drawImage(rect.topLeft() - bounds.topLeft(), img)
    painter.end()
    return canvas, bounds.topLeft()


def grab_active_window() -> QImage:
    if not IS_WINDOWS:
        raise CaptureError("Mode jendela aktif hanya tersedia di Windows")
    hwnd = _user32.GetForegroundWindow()
    if not hwnd or _user32.IsIconic(hwnd):
        raise CaptureError("Tidak ada jendela aktif")
    rect = wintypes.RECT()
    if _dwmapi.DwmGetWindowAttribute(hwnd, DWMWA_EXTENDED_FRAME_BOUNDS,
                                     ctypes.byref(rect), ctypes.sizeof(rect)) != 0:
        if not _user32.GetWindowRect(hwnd, ctypes.byref(rect)):
            raise CaptureError("Ukuran jendela aktif tidak terbaca")
    win_rect = QRect(rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)
    canvas, origin = grab_virtual_desktop()
    crop = win_rect.translated(-origin.x(), -origin.y()).intersected(canvas.rect())
    if crop.width() < 2 or crop.height() < 2:
        raise CaptureError("Jendela aktif berada di luar layar")
    return canvas.copy(crop)


# ─────────────────────────────────────────────────────────────────────────────
# Hotkey global (Windows RegisterHotKey di thread sendiri)
# ─────────────────────────────────────────────────────────────────────────────
class GlobalHotkeys(QObject):
    activated = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._thread: Optional[threading.Thread] = None
        self._thread_id = 0

    def start(self, bindings: Dict[str, Hotkey]) -> Dict[str, Optional[str]]:
        """Daftarkan hotkey. Hasil: {aksi: None jika berhasil, atau pesan galat}."""
        self.stop()
        if not bindings:
            return {}
        if not IS_WINDOWS:
            return {action: "Hotkey global hanya untuk Windows" for action in bindings}

        results: Dict[str, Optional[str]] = {}
        ready = threading.Event()
        items = list(bindings.items())

        def run() -> None:
            ids: Dict[int, str] = {}
            msg = wintypes.MSG()
            try:
                self._thread_id = _kernel32.GetCurrentThreadId()
                # Pastikan antrean pesan thread sudah ada sebelum PostThreadMessage dipakai.
                _user32.PeekMessageW(ctypes.byref(msg), None, WM_USER, WM_USER, PM_NOREMOVE)
                for hotkey_id, (action, hk) in enumerate(items, start=1):
                    if _user32.RegisterHotKey(None, hotkey_id, hk.mods | MOD_NOREPEAT, hk.vk):
                        ids[hotkey_id] = action
                        results[action] = None
                    else:
                        err = ctypes.get_last_error()
                        results[action] = ("Sudah dipakai aplikasi lain / Windows"
                                           if err == ERROR_HOTKEY_ALREADY_REGISTERED
                                           else f"Gagal didaftarkan (kode {err})")
            finally:
                ready.set()
            try:
                while _user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                    if msg.message == WM_HOTKEY:
                        action = ids.get(int(msg.wParam))
                        if action:
                            self.activated.emit(action)   # diantrekan ke thread GUI oleh Qt
            finally:
                for hotkey_id in ids:
                    _user32.UnregisterHotKey(None, hotkey_id)

        self._thread = threading.Thread(target=run, name="SnipSimpan-hotkeys", daemon=True)
        self._thread.start()
        ready.wait(3)
        return dict(results)

    def stop(self) -> None:
        thread, self._thread = self._thread, None
        if thread is not None and thread.is_alive():
            _user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            thread.join(2)


# ─────────────────────────────────────────────────────────────────────────────
# Widget perekam hotkey
# ─────────────────────────────────────────────────────────────────────────────
class HotkeyEdit(QLineEdit):
    changed = Signal()
    recording = Signal(bool)

    IDLE_HINT = "Nonaktif — klik untuk mengatur"
    REC_HINT = "Tekan kombinasi tombol…"

    def __init__(self, parent=None):
        super().__init__(parent)
        self._hotkey: Optional[Hotkey] = None
        self.setReadOnly(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPlaceholderText(self.IDLE_HINT)
        self.setMinimumWidth(200)
        self.setToolTip("Klik, lalu tekan kombinasi tombol.\nEsc = batal · Backspace = nonaktifkan")

    def hotkey(self) -> Optional[Hotkey]:
        return self._hotkey

    def setHotkey(self, hotkey: Optional[Hotkey]) -> None:
        self._hotkey = hotkey
        self._show_current()

    def _show_current(self) -> None:
        self.setText(str(self._hotkey) if self._hotkey else "")

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.setPlaceholderText(self.REC_HINT)
        self.setText("")
        self.setStyleSheet("QLineEdit { border: 2px solid #2563eb; border-radius: 3px; }")
        self.recording.emit(True)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.setPlaceholderText(self.IDLE_HINT)
        self.setStyleSheet("")
        self._show_current()
        self.recording.emit(False)

    def keyPressEvent(self, event):
        self._on_key(event)

    def keyReleaseEvent(self, event):
        key = _iv(event.key())
        is_print = key in (KEY_PRINT, KEY_SYSREQ) or (IS_WINDOWS and event.nativeVirtualKey() == VK_SNAPSHOT)
        if is_print:
            self._on_key(event)          # Windows hanya mengirim "lepas" untuk tombol PrintScreen
        elif key in MODIFIER_KEYS:
            self._show_partial(qt_mods_to_win(event.modifiers()))

    def _show_partial(self, mods: int) -> None:
        names = [name for bit, name in MOD_ORDER if mods & bit]
        self.setText("+".join(names) + "+…" if names else "")

    def _on_key(self, event) -> None:
        if event.isAutoRepeat():
            return
        key = _iv(event.key())
        mods = qt_mods_to_win(event.modifiers())
        if key in MODIFIER_KEYS:
            self._show_partial(mods)
            return
        if not mods and key == KEY_ESCAPE:
            self.clearFocus()
            return
        if not mods and key in (KEY_BACKSPACE, KEY_DELETE):
            self._hotkey = None
            self.changed.emit()
            self.clearFocus()
            return
        vk = event_vk(event)
        if vk is None or vk not in VK_NAMES:
            self.setText("Tombol ini tidak didukung")
            return
        hotkey = Hotkey(mods, vk)
        if not hotkey.is_valid:
            self.setText(f"{hotkey}  ← tambahkan Ctrl / Alt")
            return
        self._hotkey = hotkey
        self.changed.emit()
        self.clearFocus()


# ─────────────────────────────────────────────────────────────────────────────
# Layar pilih area (satu per monitor, menampilkan layar yang "dibekukan")
# ─────────────────────────────────────────────────────────────────────────────
class RegionOverlay(QWidget):
    selected = Signal(QImage, str, QRect)     # gambar, nama monitor, area (piksel fisik)
    cancelled = Signal()

    def __init__(self, screen: QScreen, shot: QPixmap):
        flags = Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool
        super().__init__(None, flags)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.CrossCursor)
        self.setWindowTitle(f"{APP_NAME} — pilih area")
        self.target_screen = screen
        self.shot = shot
        self.origin: Optional[QPoint] = None
        self.sel = QRect()
        self.mouse = QPoint(-1, -1)

    def open_on_screen(self) -> None:
        geo = self.target_screen.geometry()
        self.setGeometry(geo)
        self.winId()                               # buat jendela native agar bisa dipindah monitor
        if self.windowHandle() is not None:
            self.windowHandle().setScreen(self.target_screen)
        self.setGeometry(geo)
        self.show()

    # ---- gambar ----
    def paintEvent(self, _event):
        p = QPainter(self)
        p.drawPixmap(self.rect(), self.shot)
        shade = QColor(0, 0, 0, 120)
        sel = self.sel.normalized()
        if sel.width() > 1 and sel.height() > 1:
            p.setClipRegion(QRegion(self.rect()).subtracted(QRegion(sel)))
            p.fillRect(self.rect(), shade)
            p.setClipping(False)
            p.setPen(QPen(QColor(37, 99, 235), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(sel.adjusted(0, 0, -1, -1))
            dpr = self.shot.devicePixelRatio()
            size_text = f"{round(sel.width() * dpr)} × {round(sel.height() * dpr)}"
            self._label(p, size_text, sel.bottomLeft() + QPoint(0, 8))
        else:
            p.fillRect(self.rect(), shade)
        if self.origin is None:
            if self.rect().contains(self.mouse):
                p.setPen(QPen(QColor(255, 255, 255, 110), 1, Qt.PenStyle.DashLine))
                p.drawLine(0, self.mouse.y(), self.width(), self.mouse.y())
                p.drawLine(self.mouse.x(), 0, self.mouse.x(), self.height())
            self._label(p, "Seret untuk memilih area   ·   Esc / klik kanan = batal", None)
        p.end()

    def _label(self, p: QPainter, text: str, anchor: Optional[QPoint]) -> None:
        font = QFont(self.font())
        font.setBold(True)
        font.setPointSizeF(max(10.0, font.pointSizeF()))
        p.setFont(font)
        fm = p.fontMetrics()
        box = QRect(0, 0, fm.horizontalAdvance(text) + 20, fm.height() + 10)
        if anchor is None:
            box.moveTo((self.width() - box.width()) // 2, 24)
        else:
            box.moveTo(anchor)
            if box.bottom() > self.height() - 4:
                box.moveBottom(self.height() - 4)
            if box.right() > self.width() - 4:
                box.moveRight(self.width() - 4)
            box.moveLeft(max(4, box.left()))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(15, 23, 42, 225))
        p.drawRoundedRect(box, 6, 6)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    # ---- mouse & keyboard ----
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            self.cancelled.emit()
        elif event.button() == Qt.MouseButton.LeftButton:
            self.origin = event.position().toPoint()
            self.sel = QRect(self.origin, self.origin)
            self.update()

    def mouseMoveEvent(self, event):
        self.mouse = event.position().toPoint()
        if self.origin is not None:
            self.sel = QRect(self.origin, self.mouse).normalized()
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or self.origin is None:
            return
        sel = QRect(self.origin, event.position().toPoint()).normalized()
        self.origin = None
        if sel.width() < 4 or sel.height() < 4:   # klik tanpa seret -> abaikan
            self.sel = QRect()
            self.update()
            return
        dpr = self.shot.devicePixelRatio()
        native = QRect(round(sel.x() * dpr), round(sel.y() * dpr),
                       round(sel.width() * dpr), round(sel.height() * dpr))
        native = native.intersected(QRect(QPoint(0, 0), self.shot.size()))
        img = self.shot.copy(native).toImage().convertToFormat(QImage.Format.Format_RGB32)
        img.setDevicePixelRatio(1.0)
        self.selected.emit(img, self.target_screen.name(), native)

    def keyPressEvent(self, event):
        if _iv(event.key()) == KEY_ESCAPE:
            self.cancelled.emit()


# ─────────────────────────────────────────────────────────────────────────────
# Ikon & suara
# ─────────────────────────────────────────────────────────────────────────────
_APP_ICON: Optional[QIcon] = None


def app_icon() -> QIcon:
    global _APP_ICON
    if _APP_ICON is None:
        icon = QIcon()
        for size in (16, 20, 24, 32, 40, 48, 64, 128, 256):
            pm = QPixmap(size, size)
            pm.fill(Qt.GlobalColor.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("#2563eb"))
            p.drawRoundedRect(QRectF(0, 0, size, size), size * 0.22, size * 0.22)
            pen = QPen(QColor("white"), max(1.6, size * 0.085))
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            a, b, length = size * 0.24, size * 0.76, size * 0.17
            for x, y, dx, dy in ((a, a, 1, 1), (b, a, -1, 1), (a, b, 1, -1), (b, b, -1, -1)):
                p.drawLine(QPointF(x, y), QPointF(x + dx * length, y))
                p.drawLine(QPointF(x, y), QPointF(x, y + dy * length))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(size / 2, size / 2), size * 0.09, size * 0.09)
            p.end()
            icon.addPixmap(pm)
        _APP_ICON = icon
    return _APP_ICON


def make_shutter_wav(path: Path) -> Optional[Path]:
    """Buat bunyi 'cekrek' kecil (sekali saja) supaya tidak butuh file tambahan."""
    if path.exists():
        return path
    try:
        rate, rnd, frames = 22050, random.Random(7), bytearray()
        for i in range(int(rate * 0.16)):
            t = i / rate
            value = 0.0
            for start, amp in ((0.0, 0.9), (0.075, 0.6)):
                if t >= start:
                    d = t - start
                    value += amp * math.exp(-d / 0.012) * (rnd.uniform(-1, 1) * 0.7
                                                           + math.sin(2 * math.pi * 1800 * d) * 0.3)
            frames += struct.pack("<h", int(max(-1.0, min(1.0, value)) * 26000))
        path.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(path), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(rate)
            wav.writeframes(bytes(frames))
        return path
    except OSError:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Kamera HP: server web kecil di jaringan lokal. HP membuka halamannya lewat
# browser, memotret dengan kamera bawaan HP (<input capture>), lalu fotonya
# dikirim ke PC dan disimpan apa adanya (resolusi penuh, EXIF tetap utuh).
# Cara ini jalan lewat http:// biasa, tanpa sertifikat HTTPS.
# ─────────────────────────────────────────────────────────────────────────────
MAX_UPLOAD = 200 * 1024 * 1024          # batas satu file (200 MB)


def new_camera_token() -> str:
    return secrets.token_urlsafe(6)      # 8 karakter acak, cukup untuk jaringan rumah/kantor


def sniff_image_ext(head: bytes) -> Optional[str]:
    """Tentukan ekstensi dari isi file (bukan dari nama), sekaligus menolak file non-gambar."""
    if head[:3] == b"\xff\xd8\xff":
        return ".jpg"
    if head[:8] == b"\x89PNG\r\n\x1a\n":
        return ".png"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head[:6] in (b"GIF87a", b"GIF89a"):
        return ".gif"
    if head[4:8] == b"ftyp":
        brand = head[8:12]
        if brand in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1"):
            return ".heic"
        if brand in (b"avif", b"avis"):
            return ".avif"
    return None


def lan_addresses() -> List[Tuple[str, str]]:
    """Alamat IPv4 PC di jaringan lokal: [(ip, nama adapter)], yang paling mungkin dipakai di urutan pertama."""
    primary = ""
    try:   # UDP "connect" tidak mengirim paket apa pun; hanya memilih adapter yang dipakai untuk keluar
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            primary = s.getsockname()[0]
    except OSError:
        pass
    found: List[Tuple[str, str]] = []
    flag = QNetworkInterface.InterfaceFlag
    for iface in QNetworkInterface.allInterfaces():
        flags = iface.flags()
        if not (flags & flag.IsUp) or not (flags & flag.IsRunning) or (flags & flag.IsLoopBack):
            continue
        for entry in iface.addressEntries():
            ip = entry.ip()
            if ip.protocol() != QAbstractSocket.NetworkLayerProtocol.IPv4Protocol:
                continue
            text = ip.toString()
            if text.startswith("169.254.") or any(text == a for a, _ in found):
                continue
            found.append((text, iface.humanReadableName()))
    if primary and not any(a == primary for a, _ in found):
        found.append((primary, "Utama"))
    virtual = re.compile(r"vmware|virtualbox|vethernet|hyper-v|wsl|docker|tailscale|zerotier|vpn|loopback", re.I)
    found.sort(key=lambda item: (item[0] != primary, bool(virtual.search(item[1]))))
    return found


def qr_image(text: str, module: int = 6, border: int = 4) -> Optional[QImage]:
    """QR code sebagai QImage. None jika paket segno belum terpasang."""
    try:
        import segno
    except ImportError:
        return None
    matrix = segno.make(text, error="m", micro=False).matrix
    n = len(matrix)
    size = (n + 2 * border) * module
    img = QImage(size, size, QImage.Format.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    black = QColor("black")
    for y, row in enumerate(matrix):
        for x, on in enumerate(row):
            if on:
                p.fillRect((x + border) * module, (y + border) * module, module, module, black)
    p.end()
    return img


PHONE_PAGE = """<!doctype html>
<html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>SnipSimpan · Kamera</title>
<style>
:root{color-scheme:light dark;--b:#2563eb}
body{font-family:system-ui,-apple-system,sans-serif;margin:0 auto;padding:20px;max-width:520px}
h1{font-size:21px;margin:4px 0 2px}
p.sub{color:#888;margin:0 0 18px;font-size:14px}
label.btn{display:flex;align-items:center;justify-content:center;gap:10px;box-sizing:border-box;
  width:100%;padding:20px;border-radius:16px;font-size:19px;font-weight:600;cursor:pointer;
  margin-bottom:12px;user-select:none;-webkit-tap-highlight-color:transparent}
label.btn:active{opacity:.75}
label.main{background:var(--b);color:#fff;min-height:130px;font-size:25px}
label.alt{border:2px solid var(--b);color:var(--b)}
input[type=file]{display:none}
#count{text-align:center;color:#888;font-size:13px;margin:4px 0 0}
ul{list-style:none;padding:0;margin:16px 0 0}
li{display:flex;align-items:center;gap:10px;padding:9px 11px;border-radius:12px;
  background:rgba(127,127,127,.13);margin-bottom:8px;font-size:14px}
li img{width:46px;height:46px;object-fit:cover;border-radius:7px;flex:none;background:rgba(127,127,127,.2)}
li .t{flex:1;min-width:0}
li .s{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
li .n{color:#888;font-size:12px}
li.ok .s{color:#16a34a}
li.err .s{color:#dc2626}
li button{border:0;background:var(--b);color:#fff;border-radius:8px;padding:8px 12px;font-size:14px}
</style></head><body>
<h1>📷 SnipSimpan</h1>
<p class="sub">Foto langsung tersimpan di folder PC. Biarkan halaman ini terbuka.</p>
<label class="btn main" for="cam">📷 Ambil Foto</label>
<input id="cam" type="file" accept="image/*" capture="environment">
<label class="btn alt" for="gal">🖼️ Kirim dari Galeri</label>
<input id="gal" type="file" accept="image/*" multiple>
<p id="count"></p>
<ul id="list"></ul>
<script>
const K = "__TOKEN__";
const list = document.getElementById("list");
let queue = Promise.resolve(), sent = 0;

function kb(n){ return n > 1048576 ? (n/1048576).toFixed(1) + " MB" : Math.round(n/1024) + " KB"; }

function makeRow(file){
  const li = document.createElement("li");
  const img = document.createElement("img");
  img.src = URL.createObjectURL(file);
  img.onload = img.onerror = () => URL.revokeObjectURL(img.src);
  const t = document.createElement("div"); t.className = "t";
  const s = document.createElement("div"); s.className = "s"; s.textContent = "Menunggu…";
  const n = document.createElement("div"); n.className = "n"; n.textContent = kb(file.size);
  t.append(s, n); li.append(img, t);
  list.prepend(li);
  return {li, s};
}

function fail(row, file, msg){
  row.li.className = "err";
  row.s.textContent = "✗ " + msg;
  const b = document.createElement("button");
  b.textContent = "Ulangi";
  b.onclick = () => { b.remove(); queue = queue.then(() => upload(file, row)); };
  row.li.append(b);
}

function upload(file, row){
  return new Promise(done => {
    row.li.className = ""; row.s.textContent = "Mengirim…";
    const x = new XMLHttpRequest();
    x.open("POST", "/upload?k=" + encodeURIComponent(K));
    x.setRequestHeader("X-Filename", encodeURIComponent(file.name || "foto.jpg"));
    x.upload.onprogress = e => {
      if (e.lengthComputable) row.s.textContent = "Mengirim… " + Math.round(e.loaded * 100 / e.total) + "%";
    };
    x.onload = () => {
      let d = {}; try { d = JSON.parse(x.responseText); } catch (e) {}
      if (x.status === 200 && d.ok) {
        row.li.className = "ok"; row.s.textContent = "✓ " + d.name;
        sent++; document.getElementById("count").textContent = sent + " foto terkirim ke PC";
        if (navigator.vibrate) navigator.vibrate(40);
      } else fail(row, file, d.error || ("Galat " + x.status));
      done();
    };
    x.onerror = () => { fail(row, file, "Tidak terhubung ke PC"); done(); };
    x.send(file);
  });
}

for (const id of ["cam", "gal"]) {
  const input = document.getElementById(id);
  input.onchange = () => {
    for (const f of Array.from(input.files)) { const r = makeRow(f); queue = queue.then(() => upload(f, r)); }
    input.value = "";   // supaya bisa langsung memotret lagi
  };
}
</script></body></html>"""

PHONE_DENIED = """<!doctype html><html lang="id"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>SnipSimpan</title></head>
<body style="font-family:system-ui,sans-serif;padding:24px;max-width:480px;margin:auto">
<h2>🔒 Kode akses salah</h2>
<p>Scan ulang QR code di aplikasi SnipSimpan (tab <b>Kamera HP</b>) di PC.</p></body></html>"""


class _PhoneHttpd(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False          # di Windows SO_REUSEADDR bisa "berbagi" port dengan program lain

    def server_bind(self):
        if IS_WINDOWS and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        # Lewati HTTPServer.server_bind: getfqdn() di sana bisa lambat beberapa detik di Windows.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]

    def handle_error(self, request, client_address):
        pass                             # koneksi HP putus di tengah jalan bukan masalah bagi aplikasi


class PhoneServer(QObject):
    """Server HTTP di thread sendiri. Foto yang masuk diteruskan ke GUI lewat sinyal uploadArrived."""
    uploadArrived = Signal(object)      # dict: data, ext, client, event, name, error
    clientSeen = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._httpd: Optional[_PhoneHttpd] = None
        self._thread: Optional[threading.Thread] = None
        self.token = ""
        self.port = 0

    @property
    def running(self) -> bool:
        return self._httpd is not None

    def start(self, port: int, token: str) -> Optional[str]:
        """Nyalakan server. Hasil: None jika berhasil, atau pesan galat."""
        self.stop()
        self.token = token
        try:
            httpd = _PhoneHttpd(("0.0.0.0", port), self._handler_class())
        except OSError as exc:
            if getattr(exc, "winerror", None) in (10048, 10013) or exc.errno in (98, 10048):
                return f"Port {port} sedang dipakai program lain. Ganti nomor port."
            return f"Server tidak bisa dibuka: {exc.strerror or exc}"
        self._httpd, self.port = httpd, port
        self._thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.3},
                                        name="SnipSimpan-kamera", daemon=True)
        self._thread.start()
        return None

    def stop(self) -> None:
        httpd, self._httpd = self._httpd, None
        if httpd is not None:
            httpd.shutdown()
            httpd.server_close()
        if self._thread is not None:
            self._thread.join(2)
            self._thread = None

    def _handler_class(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = APP_NAME
            sys_version = ""

            def log_message(self, *_args):      # pythonw / exe tidak punya stderr
                pass

            def _authorized(self, query: str) -> bool:
                got = parse_qs(query).get("k", [""])[0]
                return bool(owner.token) and hmac.compare_digest(got.encode(), owner.token.encode())

            def _send(self, code: int, body: bytes, ctype: str) -> None:
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.send_header("Referrer-Policy", "no-referrer")
                self.end_headers()
                self.wfile.write(body)

            def _json(self, code: int, obj: dict) -> None:
                self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                           "application/json; charset=utf-8")

            def do_GET(self):
                url = urlsplit(self.path)
                if url.path != "/":
                    self._send(404, b"Not found", "text/plain; charset=utf-8")
                elif not self._authorized(url.query):
                    self._send(403, PHONE_DENIED.encode("utf-8"), "text/html; charset=utf-8")
                else:
                    owner.clientSeen.emit(self.client_address[0])
                    page = PHONE_PAGE.replace("__TOKEN__", owner.token)
                    self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")

            def do_POST(self):
                url = urlsplit(self.path)
                if url.path != "/upload":
                    return self._json(404, {"ok": False, "error": "Alamat tidak dikenal"})
                if not self._authorized(url.query):
                    return self._json(403, {"ok": False, "error": "Kode akses salah, scan ulang QR di PC"})
                try:
                    length = int(self.headers.get("Content-Length", ""))
                except ValueError:
                    return self._json(411, {"ok": False, "error": "Ukuran file tidak diketahui"})
                if length <= 0:
                    return self._json(400, {"ok": False, "error": "File kosong"})
                if length > MAX_UPLOAD:
                    self.close_connection = True
                    return self._json(413, {"ok": False, "error": "File terlalu besar (maks. 200 MB)"})
                data, remaining = bytearray(), length
                while remaining > 0:
                    chunk = self.rfile.read(min(1 << 20, remaining))
                    if not chunk:
                        return                   # HP terputus di tengah pengiriman
                    data += chunk
                    remaining -= len(chunk)
                ext = sniff_image_ext(bytes(data[:32]))
                if ext is None:
                    return self._json(415, {"ok": False, "error": "Bukan file gambar"})
                owner.clientSeen.emit(self.client_address[0])
                req = {"data": bytes(data), "ext": ext, "client": self.client_address[0],
                       "event": threading.Event(), "name": None, "error": None}
                del data
                owner.uploadArrived.emit(req)
                if not req["event"].wait(60):
                    return self._json(504, {"ok": False, "error": "PC tidak merespons"})
                if req["error"]:
                    return self._json(500, {"ok": False, "error": req["error"]})
                self._json(200, {"ok": True, "name": req["name"]})

        return Handler


# ─────────────────────────────────────────────────────────────────────────────
# Jendela utama
# ─────────────────────────────────────────────────────────────────────────────
STYLE = """
QPushButton#captureButton { font-size: 13px; font-weight: 600; padding: 6px 10px; }
QLabel#muted { color: gray; }
QLabel#preview { border: 1px solid rgba(128,128,128,0.45); border-radius: 4px; color: gray; }
QLabel#qr { border: 1px solid rgba(128,128,128,0.45); border-radius: 4px; color: gray; background: white; }
QLabel#url { font-size: 13px; font-weight: 600; }
"""
STATUS_COLORS = {"good": "#16a34a", "bad": "#dc2626", "muted": "gray"}


class MainWindow(QMainWindow):
    imageSaved = Signal(str, bool)

    def __init__(self, cfg: Config, server: QLocalServer):
        super().__init__()
        self.cfg = cfg
        self.server = server
        self.server.newConnection.connect(self._on_second_instance)
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(app_icon())
        self.setStyleSheet(STYLE)

        self.busy = False
        self.quitting = False
        self.restore_after = False
        self.close_hint_shown = False
        self.overlays: List[RegionOverlay] = []
        self.pending: Dict[str, Tuple[QImage, bool]] = {}
        self.session_count = 0
        self.auto_count = 0
        self.auto_hid = False
        self.recording_edits: set = set()

        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="save")
        self.imageSaved.connect(self._on_saved)
        self.hotkeys = GlobalHotkeys(self)
        self.hotkeys.activated.connect(self.on_action)
        self.auto_timer = QTimer(self)
        self.auto_timer.timeout.connect(self._auto_tick)
        self.phone = PhoneServer(self)
        self.phone.uploadArrived.connect(self._on_phone_upload)
        self.phone.clientSeen.connect(self._on_phone_seen)
        self.phone_paths: set = set()
        self.phone_count = 0
        if not self.cfg["camera_token"]:
            self.cfg["camera_token"] = new_camera_token()
            self.cfg.save()

        tabs = QTabWidget()
        tabs.addTab(self._tab_capture(), "Screenshot")
        tabs.addTab(self._tab_camera(), "Kamera HP")
        tabs.addTab(self._tab_hotkeys(), "Hotkey")
        tabs.addTab(self._tab_settings(), "Pengaturan")
        self.setCentralWidget(tabs)
        self._build_tray()

        self._update_last_region_label()
        self._update_name_preview()
        self.apply_hotkeys()
        if self.cfg["camera_autostart"]:
            self.start_phone()
        else:
            self._refresh_phone_ui()
        self.resize(600, 680)

    # ── Tab: Screenshot ──────────────────────────────────────────────────────
    def _tab_capture(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)

        box = QGroupBox("Folder penyimpanan")
        row = QHBoxLayout(box)
        self.folder_edit = QLineEdit(self.cfg["folder"])
        self.folder_edit.setToolTip("Semua screenshot langsung tersimpan di folder ini")
        self.folder_edit.editingFinished.connect(self._folder_edited)
        choose = QPushButton("Pilih…")
        choose.clicked.connect(self.choose_folder)
        open_btn = QPushButton("Buka")
        open_btn.clicked.connect(self.open_folder)
        row.addWidget(self.folder_edit, 1)
        row.addWidget(choose)
        row.addWidget(open_btn)
        lay.addWidget(box)

        box = QGroupBox("Ambil screenshot — langsung tersimpan, tanpa dialog")
        grid = QGridLayout(box)
        self.capture_buttons: Dict[str, QPushButton] = {}
        for i, action in enumerate(("full", "region", "repeat", "window")):
            btn = QPushButton(ACTION_LABEL[action])
            btn.setObjectName("captureButton")
            btn.setMinimumHeight(56)
            btn.clicked.connect(lambda _=False, a=action: self.capture(a))
            grid.addWidget(btn, i // 2, i % 2)
            self.capture_buttons[action] = btn
        self.last_region_label = QLabel()
        self.last_region_label.setObjectName("muted")
        grid.addWidget(self.last_region_label, 2, 0, 1, 2)
        lay.addWidget(box)

        box = QGroupBox("Screenshot otomatis berulang")
        row = QHBoxLayout(box)
        row.addWidget(QLabel("Setiap"))
        self.auto_interval = QSpinBox()
        self.auto_interval.setRange(1, 3600)
        self.auto_interval.setSuffix(" detik")
        self.auto_interval.setValue(self.cfg["auto_interval"])
        self.auto_interval.valueChanged.connect(self._auto_interval_changed)
        row.addWidget(self.auto_interval)
        self.auto_mode = QComboBox()
        for key, label in AUTO_MODES:
            self.auto_mode.addItem(label, key)
        self.auto_mode.setCurrentIndex(max(0, self.auto_mode.findData(self.cfg["auto_mode"])))
        self.auto_mode.currentIndexChanged.connect(
            lambda _i: self._set("auto_mode", self.auto_mode.currentData()))
        row.addWidget(self.auto_mode, 1)
        self.auto_button = QPushButton("Mulai")
        self.auto_button.setMinimumWidth(110)
        self.auto_button.clicked.connect(self.toggle_auto)
        row.addWidget(self.auto_button)
        lay.addWidget(box)

        box = QGroupBox("Riwayat")
        row = QHBoxLayout(box)
        left = QVBoxLayout()
        self.history = QListWidget()
        self.history.setToolTip("Klik dua kali untuk membuka gambar")
        self.history.itemActivated.connect(lambda item: self._open_path(item.data(Qt.ItemDataRole.UserRole)))
        left.addWidget(self.history, 1)
        buttons = QHBoxLayout()
        b = QPushButton("Buka gambar")
        b.clicked.connect(self._open_selected)
        buttons.addWidget(b)
        b = QPushButton("Tampilkan di folder")
        b.clicked.connect(self._reveal_selected)
        buttons.addWidget(b)
        buttons.addStretch(1)
        left.addLayout(buttons)
        row.addLayout(left, 1)
        right = QVBoxLayout()
        self.preview = QLabel("Belum ada\nscreenshot")
        self.preview.setObjectName("preview")
        self.preview.setFixedSize(200, 130)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.preview)
        self.count_label = QLabel("Sesi ini: 0 file")
        self.count_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.count_label)
        right.addStretch(1)
        row.addLayout(right)
        lay.addWidget(box, 1)
        return page

    # ── Tab: Kamera HP ───────────────────────────────────────────────────────
    def _tab_camera(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)

        box = QGroupBox("Foto dari kamera HP — langsung tersimpan ke folder di atas")
        row = QHBoxLayout(box)
        self.qr_label = QLabel()
        self.qr_label.setObjectName("qr")
        self.qr_label.setFixedSize(230, 230)
        self.qr_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.qr_label.setWordWrap(True)
        row.addWidget(self.qr_label)
        right = QVBoxLayout()
        self.phone_status = QLabel()
        self.phone_status.setWordWrap(True)
        right.addWidget(self.phone_status)
        self.phone_url = QLabel()
        self.phone_url.setObjectName("url")
        self.phone_url.setWordWrap(True)
        self.phone_url.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        right.addWidget(self.phone_url)
        buttons = QHBoxLayout()
        self.phone_button = QPushButton("Aktifkan")
        self.phone_button.setObjectName("captureButton")
        self.phone_button.setMinimumHeight(40)
        self.phone_button.clicked.connect(self.toggle_phone)
        buttons.addWidget(self.phone_button, 1)
        self.copy_url_button = QPushButton("Salin alamat")
        self.copy_url_button.clicked.connect(self._copy_phone_url)
        buttons.addWidget(self.copy_url_button)
        right.addLayout(buttons)
        steps = QLabel("1. HP dan PC tersambung ke Wi-Fi yang sama.\n"
                       "2. Scan QR ini dengan kamera HP (atau ketik alamatnya di browser).\n"
                       "3. Tekan \"Ambil Foto\" di HP. Setelah foto diambil, file langsung masuk ke PC.")
        steps.setObjectName("muted")
        steps.setWordWrap(True)
        right.addWidget(steps)
        right.addStretch(1)
        row.addLayout(right, 1)
        lay.addWidget(box)

        box = QGroupBox("Koneksi")
        form = QFormLayout(box)
        ip_row = QHBoxLayout()
        self.ip_combo = QComboBox()
        self.ip_combo.setToolTip("Pilih alamat dari adapter Wi-Fi/LAN yang satu jaringan dengan HP")
        self.ip_combo.currentIndexChanged.connect(self._ip_changed)
        ip_row.addWidget(self.ip_combo, 1)
        refresh = QToolButton()
        refresh.setText("⟳")
        refresh.setToolTip("Deteksi ulang alamat jaringan")
        refresh.clicked.connect(self._fill_ip_combo)
        ip_row.addWidget(refresh)
        form.addRow("Alamat PC:", ip_row)
        self.port_spin = QSpinBox()
        self.port_spin.setRange(1024, 65535)
        self.port_spin.setValue(self.cfg["camera_port"])
        self.port_spin.editingFinished.connect(self._port_changed)
        form.addRow("Port:", self.port_spin)
        token_row = QHBoxLayout()
        self.token_label = QLabel()
        self.token_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        token_row.addWidget(self.token_label)
        regen = QPushButton("Ganti kode")
        regen.setToolTip("Buat kode baru. HP yang memakai alamat lama tidak bisa mengirim lagi sampai scan ulang.")
        regen.clicked.connect(self._regen_token)
        token_row.addWidget(regen)
        token_row.addStretch(1)
        form.addRow("Kode akses:", token_row)
        auto = QCheckBox("Aktifkan otomatis saat SnipSimpan dibuka")
        auto.setChecked(self.cfg["camera_autostart"])
        auto.toggled.connect(lambda v: self._set("camera_autostart", v))
        form.addRow("", auto)
        lay.addWidget(box)

        box = QGroupBox("Nama file foto")
        form = QFormLayout(box)
        self.camera_template_edit = QLineEdit(self.cfg["camera_template"])
        self.camera_template_edit.textChanged.connect(self._camera_template_changed)
        form.addRow("Pola nama:", self.camera_template_edit)
        self.camera_name_preview = QLabel()
        form.addRow("Contoh:", self.camera_name_preview)
        note = QLabel("Kode sama seperti screenshot ({mode} = kamera). Foto disimpan dalam format aslinya "
                      "dari HP (biasanya JPG) tanpa kompres ulang.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        form.addRow("", note)
        lay.addWidget(box)

        tips = QLabel(
            "Tips:\n"
            "• Saat pertama diaktifkan, Windows Firewall bisa bertanya. Izinkan untuk jaringan Private.\n"
            "• HP tidak bisa membuka alamatnya? Pastikan Wi-Fi di Windows berprofil Private (bukan Public), "
            "lalu coba alamat lain di daftar \"Alamat PC\".\n"
            "• Simpan halaman itu sebagai bookmark atau \"Add to Home screen\" di HP. Alamatnya tetap sama "
            "selama kode akses dan IP PC tidak berubah.")
        tips.setObjectName("muted")
        tips.setWordWrap(True)
        lay.addWidget(tips)
        lay.addStretch(1)

        self._fill_ip_combo()
        self._update_camera_name_preview()
        return page

    # ── Kamera HP: handler ───────────────────────────────────────────────────
    def _fill_ip_combo(self) -> None:
        wanted = self.ip_combo.currentData() or self.cfg["camera_ip"]
        self.ip_combo.blockSignals(True)
        self.ip_combo.clear()
        for ip, name in lan_addresses():
            self.ip_combo.addItem(f"{ip}   ({name})", ip)
        index = self.ip_combo.findData(wanted)
        self.ip_combo.setCurrentIndex(index if index >= 0 else 0)
        self.ip_combo.blockSignals(False)
        self._refresh_phone_ui()

    def _ip_changed(self, _index: int) -> None:
        ip = self.ip_combo.currentData()
        if ip:
            self._set("camera_ip", ip)
        self._refresh_phone_ui()

    def _port_changed(self) -> None:
        port = self.port_spin.value()
        if port == self.cfg["camera_port"]:
            return
        self._set("camera_port", port)
        if self.phone.running:
            self.start_phone()
        else:
            self._refresh_phone_ui()

    def _regen_token(self) -> None:
        self._set("camera_token", new_camera_token())
        self.phone.token = self.cfg["camera_token"]      # server yang sedang jalan langsung memakai kode baru
        self._refresh_phone_ui()
        self.notify("Kode akses diganti. Scan ulang QR di HP.")

    def _camera_template_changed(self, text: str) -> None:
        self._set("camera_template", text)
        self._update_camera_name_preview()

    def _update_camera_name_preview(self) -> None:
        name = render_name(self.cfg["camera_template"], datetime.now(), self.cfg["counter"], "kamera")
        self.camera_name_preview.setText(name + ".jpg")

    def _phone_url(self) -> str:
        ip = self.ip_combo.currentData()
        if not ip:
            return ""
        return f"http://{ip}:{self.cfg['camera_port']}/?k={quote(self.cfg['camera_token'])}"

    def _copy_phone_url(self) -> None:
        url = self._phone_url()
        if url:
            QGuiApplication.clipboard().setText(url)
            self.statusBar().showMessage("Alamat disalin ke clipboard", 3000)

    def toggle_phone(self) -> None:
        if self.phone.running:
            self.stop_phone()
        else:
            self.start_phone()

    def start_phone(self) -> None:
        error = self.phone.start(int(self.cfg["camera_port"]), self.cfg["camera_token"])
        if error:
            self.notify(error, error=True)
        self._refresh_phone_ui(error)

    def stop_phone(self) -> None:
        self.phone.stop()
        self._refresh_phone_ui()

    def _refresh_phone_ui(self, error: Optional[str] = None) -> None:
        running = self.phone.running
        url = self._phone_url()
        self.token_label.setText(self.cfg["camera_token"])
        self.phone_button.setText("Matikan" if running else "Aktifkan")
        self.copy_url_button.setEnabled(bool(url))
        self.phone_url.setText(url or "—")
        if hasattr(self, "tray_phone_action"):
            self.tray_phone_action.setText("Matikan kamera HP" if running else "Aktifkan kamera HP")
        if error:
            self._status(self.phone_status, f"✗ {error}", "bad")
        elif not url:
            self._status(self.phone_status, "Tidak ada jaringan. Sambungkan PC ke Wi-Fi/LAN, lalu klik ⟳.", "bad")
        elif running:
            got = f" · {self.phone_count} foto diterima" if self.phone_count else ""
            self._status(self.phone_status, f"● Aktif, menunggu foto dari HP{got}", "good")
        else:
            self._status(self.phone_status, "Nonaktif. Klik Aktifkan untuk mulai.", "muted")

        self.qr_label.setPixmap(QPixmap())
        if not running or not url:
            self.qr_label.setText("Klik Aktifkan untuk\nmenampilkan QR code")
            return
        img = qr_image(url)
        if img is None:
            self.qr_label.setText("QR code butuh paket segno:\npip install segno\n\n"
                                  "Sementara itu, ketik alamat di samping pada browser HP.")
            return
        self.qr_label.setPixmap(QPixmap.fromImage(img.scaled(
            self.qr_label.size() - QSize(12, 12), Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation)))

    def _on_phone_seen(self, client: str) -> None:
        self.statusBar().showMessage(f"HP terhubung: {client}", 4000)

    def _on_phone_upload(self, req: dict) -> None:
        # Di thread GUI: tentukan nama file (nomor urut, subfolder), lalu tulis di thread penyimpan.
        try:
            if self.quitting:
                raise CaptureError("Aplikasi sedang ditutup")
            path = str(self._next_path("camera", self.cfg["camera_template"], req["ext"]))
        except Exception as exc:               # noqa: BLE001
            req["error"] = str(exc)
            req["event"].set()
            self.notify(f"Foto dari HP gagal disimpan: {exc}", error=True)
            return
        self.pending[path] = (None, False)
        self.phone_paths.add(path)
        self.executor.submit(self._write_phone_file, req, path)

    def _write_phone_file(self, req: dict, path: str) -> None:
        ok = False
        try:
            with open(path, "xb") as fh:        # "x": jangan pernah menimpa file yang sudah ada
                fh.write(req["data"])
            ok = True
            req["name"] = Path(path).name
        except OSError as exc:
            req["error"] = f"Gagal menulis file di PC: {exc.strerror or exc}"
        req["event"].set()                      # balas ke HP secepatnya; pratinjau menyusul
        req["data"] = b""
        if ok:
            reader = QImageReader(path)
            reader.setAutoTransform(True)       # ikuti orientasi EXIF (foto potret tetap tegak)
            thumb = reader.read()
            if not thumb.isNull():
                thumb = thumb.scaled(400, 260, Qt.AspectRatioMode.KeepAspectRatio,
                                     Qt.TransformationMode.SmoothTransformation)
                self.pending[path] = (thumb, False)
        self.imageSaved.emit(path, ok)

    # ── Tab: Hotkey ──────────────────────────────────────────────────────────
    def _tab_hotkeys(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)
        info = QLabel("Klik kolom, lalu tekan kombinasi tombol yang Anda mau (mis. Ctrl+Alt+S).\n"
                      "Esc = batal · Backspace = nonaktifkan. Hotkey bekerja di aplikasi mana pun, "
                      "walau jendela ini tersembunyi di tray.")
        info.setWordWrap(True)
        lay.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(10)
        self.hotkey_edits: Dict[str, HotkeyEdit] = {}
        self.hotkey_status: Dict[str, QLabel] = {}
        for row, (action, label) in enumerate(ACTIONS):
            grid.addWidget(QLabel(label), row, 0)
            edit = HotkeyEdit()
            edit.setHotkey(Hotkey.parse(self.cfg["hotkeys"].get(action, "")))
            edit.changed.connect(lambda a=action: self._hotkey_changed(a))
            edit.recording.connect(lambda on, e=edit: self._hotkey_recording(e, on))
            grid.addWidget(edit, row, 1)
            clear = QToolButton()
            clear.setText("✕")
            clear.setToolTip("Nonaktifkan hotkey ini")
            clear.clicked.connect(lambda _=False, a=action: self._clear_hotkey(a))
            grid.addWidget(clear, row, 2)
            status = QLabel()
            status.setMinimumWidth(170)
            status.setWordWrap(True)
            grid.addWidget(status, row, 3)
            self.hotkey_edits[action] = edit
            self.hotkey_status[action] = status
        grid.setColumnStretch(1, 1)
        lay.addLayout(grid)

        reset = QPushButton("Kembalikan ke default")
        reset.clicked.connect(self._reset_hotkeys)
        lay.addWidget(reset, alignment=Qt.AlignmentFlag.AlignLeft)

        tips = QLabel(
            "Tips:\n"
            "• Mau pakai tombol PrintScreen? Di Windows 11 matikan dulu: Settings → Accessibility → "
            "Keyboard → \"Use the Print screen key to open screen capture\".\n"
            "• Status \"Sudah dipakai\" berarti kombinasi itu sedang dipakai aplikasi lain; pilih kombinasi lain.\n"
            "• \"Ulangi area terakhir\" cocok untuk screenshot berulang di area yang sama, tinggal tekan hotkey-nya.")
        tips.setObjectName("muted")
        tips.setWordWrap(True)
        lay.addWidget(tips)
        lay.addStretch(1)
        return page

    # ── Tab: Pengaturan ──────────────────────────────────────────────────────
    def _tab_settings(self) -> QWidget:
        page = QWidget()
        lay = QVBoxLayout(page)

        box = QGroupBox("Nama file")
        form = QFormLayout(box)
        self.template_edit = QLineEdit(self.cfg["template"])
        self.template_edit.textChanged.connect(self._template_changed)
        form.addRow("Pola nama:", self.template_edit)
        tokens = QLabel("{tanggal} = 2026-11-16 · {jam} = 14-30-05 · {nomor} = 0001 · {mode} = layar / area / jendela / kamera")
        tokens.setObjectName("muted")
        tokens.setWordWrap(True)
        form.addRow("", tokens)
        self.name_preview = QLabel()
        self.name_preview.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        form.addRow("Contoh:", self.name_preview)
        self.counter_spin = QSpinBox()
        self.counter_spin.setRange(1, 999999)
        self.counter_spin.setValue(self.cfg["counter"])
        self.counter_spin.valueChanged.connect(self._counter_changed)
        form.addRow("Nomor berikutnya:", self.counter_spin)
        fmt_row = QHBoxLayout()
        self.format_combo = QComboBox()
        self.format_combo.addItems(["PNG", "JPG"])
        self.format_combo.setCurrentText(self.cfg["format"] if self.cfg["format"] in ("PNG", "JPG") else "PNG")
        self.format_combo.currentTextChanged.connect(self._format_changed)
        fmt_row.addWidget(self.format_combo)
        fmt_row.addSpacing(12)
        fmt_row.addWidget(QLabel("Kualitas JPG:"))
        self.quality_spin = QSpinBox()
        self.quality_spin.setRange(10, 100)
        self.quality_spin.setSuffix(" %")
        self.quality_spin.setValue(self.cfg["jpg_quality"])
        self.quality_spin.valueChanged.connect(lambda v: self._set("jpg_quality", v))
        self.quality_spin.setEnabled(self.cfg["format"] == "JPG")
        fmt_row.addWidget(self.quality_spin)
        fmt_row.addStretch(1)
        form.addRow("Format:", fmt_row)
        date_sub = QCheckBox("Buat subfolder per tanggal (mis. …\\2026-11-16\\)")
        date_sub.setChecked(self.cfg["date_subfolder"])
        date_sub.toggled.connect(lambda v: (self._set("date_subfolder", v), self._update_name_preview()))
        form.addRow("", date_sub)
        lay.addWidget(box)

        box = QGroupBox("Pengambilan")
        form = QFormLayout(box)
        self.full_target = QComboBox()
        for key, label in FULL_TARGETS:
            self.full_target.addItem(label, key)
        self.full_target.setCurrentIndex(max(0, self.full_target.findData(self.cfg["fullscreen_target"])))
        self.full_target.currentIndexChanged.connect(
            lambda _i: self._set("fullscreen_target", self.full_target.currentData()))
        form.addRow("Layar penuh:", self.full_target)
        delay = QSpinBox()
        delay.setRange(0, 10)
        delay.setSuffix(" detik")
        delay.setSpecialValueText("Tanpa jeda")
        delay.setValue(self.cfg["delay"])
        delay.valueChanged.connect(lambda v: self._set("delay", v))
        form.addRow("Jeda sebelum ambil:", delay)
        lay.addWidget(box)

        box = QGroupBox("Perilaku")
        col = QVBoxLayout(box)
        for key, text in (
            ("hide_window", "Sembunyikan jendela ini saat mengambil screenshot"),
            ("copy_clipboard", "Salin juga ke clipboard (bisa langsung Ctrl+V)"),
            ("notify", "Tampilkan notifikasi setelah tersimpan"),
            ("sound", "Bunyi \"cekrek\" setelah tersimpan"),
            ("close_to_tray", "Tombol X = sembunyikan ke tray (hotkey tetap aktif)"),
            ("start_hidden", "Saat dibuka, langsung sembunyi di tray"),
        ):
            cb = QCheckBox(text)
            cb.setChecked(bool(self.cfg[key]))
            cb.toggled.connect(lambda v, k=key: self._set(k, v))
            col.addWidget(cb)
        lay.addWidget(box)

        where = QLabel(f"File pengaturan: {QDir.toNativeSeparators(str(self.cfg.path))}")
        where.setObjectName("muted")
        where.setWordWrap(True)
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        lay.addWidget(where)
        lay.addStretch(1)
        return page

    # ── Tray ─────────────────────────────────────────────────────────────────
    def _build_tray(self) -> None:
        self.tray = QSystemTrayIcon(app_icon(), self)
        self.tray.setToolTip(APP_NAME)
        menu = QMenu(self)
        self.tray_actions: Dict[str, QAction] = {}
        for action in ("full", "region", "repeat", "auto"):
            if action == "auto":
                menu.addSeparator()
            act = menu.addAction(ACTION_LABEL[action])
            act.triggered.connect(lambda _=False, a=action: self.on_action(a))
            self.tray_actions[action] = act
        menu.addSeparator()
        self.tray_phone_action = menu.addAction("Aktifkan kamera HP")
        self.tray_phone_action.triggered.connect(self.toggle_phone)
        menu.addAction("Buka folder screenshot").triggered.connect(self.open_folder)
        menu.addAction("Tampilkan jendela").triggered.connect(self.show_normal)
        menu.addSeparator()
        menu.addAction("Keluar").triggered.connect(self.quit_app)
        self.tray_menu = menu
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_activated)
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def _tray_activated(self, reason) -> None:
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_normal()

    # ── Pengaturan: handler ──────────────────────────────────────────────────
    def _set(self, key: str, value) -> None:
        self.cfg[key] = value
        self.cfg.save()

    def _folder_edited(self) -> None:
        text = self.folder_edit.text().strip()
        if text and text != self.cfg["folder"]:
            self._set("folder", text)

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Pilih folder penyimpanan screenshot", self.cfg["folder"])
        if folder:
            folder = QDir.toNativeSeparators(folder)
            self.folder_edit.setText(folder)
            self._set("folder", folder)
            self.notify(f"Folder penyimpanan: {folder}")

    def _template_changed(self, text: str) -> None:
        self._set("template", text)
        self._update_name_preview()

    def _counter_changed(self, value: int) -> None:
        self._set("counter", value)
        self._update_name_preview()

    def _format_changed(self, fmt: str) -> None:
        self._set("format", fmt)
        self.quality_spin.setEnabled(fmt == "JPG")
        self._update_name_preview()

    def _update_name_preview(self) -> None:
        name = render_name(self.cfg["template"], datetime.now(), self.cfg["counter"], "layar")
        ext = ".jpg" if self.cfg["format"] == "JPG" else ".png"
        prefix = datetime.now().strftime("%Y-%m-%d") + os.sep if self.cfg["date_subfolder"] else ""
        self.name_preview.setText(prefix + name + ext)

    def _auto_interval_changed(self, value: int) -> None:
        self._set("auto_interval", value)
        if self.auto_timer.isActive():
            self.auto_timer.setInterval(value * 1000)

    # ── Hotkey ───────────────────────────────────────────────────────────────
    def _hotkey_changed(self, action: str) -> None:
        hk = self.hotkey_edits[action].hotkey()
        self.cfg["hotkeys"][action] = str(hk) if hk else ""
        self.cfg.save()

    def _hotkey_recording(self, edit: HotkeyEdit, on: bool) -> None:
        if on:
            self.recording_edits.add(edit)
            self.hotkeys.stop()                 # supaya kombinasi yang ditekan sampai ke kolom ini
            for label in self.hotkey_status.values():
                self._status(label, "Dijeda (sedang mengatur)", "muted")
        else:
            self.recording_edits.discard(edit)
            QTimer.singleShot(0, self.apply_hotkeys)

    def _clear_hotkey(self, action: str) -> None:
        self.hotkey_edits[action].setHotkey(None)
        self._hotkey_changed(action)
        self.apply_hotkeys()

    def _reset_hotkeys(self) -> None:
        self.cfg["hotkeys"] = dict(DEFAULT_HOTKEYS)
        self.cfg.save()
        for action, edit in self.hotkey_edits.items():
            edit.setHotkey(Hotkey.parse(DEFAULT_HOTKEYS[action]))
        self.apply_hotkeys()

    @staticmethod
    def _status(label: QLabel, text: str, kind: str) -> None:
        label.setText(text)
        label.setStyleSheet(f"color: {STATUS_COLORS[kind]};")

    def apply_hotkeys(self) -> None:
        if self.recording_edits or self.quitting:
            return
        statuses: Dict[str, Tuple[str, str]] = {}
        bindings: Dict[str, Hotkey] = {}
        seen: Dict[Hotkey, str] = {}
        for action, _ in ACTIONS:
            hk = Hotkey.parse(self.cfg["hotkeys"].get(action, ""))
            if hk is None:
                statuses[action] = ("Nonaktif", "muted")
            elif hk in seen:
                statuses[action] = (f"Sama dengan \"{ACTION_LABEL[seen[hk]]}\"", "bad")
            else:
                seen[hk] = action
                bindings[action] = hk
        for action, error in self.hotkeys.start(bindings).items():
            statuses[action] = ("✓ Aktif" if error is None else error, "good" if error is None else "bad")
        for action, (text, kind) in statuses.items():
            self._status(self.hotkey_status[action], text, kind)
        self._refresh_hotkey_hints()

    def _refresh_hotkey_hints(self) -> None:
        for action, btn in self.capture_buttons.items():
            hk = self.cfg["hotkeys"].get(action, "")
            btn.setText(f"{ACTION_LABEL[action]}\n{hk}" if hk else ACTION_LABEL[action])
        running = self.auto_timer.isActive()
        for action, act in self.tray_actions.items():
            label = ("Stop otomatis" if running else "Mulai otomatis") if action == "auto" else ACTION_LABEL[action]
            hk = self.cfg["hotkeys"].get(action, "")
            act.setText(f"{label}\t{hk}" if hk else label)
        hk = self.cfg["hotkeys"].get("auto", "")
        self.auto_button.setText("Stop" if running else "Mulai")
        self.auto_button.setToolTip(f"Hotkey: {hk}" if hk else "")

    def on_action(self, action: str) -> None:
        if action == "auto":
            self.toggle_auto()
        else:
            self.capture(action)

    # ── Proses screenshot ────────────────────────────────────────────────────
    def capture(self, mode: str, auto: bool = False) -> None:
        if self.busy or self.quitting or QApplication.activeModalWidget() is not None:
            return
        self.busy = True
        self.restore_after = False
        wait = 0
        if not auto:
            wait = int(self.cfg["delay"]) * 1000
            if self.cfg["hide_window"] and self.isVisible() and not self.isMinimized():
                self.restore_after = True
                self.hide()
                wait += 250                      # beri waktu jendela benar-benar hilang
            if self.cfg["delay"]:
                self.statusBar().showMessage(f"Mengambil dalam {self.cfg['delay']} detik…")
        QTimer.singleShot(wait, lambda: self._do_capture(mode, auto))

    def _do_capture(self, mode: str, auto: bool) -> None:
        try:
            if mode == "repeat" and not self._last_region_valid():
                if auto:
                    raise CaptureError("Belum ada area tersimpan untuk mode otomatis")
                self.notify("Belum ada area tersimpan — silakan pilih area dulu.")
                mode = "region"
            if mode == "region":
                self._start_region()
                return                          # dilanjutkan di _region_selected / _region_cancelled
            self._store(self._grab(mode), mode, quiet=auto)
        except Exception as exc:               # noqa: BLE001 - tampilkan ke pengguna, jangan crash
            self.notify(f"Gagal mengambil screenshot: {exc}", error=True)
            if auto:
                self.stop_auto()
        self._finish()

    def _grab(self, mode: str) -> QImage:
        if mode == "full":
            target = self.cfg["fullscreen_target"]
            if target == "all":
                return grab_virtual_desktop()[0]
            screen = QGuiApplication.primaryScreen() if target == "primary" else screen_under_cursor()
            return grab_screen(screen)
        if mode == "repeat":
            region = self.cfg["last_region"]
            screen = next((s for s in QGuiApplication.screens() if s.name() == region.get("screen")),
                          QGuiApplication.primaryScreen())
            img = grab_screen(screen)
            rect = QRect(region["x"], region["y"], region["w"], region["h"]).intersected(img.rect())
            if rect.isEmpty():
                raise CaptureError("Area terakhir berada di luar layar")
            return img.copy(rect)
        if mode == "window":
            return grab_active_window()
        raise CaptureError(f"Mode tidak dikenal: {mode}")

    def _start_region(self) -> None:
        shots = [(screen, screen.grabWindow(0)) for screen in QGuiApplication.screens()]
        cursor_screen = screen_under_cursor()
        self.overlays = []
        for screen, shot in shots:
            overlay = RegionOverlay(screen, shot)
            overlay.selected.connect(self._region_selected)
            overlay.cancelled.connect(self._region_cancelled)
            self.overlays.append(overlay)
            overlay.open_on_screen()
        focus = next((o for o in self.overlays if o.target_screen is cursor_screen), self.overlays[0])
        focus.raise_()
        focus.activateWindow()
        focus.setFocus()

    def _close_overlays(self) -> bool:
        overlays, self.overlays = self.overlays, []
        for overlay in overlays:
            overlay.close()
        return bool(overlays)

    def _region_selected(self, img: QImage, screen_name: str, rect: QRect) -> None:
        if not self._close_overlays():
            return
        self.cfg["last_region"] = {"screen": screen_name, "x": rect.x(), "y": rect.y(),
                                   "w": rect.width(), "h": rect.height()}
        self.cfg.save()
        self._update_last_region_label()
        try:
            self._store(img, "region")
        except Exception as exc:               # noqa: BLE001
            self.notify(f"Gagal menyimpan: {exc}", error=True)
        self._finish()

    def _region_cancelled(self) -> None:
        if self._close_overlays():
            self.statusBar().showMessage("Pilih area dibatalkan", 3000)
            self._finish()

    def _finish(self) -> None:
        self.busy = False
        if self.restore_after:
            self.restore_after = False
            self.show()

    def _last_region_valid(self) -> bool:
        region = self.cfg.get("last_region")
        return (isinstance(region, dict)
                and all(isinstance(region.get(k), int) for k in ("x", "y", "w", "h"))
                and region["w"] > 0 and region["h"] > 0)

    def _update_last_region_label(self) -> None:
        if self._last_region_valid():
            region = self.cfg["last_region"]
            screen = str(region.get("screen", "")).replace("\\\\.\\", "")
            self.last_region_label.setText(
                f"Area terakhir: {region['w']} × {region['h']} px di posisi ({region['x']}, {region['y']})"
                + (f" · {screen}" if screen else ""))
        else:
            self.last_region_label.setText("Area terakhir: belum ada — pakai \"Pilih area\" sekali dulu.")

    # ── Simpan file ──────────────────────────────────────────────────────────
    def _next_path(self, mode: str, template: Optional[str] = None, ext: Optional[str] = None) -> Path:
        folder_text = (self.cfg["folder"] or "").strip()
        if not folder_text:
            raise CaptureError("Folder penyimpanan belum dipilih")
        folder = Path(os.path.expandvars(folder_text)).expanduser()
        now = datetime.now()
        if self.cfg["date_subfolder"]:
            folder = folder / now.strftime("%Y-%m-%d")
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise CaptureError(f"Folder tidak bisa dibuat: {folder} ({exc.strerror or exc})") from exc
        if template is None:
            template = self.cfg["template"]
        stem = render_name(template, now, self.cfg["counter"], MODE_TOKEN.get(mode, mode))
        if "{nomor}" in template:
            self.cfg["counter"] += 1
            self.cfg.save()
            self.counter_spin.blockSignals(True)
            self.counter_spin.setValue(self.cfg["counter"])
            self.counter_spin.blockSignals(False)
            self._update_name_preview()
            self._update_camera_name_preview()
        if ext is None:
            ext = ".jpg" if self.cfg["format"] == "JPG" else ".png"
        path = folder / f"{stem}{ext}"
        n = 2
        while path.exists() or str(path) in self.pending:
            path = folder / f"{stem}_{n}{ext}"
            n += 1
        return path

    def _store(self, img: QImage, mode: str, quiet: bool = False) -> None:
        if img is None or img.isNull():
            raise CaptureError("Gambar layar kosong")
        path = str(self._next_path(mode))
        if self.cfg["copy_clipboard"]:
            QGuiApplication.clipboard().setImage(img)
        self.pending[path] = (img, quiet)
        is_jpg = self.cfg["format"] == "JPG"
        self.executor.submit(self._write_file, img, path, "JPG" if is_jpg else "PNG",
                             int(self.cfg["jpg_quality"]) if is_jpg else -1)

    def _write_file(self, img: QImage, path: str, fmt: str, quality: int) -> None:
        # Dijalankan di thread terpisah supaya GUI tidak tersendat saat menyimpan gambar besar.
        try:
            ok = img.save(path, fmt, quality)
        except Exception:                      # noqa: BLE001
            ok = False
        self.imageSaved.emit(path, ok)

    def _on_saved(self, path: str, ok: bool) -> None:
        img, quiet = self.pending.pop(path, (None, False))
        from_phone = path in self.phone_paths
        self.phone_paths.discard(path)
        if not ok:
            self.notify(f"Gagal menyimpan file: {path}", error=True)
            return
        if from_phone:
            self.phone_count += 1
            self._refresh_phone_ui()
        self.session_count += 1
        name = Path(path).name
        item = QListWidgetItem(f"{datetime.now():%H:%M:%S}   {name}")
        item.setData(Qt.ItemDataRole.UserRole, path)
        item.setToolTip(path)
        self.history.insertItem(0, item)
        while self.history.count() > 300:
            self.history.takeItem(self.history.count() - 1)
        if img is not None:
            thumb = img.scaled(self.preview.size(), Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
            self.preview.setPixmap(QPixmap.fromImage(thumb))
        self.count_label.setText(f"Sesi ini: {self.session_count} file")
        if quiet:
            self.auto_count += 1
            self.tray.setToolTip(f"{APP_NAME} — otomatis: {self.auto_count} screenshot")
            self.statusBar().showMessage(f"[Otomatis #{self.auto_count}] Tersimpan: {name}", 4000)
        else:
            self.notify(f"Foto dari HP tersimpan: {name}" if from_phone else f"Tersimpan: {name}")
            self._beep()

    # ── Mode otomatis ────────────────────────────────────────────────────────
    def toggle_auto(self) -> None:
        if self.auto_timer.isActive():
            self.stop_auto()
        else:
            self.start_auto()

    def start_auto(self) -> None:
        mode = self.cfg["auto_mode"]
        if mode == "repeat" and not self._last_region_valid():
            self.notify("Mode otomatis \"Area terakhir\" butuh area. Pakai \"Pilih area\" dulu.", error=True)
            return
        self.auto_count = 0
        self.auto_hid = False
        first = 0
        if self.cfg["hide_window"] and self.isVisible() and not self.isMinimized():
            self.hide()
            self.auto_hid = True
            first = 300
        self.auto_timer.start(int(self.cfg["auto_interval"]) * 1000)
        QTimer.singleShot(first, self._auto_tick)
        self._refresh_hotkey_hints()
        hk = self.cfg["hotkeys"].get("auto", "")
        stop_hint = f"tekan {hk} atau menu tray" if hk else "lewat menu tray"
        self.notify(f"Otomatis dimulai: tiap {self.cfg['auto_interval']} detik. Untuk berhenti {stop_hint}.",
                    important=True)

    def stop_auto(self) -> None:
        if not self.auto_timer.isActive():
            return
        self.auto_timer.stop()
        self._refresh_hotkey_hints()
        self.tray.setToolTip(APP_NAME)
        self.notify(f"Otomatis berhenti — {self.auto_count} screenshot tersimpan.", important=True)
        if self.auto_hid:
            self.auto_hid = False
            self.show_normal()

    def _auto_tick(self) -> None:
        if self.auto_timer.isActive() and not self.busy:
            self.capture(self.cfg["auto_mode"], auto=True)

    # ── Notifikasi, suara, file ──────────────────────────────────────────────
    def notify(self, text: str, error: bool = False, important: bool = False) -> None:
        self.statusBar().showMessage(text, 6000)
        wanted = error or important or self.cfg["notify"]
        if wanted and self.tray.isVisible() and not self.isActiveWindow():
            icon = QSystemTrayIcon.MessageIcon.Warning if error else QSystemTrayIcon.MessageIcon.Information
            self.tray.showMessage(APP_NAME, text, icon, 2500)

    def _beep(self) -> None:
        if not self.cfg["sound"]:
            return
        if IS_WINDOWS:
            import winsound
            wav = make_shutter_wav(self.cfg.path.parent / "shutter.wav")
            try:
                if wav:
                    winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
                else:
                    winsound.MessageBeep(winsound.MB_OK)
            except RuntimeError:
                pass
        else:
            QApplication.beep()

    def _base_folder(self) -> Path:
        return Path(os.path.expandvars(self.cfg["folder"] or default_folder())).expanduser()

    def open_folder(self) -> None:
        folder = self._base_folder()
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self.notify(f"Folder tidak bisa dibuat: {exc}", error=True)
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(folder)))

    def _selected_path(self) -> Optional[str]:
        item = self.history.currentItem() or self.history.item(0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _open_path(self, path: Optional[str]) -> None:
        if path and Path(path).exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))
        elif path:
            self.notify("File sudah tidak ada (mungkin dipindah atau dihapus).", error=True)

    def _open_selected(self) -> None:
        self._open_path(self._selected_path())

    def _reveal_selected(self) -> None:
        path = self._selected_path()
        if not path:
            self.open_folder()
        elif IS_WINDOWS and Path(path).exists():
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent)))

    # ── Jendela, tray & keluar ───────────────────────────────────────────────
    def show_normal(self) -> None:
        self.show()
        self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
        self.raise_()
        self.activateWindow()

    def _on_second_instance(self) -> None:
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            sock.disconnected.connect(sock.deleteLater)
        self.show_normal()

    def closeEvent(self, event):
        if self.quitting:
            event.accept()
            return
        event.ignore()
        if self.cfg["close_to_tray"] and self.tray.isVisible():
            self.hide()
            if not self.close_hint_shown:
                self.close_hint_shown = True
                self.tray.showMessage(APP_NAME, "Masih berjalan di tray, hotkey tetap aktif.\n"
                                      "Klik kanan ikon ini lalu pilih Keluar untuk menutup.",
                                      QSystemTrayIcon.MessageIcon.Information, 3000)
        else:
            self.quit_app()

    def quit_app(self) -> None:
        if self.quitting:
            return
        self.quitting = True
        self.auto_timer.stop()
        self._close_overlays()
        self.hotkeys.stop()
        self.phone.stop()
        self.executor.shutdown(wait=True)
        self._folder_edited()
        self.cfg.save()
        self.tray.hide()
        QApplication.quit()


# ─────────────────────────────────────────────────────────────────────────────
# Start-up
# ─────────────────────────────────────────────────────────────────────────────
def single_instance_server() -> Optional[QLocalServer]:
    """Kembalikan server jika ini instance pertama; None jika sudah ada yang berjalan."""
    try:
        user = getpass.getuser()
    except Exception:                          # noqa: BLE001
        user = "user"
    name = f"{APP_NAME}-{re.sub(r'[^A-Za-z0-9_-]', '_', user)}"
    sock = QLocalSocket()
    sock.connectToServer(name)
    if sock.waitForConnected(400):
        sock.write(b"show")
        sock.flush()
        sock.waitForBytesWritten(400)
        sock.disconnectFromServer()
        return None
    QLocalServer.removeServer(name)
    server = QLocalServer()
    server.listen(name)
    return server


def install_excepthook(log_path: Path) -> None:
    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        if sys.stderr is not None:
            sys.stderr.write(text)
        if QApplication.instance() is not None and threading.current_thread() is threading.main_thread():
            QMessageBox.critical(None, APP_NAME, f"Terjadi kesalahan tak terduga:\n{exc}\n\n"
                                                 f"Detail dicatat di:\n{log_path}")
    sys.excepthook = hook


def main() -> int:
    QApplication.setApplicationName(APP_NAME)
    if IS_WINDOWS:
        try:   # agar ikon di taskbar memakai ikon SnipSimpan, bukan ikon Python
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("SnipSimpan.Screenshot")
        except Exception:                      # noqa: BLE001
            pass
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setWindowIcon(app_icon())

    server = single_instance_server()
    if server is None:
        return 0          # sudah berjalan; jendela yang lama sudah dimunculkan

    config_dir = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppConfigLocation)
    config_dir = Path(config_dir) if config_dir else Path.home() / f".{APP_NAME.lower()}"
    install_excepthook(config_dir / "error.log")
    cfg = Config(config_dir / "config.json")

    window = MainWindow(cfg, server)
    if cfg["start_hidden"] and QSystemTrayIcon.isSystemTrayAvailable():
        window.tray.showMessage(APP_NAME, "Berjalan di tray. Gunakan hotkey untuk screenshot.",
                                QSystemTrayIcon.MessageIcon.Information, 2500)
    else:
        window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
