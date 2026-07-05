"""MySQL access layer, ported from Sources/Mysql.php.

Uses PyMySQL (blocking) but every call is expected to be invoked via
`await asyncio.to_thread(...)` from async code so it doesn't block the
event loop. Table-prefix indirection ("#___name" -> real table name) is
preserved since every Main module SQL string in the original bot uses it.
"""
from __future__ import annotations

import re
import sys
import time

import pymysql
import pymysql.cursors


class MySQL:
    def __init__(self, bot, dbase: str, user: str, password: str, server: str,
                 table_prefix: str | None = None, master_tablename: str | None = None,
                 no_underscore: bool = False):
        self.bot = bot
        self.botname = bot.botname
        self.error_count = 0
        self.underscore = "" if no_underscore else "_"

        self.dbase = dbase
        self.user = user
        self.password = password
        if ":" in server:
            self.server, port_str = server.rsplit(":", 1)
            self.port = int(port_str)
        else:
            self.server = server
            self.port = 3306

        botname_lower = self.botname.lower()
        if not master_tablename:
            self.master_tablename = f"{botname_lower}_tablenames"
        else:
            self.master_tablename = re.sub("<botname>", botname_lower, master_tablename, flags=re.I)

        if table_prefix is None:
            self.table_prefix = botname_lower
        else:
            self.table_prefix = re.sub("<botname>", botname_lower, table_prefix, flags=re.I)

        self.tablenames: dict[str, str] = {}
        self.conn: pymysql.connections.Connection | None = None

        self.connect(initial=True)
        self.query(
            f"CREATE TABLE IF NOT EXISTS {self.master_tablename} "
            "(internal_name VARCHAR(255) NOT NULL PRIMARY KEY, prefix VARCHAR(100), "
            "use_prefix VARCHAR(10) NOT NULL DEFAULT 'false', "
            "schemaversion INT(3) NOT NULL DEFAULT 1)"
        )
        self.query(
            "CREATE TABLE IF NOT EXISTS table_versions "
            "(internal_name VARCHAR(255) NOT NULL PRIMARY KEY, schemaversion INT(3) NOT NULL DEFAULT 1)"
        )

    # -- connection -----------------------------------------------------
    def connect(self, initial: bool = False) -> None:
        if initial:
            self.bot.log("MYSQL", "START", "Establishing MySQL database connection....")
        try:
            self.conn = pymysql.connect(
                host=self.server, port=self.port, user=self.user, password=self.password,
                database=self.dbase, autocommit=True, charset="utf8mb4",
            )
        except pymysql.MySQLError as exc:
            self.error(f"Cannot connect to the database server! {exc}", initial, connected=False)
            return
        if initial:
            self.bot.log("MYSQL", "START", "MySQL database connection test successful.")

    def close(self) -> None:
        if self.conn is not None:
            self.conn.close()
            self.conn = None

    def _ensure_connected(self) -> None:
        if self.conn is None:
            self.connect()
            return
        try:
            self.conn.ping(reconnect=True)
        except pymysql.MySQLError:
            self.connect()

    def real_escape_string(self, value) -> str:
        if self.conn is None:
            self.connect()
        escaped = self.conn.escape(str(value))
        # pymysql's escape() wraps strings in quotes; strip them to match
        # mysqli_real_escape_string()'s behaviour (no surrounding quotes).
        if escaped.startswith("'") and escaped.endswith("'"):
            escaped = escaped[1:-1]
        return escaped

    def error(self, text: str, fatal: bool = False, connected: bool = True) -> None:
        self.error_count += 1
        self.bot.log("MySQL", "ERROR", f"(# {self.error_count}) on query: {text}", connected)
        if fatal:
            self.bot.log("MySQL", "ERROR", "A fatal database error has occurred. Shutting down.", connected)
            sys.exit(1)

    # -- queries ----------------------------------------------------------
    def select(self, sql: str, as_dict: bool = False):
        self._ensure_connected()
        sql = self.add_prefix(sql)
        cursor_cls = pymysql.cursors.DictCursor if as_dict else pymysql.cursors.Cursor
        try:
            with self.conn.cursor(cursor_cls) as cur:
                cur.execute(sql)
                rows = cur.fetchall()
                return [list(r) if not as_dict else r for r in rows] if not as_dict else list(rows)
        except pymysql.MySQLError:
            self.error(sql)
            return False

    def query(self, sql: str) -> bool:
        self._ensure_connected()
        sql = self.add_prefix(sql)
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql)
            return True
        except pymysql.MySQLError:
            self.error(sql)
            return False

    def return_query(self, sql: str):
        self._ensure_connected()
        sql = self.add_prefix(sql)
        try:
            with self.conn.cursor() as cur:
                cur.execute(sql)
                return cur
        except pymysql.MySQLError:
            return False

    def drop_table(self, name: str) -> bool:
        return self.query(f"DROP TABLE {self.add_prefix(name)}")

    # -- table-name prefixing ---------------------------------------------
    def add_prefix(self, sql: str) -> str:
        return re.sub(r"\w?(#___.+?)\b", self._strip_prefix_control, sql)

    def _strip_prefix_control(self, match: re.Match) -> str:
        return self.get_tablename(match.group(1)[4:])

    def get_tablename(self, table: str) -> str:
        if table in self.tablenames:
            return self.tablenames[table]
        name = self.select(f"SELECT * FROM {self.master_tablename} WHERE internal_name = '{table}'")
        if not name:
            tablename = table if not self.table_prefix else f"{self.table_prefix}{self.underscore}{table}"
            self.query(
                f"INSERT INTO {self.master_tablename} (internal_name, prefix, use_prefix) "
                f"VALUES ('{table}', '{self.table_prefix}', 'true')"
            )
        else:
            if name[0][2] == "true" and self.table_prefix:
                tablename = f"{name[0][1]}{self.underscore}{table}"
            else:
                tablename = table
        self.tablenames[table] = tablename
        return tablename

    def define_tablename(self, table: str, use_prefix) -> str:
        if table in self.tablenames:
            return self.tablenames[table]
        name = self.select(f"SELECT * FROM {self.master_tablename} WHERE internal_name = '{table}'")
        use_prefix_str = str(use_prefix).lower()
        if not name:
            if use_prefix_str in ("true", "1") and self.table_prefix:
                prefix = self.table_prefix
                tablename = f"{prefix}{self.underscore}{table}"
                use_prefix_str = "true"
            else:
                prefix = ""
                tablename = table
                use_prefix_str = "false"
            self.query(
                f"INSERT INTO {self.master_tablename} (internal_name, prefix, use_prefix) "
                f"VALUES ('{table}', '{prefix}', '{use_prefix_str}')"
            )
        else:
            if name[0][2] == "true" and self.table_prefix:
                tablename = f"{name[0][1]}{self.underscore}{table}"
            else:
                tablename = table
        self.tablenames[table] = tablename
        return tablename

    def get_version(self, table: str) -> int:
        version = self.select(
            f"SELECT schemaversion, use_prefix FROM {self.master_tablename} WHERE internal_name = '{table}'"
        )
        if version:
            return version[0][0]
        return 1

    def set_version(self, table: str, version) -> None:
        self.query(
            f"UPDATE {self.master_tablename} SET schemaversion = {int(version)} "
            f"WHERE internal_name = '{table}'"
        )
