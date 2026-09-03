# 蔵書貸出管理ツール

自宅にある本と、友人への貸出状況を管理する個人向けのコマンドラインツールです。本の登録・検索・冊数確認、貸出・返却、返却期限の延長、延滞確認ができます。データはSQLiteの`bookshelf.db`へ保存されます。

## 提出書類

- [要件定義書](requirements.md)
- [仕様設計書](specification.md)

## 必要な環境

- Python 3.10以上
- SQLite（Pythonの標準ライブラリに含まれます）
- pytest（テスト実行時のみ）

## 起動方法

リポジトリのフォルダで、次のコマンドを実行します。

```bash
python library.py --help
```

初回実行時に`bookshelf.db`が自動作成されます。

## コマンド一覧

### 本を登録する

```bash
python library.py add "吾輩は猫である" --author "夏目漱石"
```

著者名は省略できます。

### 本を一覧表示する

```bash
python library.py list
```

### タイトルから検索する

```bash
python library.py search "猫"
```

### 本の合計冊数を表示する

```bash
python library.py count
```

### 本を貸し出す

```bash
python library.py lend 1 "山田さん"
```

貸出日は実行日、返却期限は実行日の14日後になります。

### 貸出中の本を表示する

```bash
python library.py loans
```

返却期限を過ぎた本は「延滞」と表示されます。

### 返却期限を延長する

```bash
python library.py extend 1
```

返却期限前に1回だけ、現在の返却期限から7日間延長できます。延滞中の本は延長できません。

### 本を返却する

```bash
python library.py return 1
```

## テスト方法

pytestをインストールし、テストを実行します。

```bash
python -m pip install -r requirements-dev.txt
python -m pytest
```

テストでは一時的なSQLiteデータベースを使用するため、実際の`bookshelf.db`は変更されません。

## ファイル構成

- `library.py`：コマンドの受け付けと各機能の処理
- `db.py`：SQLiteへの接続とテーブルの初期化
- `tests/test_library.py`：pytestによるテストコード
- `requirements.md`：要件定義書
- `specification.md`：仕様設計書

## データベース

- `books`：本の管理ID、タイトル、著者名、登録日時を保存
- `loans`：貸出相手、貸出日、返却期限、延長の有無、返却日を保存

`books`と`loans`は1対多の関係で、`loans.book_id`が`books.id`を参照します。

## 意思決定と理由

- 通常の返却期限は、本を読む期間として分かりやすい14日後としました。
- 返却期限前なら1回だけ7日間延長できます。何度も延長されるのを防ぐため、回数を制限しています。
- 返却期限を過ぎた本は「延滞」と表示し、誰に貸しているか確認できるようにしました。
- 同じタイトルの本でも管理IDが異なるため、複数冊登録できます。
