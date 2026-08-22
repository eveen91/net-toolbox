"""Central logging setup for the net::toolbox backend.

Every module gets a logger named for its location (e.g. net_toolbox.main,
net_toolbox.device_drivers.base), and setup_logging() wires them all to the
console plus a rotating file. The format embeds the logger name, function
name, and line number in every line, so an error message tells you exactly
which place it came from.

Uvicorn's own loggers (uvicorn / uvicorn.error / uvicorn.access) are left to
their own handlers and marked non-propagating, so nothing double-prints
through the root logger.

Credentials must never be passed into log messages anywhere in the app —
only device names / hosts / usernames / commands, never passwords.
"""

import logging
import logging.handlers
from pathlib import Path

LOG_FILE = Path(__file__).parent / "server.log"
LOG_FORMAT = (
    "%(asctime)s %(levelname)-8s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_FILE_MAX_BYTES = 5 * 1024 * 1024
LOG_FILE_BACKUP_COUNT = 5


def _quiet_uvicorn_loggers():
    # Let uvicorn keep its own handlers (stdout/stderr) and never propagate
    # into the root logger, so we don't print its lines twice.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logging.getLogger(name).propagate = False


def setup_logging(level: int = logging.INFO, log_file: Path | None = None) -> None:
    root = logging.getLogger()
    if root.handlers:
        # Already configured once (uvicorn --reload re-imports modules but the
        # root logger object persists) — nothing to re-add.
        _quiet_uvicorn_loggers()
        return

    root.setLevel(level)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    try:
        file_handler = logging.handlers.RotatingFileHandler(
            str(log_file or LOG_FILE),
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        # Log file not writable here (e.g. read-only volume) — console logging
        # still works, that's not worth taking the app down over.
        root.warning(
            "Could not create log file at %s — console logging only",
            log_file or LOG_FILE,
        )

    _quiet_uvicorn_loggers()
