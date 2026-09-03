"""蔵書貸出管理ツールのコマンドラインプログラム。"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import date, datetime, timedelta

import db


LOAN_DAYS = 14
EXTENSION_DAYS = 7


def configure_output_encoding() -> None:
    """Windowsを含む各環境で日本語をUTF-8として出力する。"""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def current_date() -> date:
    """本日の日付を返す。テスト時に差し替えられるよう関数に分ける。"""
    return date.today()


def _error(message: str) -> int:
    print(f"エラー：{message}", file=sys.stderr)
    return 1


def _active_loan(conn: sqlite3.Connection, book_id: int) -> sqlite3.Row | None:
    return conn.execute(
        "SELECT * FROM loans WHERE book_id = ? AND returned_on IS NULL",
        (book_id,),
    ).fetchone()


def _book_exists(conn: sqlite3.Connection, book_id: int) -> bool:
    return (
        conn.execute("SELECT 1 FROM books WHERE id = ?", (book_id,)).fetchone()
        is not None
    )


def cmd_add(args: argparse.Namespace) -> int:
    """本を登録する。"""
    title = args.title.strip()
    author = args.author.strip() if args.author else None
    if not title:
        return _error("タイトルを入力してください。")

    conn = db.get_connection()
    try:
        with conn:
            cursor = conn.execute(
                "INSERT INTO books (title, author, created_at) VALUES (?, ?, ?)",
                (title, author, datetime.now().isoformat(timespec="seconds")),
            )
        print(f"本を登録しました。管理ID: {cursor.lastrowid} / {title}")
        return 0
    except sqlite3.Error:
        return _error("データを保存できませんでした。")
    finally:
        conn.close()


def cmd_list(args: argparse.Namespace) -> int:
    """本と現在の貸出状態を一覧表示する。"""
    today = current_date().isoformat()
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT b.id, b.title, b.author,
                   CASE
                       WHEN l.id IS NULL THEN '貸出可能'
                       WHEN l.due_on < ? THEN '延滞'
                       ELSE '貸出中'
                   END AS status
            FROM books AS b
            LEFT JOIN loans AS l
              ON l.book_id = b.id AND l.returned_on IS NULL
            ORDER BY b.id
            """,
            (today,),
        ).fetchall()
    except sqlite3.Error:
        return _error("データを読み込めませんでした。")
    finally:
        conn.close()

    if not rows:
        print("登録されている本はありません。")
        return 0

    print("ID\tタイトル\t著者名\t状態")
    for row in rows:
        print(f"{row['id']}\t{row['title']}\t{row['author'] or '-'}\t{row['status']}")
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    """タイトルの一部から本を検索する。"""
    keyword = args.keyword.strip()
    if not keyword:
        return _error("検索する文字を入力してください。")

    conn = db.get_connection()
    try:
        rows = conn.execute(
            "SELECT id, title, author FROM books WHERE title LIKE ? ORDER BY id",
            (f"%{keyword}%",),
        ).fetchall()
    except sqlite3.Error:
        return _error("データを読み込めませんでした。")
    finally:
        conn.close()

    if not rows:
        print("該当する本はありません。")
        return 0

    print("ID\tタイトル\t著者名")
    for row in rows:
        print(f"{row['id']}\t{row['title']}\t{row['author'] or '-'}")
    return 0


def cmd_count(args: argparse.Namespace) -> int:
    """登録されている本の合計冊数を表示する。"""
    conn = db.get_connection()
    try:
        count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    except sqlite3.Error:
        return _error("データを読み込めませんでした。")
    finally:
        conn.close()

    print(f"本の合計冊数: {count}冊")
    return 0


def cmd_lend(args: argparse.Namespace) -> int:
    """本の貸出を登録する。"""
    borrower = args.borrower.strip()
    if not borrower:
        return _error("貸出相手を入力してください。")

    lent_on = current_date()
    due_on = lent_on + timedelta(days=LOAN_DAYS)
    conn = db.get_connection()
    try:
        if not _book_exists(conn, args.book_id):
            return _error("指定した本は見つかりません。")
        if _active_loan(conn, args.book_id):
            return _error("この本はすでに貸出中です。")

        with conn:
            conn.execute(
                """
                INSERT INTO loans
                    (book_id, borrower, lent_on, due_on, is_extended, returned_on)
                VALUES (?, ?, ?, ?, 0, NULL)
                """,
                (args.book_id, borrower, lent_on.isoformat(), due_on.isoformat()),
            )
        print(
            f"本を貸し出しました。管理ID: {args.book_id} / "
            f"相手: {borrower} / 返却期限: {due_on.isoformat()}"
        )
        return 0
    except sqlite3.Error:
        return _error("データを保存できませんでした。")
    finally:
        conn.close()


