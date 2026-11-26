#!/usr/bin/env python3
"""Membuat snipsimpan.ico (16–256 px) dari ikon yang digambar di snipsimpan.py.

Jalankan: python buat_icon.py   (dipanggil otomatis oleh buat_exe.bat)
"""
import os
import struct
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from PySide6.QtCore import QBuffer, QByteArray, QSize  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402

import snipsimpan  # noqa: E402

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def png_bytes(size: int) -> bytes:
    pixmap = snipsimpan.app_icon().pixmap(QSize(size, size))
    data = QByteArray()
    buf = QBuffer(data)
    buf.open(QBuffer.OpenModeFlag.WriteOnly)
    pixmap.toImage().save(buf, "PNG")
    return bytes(data)


def main() -> None:
    app = QGuiApplication(sys.argv)  # noqa: F841 - QPixmap butuh aplikasi Qt
    images = [(size, png_bytes(size)) for size in SIZES]
    # Format ICO: header, daftar entri, lalu data PNG tiap ukuran (didukung sejak Windows Vista).
    out = bytearray(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, png in images:
        dim = 0 if size >= 256 else size
        out += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset)
        offset += len(png)
    for _, png in images:
        out += png
    target = HERE / "snipsimpan.ico"
    target.write_bytes(out)
    print(f"Ikon dibuat: {target}")


if __name__ == "__main__":
    main()
