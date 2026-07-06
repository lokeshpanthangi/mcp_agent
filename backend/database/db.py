from collections.abc import Generator

from sqlmodel import Session, SQLModel, create_engine

from config import settings

connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)
engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)


def create_db_and_tables() -> None:
    from database import models  # noqa: F401 - import registers the tables

    SQLModel.metadata.create_all(engine)
    _add_missing_columns()


def _add_missing_columns() -> None:
    """Add nullable columns introduced after a table already existed (SQLite)."""
    from sqlalchemy import text

    needed = {
        "usersettings": [("model", "VARCHAR")],
        "mcpserver": [
            ("tools_snapshot_json", "TEXT"),
            ("prompts_snapshot_json", "TEXT"),
        ],
    }
    with engine.begin() as conn:
        for table, columns in needed.items():
            existing = {row[1] for row in conn.execute(text(f"PRAGMA table_info({table})"))}
            for name, coltype in columns:
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {coltype}"))


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
