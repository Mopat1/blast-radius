"""Database layer for BlastRadius Cloud.

MVP uses SQLite so the whole product runs with zero infrastructure.
Swap point: change DATABASE_URL to postgresql+psycopg://... for production.
"""

from __future__ import annotations

import datetime as dt
import os

from sqlalchemy import (create_engine, String, Integer, Text, DateTime,
                        ForeignKey, UniqueConstraint)
from sqlalchemy.orm import (DeclarativeBase, Mapped, mapped_column,
                            relationship, sessionmaker)

DATABASE_URL = os.environ.get("BLASTRADIUS_DB", "sqlite:///blastradius.db")

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}
                       if DATABASE_URL.startswith("sqlite") else {})
SessionLocal = sessionmaker(bind=engine, autoflush=False)


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    repos: Mapped[list["Repo"]] = relationship(back_populates="owner",
                                               cascade="all, delete-orphan")


class Repo(Base):
    __tablename__ = "repos"
    __table_args__ = (UniqueConstraint("owner_id", "name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    name: Mapped[str] = mapped_column(String(200))
    source: Mapped[str] = mapped_column(Text)          # git URL or local path
    layout_json: Mapped[str] = mapped_column(Text, default="")   # saved dashboard layout
    status: Mapped[str] = mapped_column(String(20), default="pending")
    # pending | analyzing | ready | failed
    error: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    owner: Mapped[User] = relationship(back_populates="repos")
    analysis: Mapped["Analysis | None"] = relationship(back_populates="repo",
                                                       uselist=False,
                                                       cascade="all, delete-orphan")


class Analysis(Base):
    __tablename__ = "analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    repo_id: Mapped[int] = mapped_column(ForeignKey("repos.id"), unique=True)
    ir_json: Mapped[str] = mapped_column(Text)          # serialized IRDocument
    coupling_json: Mapped[str] = mapped_column(Text, default="[]")  # co-change pairs
    n_nodes: Mapped[int] = mapped_column(Integer, default=0)
    n_edges: Mapped[int] = mapped_column(Integer, default=0)
    finished_at: Mapped[dt.datetime] = mapped_column(DateTime, default=dt.datetime.utcnow)

    repo: Mapped[Repo] = relationship(back_populates="analysis")


def init_db() -> None:
    Base.metadata.create_all(engine)
    # lightweight migration for existing databases (SQLite + Postgres)
    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("ALTER TABLE analyses ADD COLUMN coupling_json TEXT DEFAULT '[]'"))
    except Exception:
        pass  # column already exists
    try:
        with engine.begin() as conn:
            from sqlalchemy import text
            conn.execute(text("ALTER TABLE repos ADD COLUMN layout_json TEXT DEFAULT ''"))
    except Exception:
        pass  # column already exists


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
