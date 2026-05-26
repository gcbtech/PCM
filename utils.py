"""
PCM (PC Mover) - Shared Utilities
Cross-cutting helper functions shared across engine and GUI modules.
"""

import os
import sys


def is_reparse_point(path):
    """
    Checks if a file or directory is a Windows reparse point (junction, symlink,
    or cloud-only placeholder).  Reparse points can cause infinite loops or force
    slow cloud-download 'on demand' fetches on Windows.
    """
    if sys.platform != 'win32':
        return os.path.islink(path)
    try:
        # 0x400 (1024) == FILE_ATTRIBUTE_REPARSE_POINT
        return bool(os.lstat(path).st_file_attributes & 0x400)
    except Exception:
        return False


def format_bytes(size_bytes):
    """
    Converts a raw byte count into a human-readable string with the appropriate unit.

    Examples:
        format_bytes(0)           -> '0.00 B'
        format_bytes(1536)        -> '1.50 KB'
        format_bytes(2147483648)  -> '2.00 GB'
    """
    size = float(size_bytes)
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if size < 1024.0:
            return f'{size:.2f} {unit}'
        size /= 1024.0
    return f'{size:.2f} PB'


def should_exclude_file_or_dir(path):
    """
    Checks if a file or directory path corresponds to Google Chrome or other browser
    cache directories, temporary folders, or log files that should not be migrated.
    """
    path_lower = path.lower().replace('\\', '/')
    
    # Exclude directories
    exclude_dirs = [
        '/cache/',
        '/code cache/',
        '/gpucache/',
        '/application cache/',
        '/cachestorage/',
        '/scriptcache/',
        '/service worker/cachestorage/',
        '/service worker/scriptcache/',
        '/service worker/cache/',
        '/crashpad/'
    ]
    for d in exclude_dirs:
        if d in path_lower or path_lower.endswith(d[:-1]):
            return True
            
    # Exclude log files
    parts = path_lower.split('/')
    if parts:
        file_name = parts[-1]
        if file_name.endswith('.log') or file_name == 'log' or file_name == 'log.old':
            return True
            
    return False

