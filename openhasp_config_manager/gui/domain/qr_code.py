"""The modules of the QR code of a `qrcode` object. Qt-free."""

from typing import List

import segno

# the plate uses QR code version 7, which holds up to this many characters (with the lowest error correction)
MAX_TEXT_LENGTH = 122


def qr_modules(text: str) -> List[List[bool]]:
    """
    :return: the rows of the code, True for a dark module, without the quiet zone. Empty for an empty text. Measured on a plate: the lowest
        version that holds the text, with error correction Q (not raised to a higher level by segno) and mask 0.
    """
    if not text:
        return []
    return [
        [bool(module) for module in row] for row in segno.make(text, error="q", micro=False, mask=0, boost_error=False).matrix
    ]
