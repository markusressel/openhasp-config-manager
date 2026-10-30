"""
Where an error of processing a file is: processing a file also reads the variables and objects of the other files of the
device, so an error in one of them stops it too. The error is marked with that file, without changing its type.
"""

from pathlib import Path
from typing import Optional

_SOURCE = "openhasp_source_file"


def mark_error_source(error: Exception, path: Path):
    """Marks `error` as one of the file at `path`, unless a file that is read deeper down already marked it."""
    if getattr(error, _SOURCE, None) is None:
        setattr(error, _SOURCE, path)


def error_source(error: Exception) -> Optional[Path]:
    """:return: the file the error is in, if it is not the file that was processed"""
    return getattr(error, _SOURCE, None)
