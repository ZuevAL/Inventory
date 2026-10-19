import sqlite3
import subprocess
import sys
from pathlib import Path


def migrate(database_path, revision):
    completed = subprocess.run([
        sys.executable, "-m", "alembic", "-x",
        f"db_url=sqlite+aiosqlite:///{database_path.as_posix()}",
        "upgrade", revision,
    ], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, errors="replace")
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_migration_preserves_existing_account_and_warehouse(tmp_path):
    database_path = tmp_path / "migration.db"
    migrate(database_path, "a50fc9e36bfe")
    with sqlite3.connect(database_path) as connection:
        connection.execute("INSERT INTO users (login, full_name, password_hash, role) VALUES (?, ?, ?, ?)",
                           ("admin_01", "Existing Admin", "existing-hash-must-not-change", "admin"))
        connection.execute("INSERT INTO products (name, barcode) VALUES ('Existing product', '123')")
    migrate(database_path, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT login, password_hash, credential_version FROM users").fetchone() == (
            "admin_01", "existing-hash-must-not-change", 0,
        )
        assert connection.execute("SELECT name, barcode FROM products").fetchone() == ("Existing product", "123")
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "c83170d591a2"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
        assert "uq_sessions_one_open_per_user" in [row[1] for row in connection.execute("PRAGMA index_list(sessions)")]


def test_empty_database_migrates_to_head(tmp_path):
    database_path = tmp_path / "empty.db"
    migrate(database_path, "head")
    with sqlite3.connect(database_path) as connection:
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"users", "sessions", "products", "shelves", "shelf_stock", "alembic_version"} <= tables
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
