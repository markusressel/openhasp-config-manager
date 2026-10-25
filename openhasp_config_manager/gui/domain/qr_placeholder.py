"""
A pattern that looks like a QR code, for the preview of `qrcode` objects. It is *not* the code of the text and can't be scanned:
the same text always gives the same pattern, so a changed text is visible. Qt-free.
"""

import hashlib
from typing import List

# modules per side (QR version 2)
MODULES = 25
_FINDER = 7


def placeholder_modules(text: str) -> List[List[bool]]:
    """:return: MODULES rows of MODULES dark (True) or light modules, with the three finder squares of a QR code"""
    digest = hashlib.sha256(text.encode()).digest()
    bits = [bool(digest[(i // 8) % len(digest)] >> (i % 8) & 1) for i in range(MODULES * MODULES)]
    modules = [[bits[row * MODULES + col] for col in range(MODULES)] for row in range(MODULES)]
    for top, left in ((0, 0), (0, MODULES - _FINDER), (MODULES - _FINDER, 0)):
        for row in range(-1, _FINDER + 1):
            for col in range(-1, _FINDER + 1):
                y, x = top + row, left + col
                if 0 <= y < MODULES and 0 <= x < MODULES:
                    on_frame = row in (0, _FINDER - 1) or col in (0, _FINDER - 1)
                    in_core = 2 <= row <= 4 and 2 <= col <= 4
                    modules[y][x] = 0 <= row < _FINDER and 0 <= col < _FINDER and (on_frame or in_core)
    return modules
