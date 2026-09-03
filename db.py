"""SQLiteデータベースの接続と初期化を行う。"""

from __future__ import annotations

import sqlite3
from pathlib import Path


DB_PATH = Path(__file__).with_name("bookshelf.db")


def get_connection() -> sqlite3.Connection:
    """蔵書データベースへの接続を返す。"""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """booksとloansテーブルを、存在しない場合だけ作成する。"""
    conn = get_connection()
    try:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS books (
                    id         INTEGER PRIMARY KEY AUTOINCREMENT,
                    title      TEXT NOT NULL,
                    author     TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS loans (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    book_id      INTEGER NOT NULL,
                    borrower     TEXT NOT NULL,
                    lent_on      TEXT NOT NULL,
                    due_on       TEXT NOT NULL,
                    is_extended  INTEGER NOT NULL DEFAULT 0
                                 CHECK (is_extended IN (0, 1)),
                    returned_on  TEXT,
                    FOREIGN KEY (book_id) REFERENCES books(id)
                )
                """
            )
            conn.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS one_active_loan_per_book
                ON loans(book_id)
                WHERE returned_on IS NULL
                """
            )
    finally:
        conn.close()
