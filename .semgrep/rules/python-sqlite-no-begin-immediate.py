import sqlite3


def bad_executescript_bare(conn: sqlite3.Connection) -> None:
    # ruleid: python-sqlite-no-begin-immediate
    conn.executescript("CREATE TABLE t (id INTEGER)")


def bad_executescript_variable(conn: sqlite3.Connection, sql: str) -> None:
    # ruleid: python-sqlite-no-begin-immediate
    conn.executescript(sql)


def bad_executescript_after_begin(conn: sqlite3.Connection) -> None:
    conn.execute("BEGIN IMMEDIATE")
    # ruleid: python-sqlite-no-begin-immediate
    conn.executescript("CREATE TABLE t (id INTEGER)")


def ok_cursor_execute(conn: sqlite3.Connection) -> None:
    # ok: python-sqlite-no-begin-immediate
    conn.execute("CREATE TABLE t (id INTEGER)")
