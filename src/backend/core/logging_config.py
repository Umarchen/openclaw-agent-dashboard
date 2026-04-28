"""
NFR-S-003: Logging storage security configuration.

Provides secure logging setup with:
- File rotation (size-based)
- Compression of rotated files
- Automatic cleanup of old logs based on retention policy
- File permission hardening

Usage:
    from core.logging_config import setup_secure_logging
    setup_secure_logging()

Configuration via environment variables:
    OPENCLAW_LOG_RETENTION_DAYS: Days to retain log files (default: 30)
    OPENCLAW_LOG_MAX_SIZE_MB: Max size per log file in MB (default: 100)
    OPENCLAW_LOG_BACKUP_COUNT: Number of backup files to keep (default: 5)
    OPENCLAW_LOG_FILE_PATH: Custom log file path (optional)
    OPENCLAW_LOG_COMPRESSION: Compress rotated logs (default: true)
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path
from typing import Optional

from core.config_fortify import get_fortify_config


def get_log_file_path() -> Optional[Path]:
    """Determine the log file path based on configuration."""
    cfg = get_fortify_config()
    if cfg.log_file_path:
        return Path(cfg.log_file_path)

    # Default path: logs/openclaw.log in project root
    project_root = Path(__file__).parent.parent.parent
    log_dir = project_root / "logs"
    return log_dir / "openclaw.log"


def ensure_log_directory(log_path: Path) -> None:
    """Ensure log directory exists with proper permissions."""
    log_dir = log_path.parent
    log_dir.mkdir(parents=True, exist_ok=True)

    # Set directory permissions to 0o750 (owner rwx, group r-x, others none)
    # Note: This may fail on Windows or if running as non-owner
    try:
        os.chmod(log_dir, 0o750)
    except (OSError, PermissionError):
        pass  # Skip on platforms that don't support chmod


def setup_secure_logging() -> None:
    """
    Configure secure logging with rotation, compression, and retention.

    This sets up handlers for all openclaw.* loggers:
    - Console handler for development
    - Rotating file handler with compression for production
    """
    cfg = get_fortify_config()
    log_path = get_log_file_path()

    if log_path is None:
        # No file logging, just console
        return

    ensure_log_directory(log_path)

    # Determine which loggers to configure
    logger_names = ["openclaw", "openclaw.fortify", "openclaw.fortify.watcher",
                    "openclaw.fortify.audit", "openclaw.fortify.cache_probe"]

    # Create rotating file handler
    max_bytes = cfg.log_max_size_mb * 1024 * 1024
    backup_count = cfg.log_backup_count

    # Base rotating handler
    if cfg.log_compression:
        # Use custom rotating handler with gzip compression
        handler: logging.Handler = _CompressedRotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )
    else:
        handler = logging.handlers.RotatingFileHandler(
            filename=str(log_path),
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding="utf-8",
        )

    # Set file permissions (owner read/write only)
    try:
        os.chmod(log_path, 0o600)
    except (OSError, PermissionError):
        pass

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    handler.setFormatter(formatter)

    # Apply to all relevant loggers
    for logger_name in logger_names:
        logger = logging.getLogger(logger_name)
        # Avoid duplicate handlers
        if not any(isinstance(h, (logging.handlers.RotatingFileHandler, _CompressedRotatingFileHandler))
                   for h in logger.handlers):
            logger.addHandler(handler)

    # Set levels based on config
    level = getattr(logging, cfg.error_log_level, logging.INFO)
    for logger_name in logger_names:
        logging.getLogger(logger_name).setLevel(level)

    # Schedule cleanup of old logs (best-effort)
    _schedule_log_cleanup(log_path, cfg.log_retention_days)


class _CompressedRotatingFileHandler(logging.handlers.RotatingFileHandler):
    """
    Rotating file handler that compresses old log files using gzip.

    Rotated files are renamed to <filename>.1.gz, <filename>.2.gz, etc.
    """

    def __init__(self, filename: str, maxBytes: int = 0, backupCount: int = 0,
                 encoding: str = "utf-8", compress: bool = True):
        super().__init__(filename, maxBytes=maxBytes, backupCount=backupCount, encoding=encoding)
        self._compress = compress

    def rotate(self, source: str, dest: str) -> None:
        """Compress the rotated file."""
        super().rotate(source, dest)

        if self._compress and os.path.exists(dest):
            try:
                import gzip
                with open(dest, "rb") as f_in:
                    with gzip.open(dest + ".gz", "wb", compresslevel=6) as f_out:
                        f_out.writelines(f_in)
                os.remove(dest)
            except Exception:
                # Compression failed, keep uncompressed file
                pass

    def shouldRollover(self, record: logging.LogRecord) -> int:
        """Check if rollover should occur."""
        if self.stream is None:
            self.stream = self._open()

        if self.maxBytes > 0:
            msg = "%s\n" % self.format(record)
            if self.stream.tell() + len(msg) >= self.maxBytes:
                return 1
        return 0


def _schedule_log_cleanup(log_path: Path, retention_days: int) -> None:
    """
    Schedule cleanup of log files older than retention period.

    This is a best-effort cleanup that runs on startup.
    For production, use an external cron job or logrotate.
    """
    import time

    def _cleanup():
        try:
            cutoff = time.time() - (retention_days * 86400)
            log_dir = log_path.parent

            for pattern in ["*.log*", "*.gz"]:
                for file_path in log_dir.glob(pattern):
                    if file_path.is_file() and file_path.stat().st_mtime < cutoff:
                        try:
                            file_path.unlink()
                        except OSError:
                            pass
        except Exception:
            pass  # Best-effort cleanup

    # Run cleanup in background thread
    import threading
    t = threading.Thread(target=_cleanup, daemon=True)
    t.start()


def get_logging_config_summary() -> dict:
    """Get a summary of the logging configuration for diagnostics."""
    cfg = get_fortify_config()
    log_path = get_log_file_path()

    summary = {
        "log_retention_days": cfg.log_retention_days,
        "log_max_size_mb": cfg.log_max_size_mb,
        "log_backup_count": cfg.log_backup_count,
        "log_file_path": str(log_path) if log_path else None,
        "log_compression": cfg.log_compression,
        "log_directory_exists": log_path.parent.exists() if log_path else False,
    }

    if log_path and log_path.exists():
        stat = log_path.stat()
        summary["current_log_size_bytes"] = stat.st_size
        summary["current_log_size_mb"] = round(stat.st_size / (1024 * 1024), 2)

    return summary