def cmd_loans(args: argparse.Namespace) -> int:
    """未返却の貸出を、延長・延滞状態とともに一覧表示する。"""
    today = current_date().isoformat()
    conn = db.get_connection()
    try:
        rows = conn.execute(
            """
            SELECT b.id AS book_id, b.title, l.borrower, l.lent_on, l.due_on,
                   l.is_extended,
                   CASE WHEN l.due_on < ? THEN '延滞' ELSE '貸出中' END AS status
            FROM loans AS l
            JOIN books AS b ON b.id = l.book_id
            WHERE l.returned_on IS NULL
            ORDER BY l.due_on, b.id
            """,
            (today,),
        ).fetchall()
    except sqlite3.Error:
        return _error("データを読み込めませんでした。")
    finally:
        conn.close()

    if not rows:
        print("貸出中の本はありません。")
        return 0

    print("ID\tタイトル\t貸出相手\t貸出日\t返却期限\t延長\t状態")
    for row in rows:
        extended = "あり" if row["is_extended"] else "なし"
        print(
            f"{row['book_id']}\t{row['title']}\t{row['borrower']}\t"
            f"{row['lent_on']}\t{row['due_on']}\t{extended}\t{row['status']}"
        )
    return 0


def cmd_extend(args: argparse.Namespace) -> int:
    """貸出中の本の返却期限を1回だけ7日間延長する。"""
    today = current_date()
    conn = db.get_connection()
    try:
        if not _book_exists(conn, args.book_id):
            return _error("指定した本は見つかりません。")

        loan = _active_loan(conn, args.book_id)
        if loan is None:
            return _error("この本は貸出中ではありません。")
        if loan["is_extended"]:
            return _error("延長できるのは1回までです。")

        current_due = date.fromisoformat(loan["due_on"])
        if current_due < today:
            return _error("延滞している本は延長できません。")

        new_due = current_due + timedelta(days=EXTENSION_DAYS)
        with conn:
            conn.execute(
                "UPDATE loans SET due_on = ?, is_extended = 1 WHERE id = ?",
                (new_due.isoformat(), loan["id"]),
            )
        print(
            f"返却期限を延長しました。管理ID: {args.book_id} / "
            f"新しい返却期限: {new_due.isoformat()}"
        )
        return 0
    except (sqlite3.Error, ValueError):
        return _error("データを保存できませんでした。")
    finally:
        conn.close()


def cmd_return(args: argparse.Namespace) -> int:
    """貸出中の本を返却済みにする。"""
    returned_on = current_date().isoformat()
    conn = db.get_connection()
    try:
        if not _book_exists(conn, args.book_id):
            return _error("指定した本は見つかりません。")

        loan = _active_loan(conn, args.book_id)
        if loan is None:
            return _error("この本は貸出中ではありません。")

        with conn:
            conn.execute(
                "UPDATE loans SET returned_on = ? WHERE id = ?",
                (returned_on, loan["id"]),
            )
        print(f"本を返却しました。管理ID: {args.book_id} / 返却日: {returned_on}")
        return 0
    except sqlite3.Error:
        return _error("データを保存できませんでした。")
    finally:
        conn.close()


class JapaneseArgumentParser(argparse.ArgumentParser):
    """入力エラーを日本語で表示するArgumentParser。"""

    def error(self, message: str) -> None:
        if "invalid choice" in message:
            self.exit(2, "エラー：コマンドが見つかりません。\n")
        self.exit(2, f"エラー：入力内容が正しくありません。{message}\n")


def build_parser() -> argparse.ArgumentParser:
    parser = JapaneseArgumentParser(description="蔵書貸出管理ツール")
    subparsers = parser.add_subparsers(dest="command", metavar="コマンド")

    add_parser = subparsers.add_parser("add", help="本を登録する")
    add_parser.add_argument("title", help="本のタイトル")
    add_parser.add_argument("--author", default=None, help="著者名（任意）")
    add_parser.set_defaults(handler=cmd_add)

    list_parser = subparsers.add_parser("list", help="本を一覧表示する")
    list_parser.set_defaults(handler=cmd_list)

    search_parser = subparsers.add_parser("search", help="タイトルから検索する")
    search_parser.add_argument("keyword", help="検索する文字")
    search_parser.set_defaults(handler=cmd_search)

    count_parser = subparsers.add_parser("count", help="本の合計冊数を表示する")
    count_parser.set_defaults(handler=cmd_count)

    lend_parser = subparsers.add_parser("lend", help="本の貸出を登録する")
    lend_parser.add_argument("book_id", type=int, help="本の管理ID")
    lend_parser.add_argument("borrower", help="貸出相手")
    lend_parser.set_defaults(handler=cmd_lend)

    loans_parser = subparsers.add_parser("loans", help="貸出中の本を表示する")
    loans_parser.set_defaults(handler=cmd_loans)

    extend_parser = subparsers.add_parser("extend", help="返却期限を7日間延長する")
    extend_parser.add_argument("book_id", type=int, help="本の管理ID")
    extend_parser.set_defaults(handler=cmd_extend)

    return_parser = subparsers.add_parser("return", help="本の返却を登録する")
    return_parser.add_argument("book_id", type=int, help="本の管理ID")
    return_parser.set_defaults(handler=cmd_return)

    return parser


def main(argv: list[str] | None = None) -> int:
    configure_output_encoding()
    db.init_db()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 0
    return args.handler(args)


if __name__ == "__main__":
    raise SystemExit(main())
