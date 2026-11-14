"""
HimShiksha API - Temporary File Cleanup Utilities
Provides background task helpers and safe deletion routines.
"""

import os
import shutil
import logging

logger = logging.getLogger("himshiksha.cleanup")


def remove_file_silent(filepath: str) -> None:
    """Silently remove a file from disk without throwing exceptions."""
    if filepath and os.path.exists(filepath):
        try:
            if os.path.isdir(filepath):
                shutil.rmtree(filepath, ignore_errors=True)
            else:
                os.remove(filepath)
        except OSError as e:
            logger.warning("Could not remove temp file %s: %s", filepath, e)


def cleanup_paths(*paths: str) -> None:
    """Clean up multiple file or directory paths."""
    for p in paths:
        if p:
            remove_file_silent(p)
