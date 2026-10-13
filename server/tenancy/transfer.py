"""Atomic cross-tenant writes with the central identity/audit DB as coordinator."""
import sqlite3
from contextlib import contextmanager
from pathlib import Path

import auth_db
class TransferConflict(Exception):
    pass

class HostNotFound(Exception):
    pass

class TransferUnavailable(Exception):
    pass


@contextmanager
def attached_transaction(source, target, *, write=False):
    if Path(source.database_path).resolve() == Path(target.database_path).resolve():
        raise TransferConflict("Source and destination use the same database")
    conn = auth_db.get_connection()
    try:
        for alias, path in [("origin", source.database_path), ("destination", target.database_path)]:
            if not Path(path).is_file():
                raise TransferUnavailable("Tenant database is unavailable")
            conn.execute(f"ATTACH DATABASE ? AS {alias}", (str(path),))
        if write:
            for alias in ("main", "origin", "destination"):
                mode = conn.execute(f"PRAGMA {alias}.journal_mode").fetchone()[0]
                if mode.lower() not in ("delete", "truncate", "persist"):
                    raise TransferUnavailable("Moving data requires rollback-journal mode for tenant and identity databases")
        conn.execute("BEGIN IMMEDIATE" if write else "BEGIN")
        yield conn
        if write:
            conn.commit()
    except sqlite3.OperationalError as exc:
        raise TransferUnavailable("Tenant database is unavailable or busy. Retry the move") from exc
    finally:
        conn.close()  # Rolls back the whole operation on every failure/preview.
