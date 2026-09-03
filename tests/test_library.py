from __future__ import annotations

from datetime import date

import pytest

import db
import library


@pytest.fixture(autouse=True)
def use_temporary_database(tmp_path, monkeypatch):
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test_bookshelf.db")
    monkeypatch.setattr(library, "current_date", lambda: date(2026, 9, 3))
    db.init_db()


def run_command(*arguments: str) -> int:
    return library.main(list(arguments))


def add_sample_book(title: str = "吾輩は猫である") -> int:
    assert run_command("add", title, "--author", "夏目漱石") == 0
    conn = db.get_connection()
    try:
        return conn.execute("SELECT MAX(id) FROM books").fetchone()[0]
    finally:
        conn.close()


def test_database_has_books_and_loans_with_foreign_key():
    conn = db.get_connection()
    try:
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        foreign_keys = conn.execute("PRAGMA foreign_key_list(loans)").fetchall()
    finally:
        conn.close()

    assert {"books", "loans"}.issubset(tables)
    assert any(row["table"] == "books" and row["from"] == "book_id" for row in foreign_keys)


def test_add_and_list_book(capsys):
    assert run_command("add", "吾輩は猫である", "--author", "夏目漱石") == 0
    add_output = capsys.readouterr().out
    assert "本を登録しました" in add_output
    assert "管理ID: 1" in add_output

    assert run_command("list") == 0
    list_output = capsys.readouterr().out
    assert "吾輩は猫である" in list_output
    assert "夏目漱石" in list_output
    assert "貸出可能" in list_output


def test_same_title_can_be_added_more_than_once(capsys):
    assert run_command("add", "銀河鉄道の夜") == 0
    assert run_command("add", "銀河鉄道の夜") == 0
    capsys.readouterr()

    assert run_command("count") == 0
    assert "2冊" in capsys.readouterr().out


def test_blank_title_is_rejected(capsys):
    assert run_command("add", "   ") == 1
    assert "タイトルを入力してください" in capsys.readouterr().err


def test_search_finds_partial_title(capsys):
    add_sample_book("吾輩は猫である")
    add_sample_book("こころ")
    capsys.readouterr()

    assert run_command("search", "猫") == 0
    output = capsys.readouterr().out
    assert "吾輩は猫である" in output
    assert "こころ" not in output


def test_search_with_no_matches(capsys):
    add_sample_book()
    capsys.readouterr()

    assert run_command("search", "存在しない題名") == 0
    assert "該当する本はありません" in capsys.readouterr().out


def test_lend_creates_fourteen_day_loan(capsys):
    book_id = add_sample_book()
    capsys.readouterr()

    assert run_command("lend", str(book_id), "山田さん") == 0
    assert "返却期限: 2026-09-17" in capsys.readouterr().out

    conn = db.get_connection()
    try:
        loan = conn.execute("SELECT * FROM loans WHERE book_id = ?", (book_id,)).fetchone()
    finally:
        conn.close()
    assert loan["borrower"] == "山田さん"
    assert loan["lent_on"] == "2026-09-03"
    assert loan["due_on"] == "2026-09-17"
    assert loan["is_extended"] == 0
    assert loan["returned_on"] is None


def test_book_cannot_be_lent_twice(capsys):
    book_id = add_sample_book()
    run_command("lend", str(book_id), "山田さん")
    capsys.readouterr()

    assert run_command("lend", str(book_id), "佐藤さん") == 1
    assert "すでに貸出中" in capsys.readouterr().err


def test_loans_displays_extension_and_status(capsys):
    book_id = add_sample_book()
    run_command("lend", str(book_id), "山田さん")
    capsys.readouterr()

    assert run_command("loans") == 0
    output = capsys.readouterr().out
    assert "山田さん" in output
    assert "2026-09-17" in output
    assert "なし" in output
    assert "貸出中" in output


def test_extend_adds_seven_days_and_can_only_run_once(capsys):
    book_id = add_sample_book()
    run_command("lend", str(book_id), "山田さん")
    capsys.readouterr()

    assert run_command("extend", str(book_id)) == 0
    assert "新しい返却期限: 2026-09-24" in capsys.readouterr().out

    conn = db.get_connection()
    try:
        loan = conn.execute("SELECT * FROM loans WHERE book_id = ?", (book_id,)).fetchone()
    finally:
        conn.close()
    assert loan["due_on"] == "2026-09-24"
    assert loan["is_extended"] == 1

    assert run_command("extend", str(book_id)) == 1
    assert "延長できるのは1回まで" in capsys.readouterr().err


def test_overdue_book_cannot_be_extended(capsys):
    book_id = add_sample_book()
    capsys.readouterr()
    conn = db.get_connection()
    try:
        with conn:
            conn.execute(
                """
                INSERT INTO loans
                    (book_id, borrower, lent_on, due_on, is_extended, returned_on)
                VALUES (?, ?, ?, ?, 0, NULL)
                """,
                (book_id, "山田さん", "2026-08-01", "2026-08-15"),
            )
    finally:
        conn.close()

    assert run_command("extend", str(book_id)) == 1
    assert "延滞している本は延長できません" in capsys.readouterr().err

    assert run_command("loans") == 0
    assert "延滞" in capsys.readouterr().out


def test_return_closes_loan_and_book_becomes_available(capsys):
    book_id = add_sample_book()
    run_command("lend", str(book_id), "山田さん")
    capsys.readouterr()

    assert run_command("return", str(book_id)) == 0
    assert "返却日: 2026-09-03" in capsys.readouterr().out

    conn = db.get_connection()
    try:
        returned_on = conn.execute(
            "SELECT returned_on FROM loans WHERE book_id = ?", (book_id,)
        ).fetchone()[0]
    finally:
        conn.close()
    assert returned_on == "2026-09-03"

    assert run_command("list") == 0
    assert "貸出可能" in capsys.readouterr().out


def test_nonexistent_book_is_rejected(capsys):
    assert run_command("lend", "999", "山田さん") == 1
    assert "指定した本は見つかりません" in capsys.readouterr().err


def test_returning_available_book_is_rejected(capsys):
    book_id = add_sample_book()
    capsys.readouterr()

    assert run_command("return", str(book_id)) == 1
    assert "貸出中ではありません" in capsys.readouterr().err


def test_unknown_command_is_reported_in_japanese(capsys):
    with pytest.raises(SystemExit) as error:
        library.main(["unknown"])
    assert error.value.code == 2
    assert "コマンドが見つかりません" in capsys.readouterr().err
