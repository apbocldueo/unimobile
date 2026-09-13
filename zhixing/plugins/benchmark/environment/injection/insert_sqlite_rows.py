import os
import ast
import glob
import shlex
import shutil
import sqlite3
import tempfile
import time
import uuid
from typing import Dict, Any, List, Optional

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


def _quote_posix_single(s: str) -> str:
    """Wrap ``s`` in single quotes for ``/system/bin/sh`` on device."""
    return "'" + s.replace("'", "'\\''") + "'"


def _is_org_tasks_table(database: str, table: str) -> bool:
    """True for Tasks app DB where the schema has a reserved-word column ``order``."""
    return table == "tasks" and "org.tasks" in database


def _format_insert_column_list(column_names, quote_identifiers: bool) -> str:
    if quote_identifiers:
        return ", ".join('"' + name.replace('"', '""') + '"' for name in column_names)
    return ", ".join(column_names)


# Simple Calendar Pro ``events``: JSON rows only need start_ts, end_ts, title (and
# optionally location, description). Remaining ``CalendarEvent`` columns are filled here.
_CALENDAR_EVENT_ROW_DEFAULTS: Dict[str, Any] = {
    "location": "",
    "description": "",
    "repeat_interval": 0,
    "repeat_rule": 0,
    "reminder_1_minutes": -1,
    "reminder_2_minutes": -1,
    "reminder_3_minutes": -1,
    "reminder_1_type": 0,
    "reminder_2_type": 0,
    "reminder_3_type": 0,
    "repeat_limit": 0,
    "repetition_exceptions": "[]",
    "attendees": "",
    "import_id": "",
    "time_zone": "UTC",
    "flags": 0,
    "event_type": 1,
    "parent_id": 0,
    "last_updated": 0,
    "source": "simple-calendar",
    "availability": 0,
    "color": 0,
    "type": 0,
}


# Telephony ``sms`` (mmssms.db): JSON rows only need address, body (and optionally type).
# Other columns match typical AndroidWorld / AOSP inbox seed rows.
_OPENTRACKS_TRACK_ROW_DEFAULTS: Dict[str, Any] = {
    "description": "",
    "numpoints": 0,
    "maxspeed": 0.0,
    "minelevation": 0.0,
    "maxelevation": 0.0,
    "elevationgain": 0.0,
    "elevationloss": 0.0,
    "icon": "",
    "starttime_offset": 0,
}


_SMS_ROW_DEFAULTS: Dict[str, Any] = {
    "thread_id": 1,
    "body": "",
    "type": 1,
    "read": 1,
    "seen": 1,
    "date_sent": 0,
    "status": -1,
    "locked": 0,
    "sub_id": 1,
    "error_code": -1,
    "creator": "com.google.android.apps.messaging",
}

_THREADS_ROW_DEFAULTS: Dict[str, Any] = {
    "_id": 1,
    "date": 0,
    "message_count": 1,
    "snippet": "",
    "read": 1,
}

_TASKS_ROW_DEFAULTS: Dict[str, Any] = {
    "importance": 2,
    "dueDate": 0,
    "hideUntil": 0,
    "created": 0,
    "modified": 0,
    "completed": 0,
    "deleted": 0,
    "estimatedSeconds": 0,
    "elapsedSeconds": 0,
    "timerStart": 0,
    "notificationFlags": 0,
    "lastNotified": 0,
    "recurrence": None,
    "repeat_from": 0,
    "calendarUri": None,
    "remoteId": "",
    "collapsed": 0,
    "parent": 0,
    "order": None,
    "read_only": 0,
}

_JOPLIN_FOLDER_ROW_DEFAULTS: Dict[str, Any] = {
    "id": "",
    "title": "",
    "created_time": 0,
    "updated_time": 0,
    "user_created_time": 0,
    "user_updated_time": 0,
}

_JOPLIN_NOTE_ROW_DEFAULTS: Dict[str, Any] = {
    "id": "",
    "parent_id": "",
    "title": "",
    "body": "",
    "is_todo": 0,
    "todo_completed": 0,
    "todo_due": 0,
    "created_time": 0,
    "updated_time": 0,
    "user_created_time": 0,
    "user_updated_time": 0,
}


def _merge_known_table_defaults(
    database: str, table: str, rows: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Apply built-in defaults for known (database, table) pairs; pass through otherwise."""
    defaults: Optional[Dict[str, Any]] = None
    default_date_now = False

    if table == "events" and "com.simplemobiletools.calendar.pro" in database:
        defaults = _CALENDAR_EVENT_ROW_DEFAULTS
    elif table == "sms" and "com.android.providers.telephony" in database:
        defaults = _SMS_ROW_DEFAULTS
        default_date_now = True
    elif table == "threads" and "com.android.providers.telephony" in database:
        defaults = _THREADS_ROW_DEFAULTS
        default_date_now = True
    elif table == "tracks" and "de.dennisguse.opentracks" in database:
        defaults = _OPENTRACKS_TRACK_ROW_DEFAULTS
    elif table == "tasks" and "org.tasks" in database:
        defaults = _TASKS_ROW_DEFAULTS
    elif table == "folders" and "net.cozic.joplin" in database:
        defaults = _JOPLIN_FOLDER_ROW_DEFAULTS
    elif table == "notes" and "net.cozic.joplin" in database:
        defaults = _JOPLIN_NOTE_ROW_DEFAULTS

    if defaults is None:
        return rows

    merged: List[Dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            merged.append(row)
            continue
        full = dict(defaults)
        full.update(row)
        if default_date_now and "date" not in row:
            full["date"] = int(time.time() * 1000)
        if table == "tracks" and "de.dennisguse.opentracks" in database:
            if "activity_type" not in row and full.get("category"):
                full["activity_type"] = full["category"]
            start = full.get("starttime")
            stop = full.get("stoptime")
            if start is not None and stop is not None and "totaltime" not in row:
                full["totaltime"] = int(stop) - int(start)
            if "movingtime" not in row and "totaltime" in full:
                full["movingtime"] = full["totaltime"]
            dist = float(full.get("totaldistance") or 0)
            tt = int(full.get("totaltime") or 0)
            if tt > 0 and dist > 0 and "avgspeed" not in row:
                speed = dist / (tt / 1000.0)
                full["avgspeed"] = speed
                full["avgmovingspeed"] = speed
        if table == "tasks" and "org.tasks" in database:
            if not full.get("remoteId"):
                full["remoteId"] = str(uuid.uuid4().int)
            due = full.get("dueDate")
            if due and "created" not in row:
                full["created"] = int(due) - 604800000
            if due and "modified" not in row:
                full["modified"] = full.get("created", int(due) - 604800000)
        merged.append(full)
    return merged


@PluginRegistry.register(namespace="benchmark.environment.injection", name="android_injection_insert_sqlite_rows")
class ADBInjectionInsertSQLiteRowsGenerator(BaseEnvironmentInitializerOperation):
    """
    Insert rows into a SQLite database on the Android device.

    This initializer injects test data directly into an application's
    SQLite database using the sqlite3 command-line tool.

    The plugin dynamically constructs SQL INSERT statements based on
    the provided row dictionaries.

    This design allows the plugin to support different database schemas
    without hardcoding any table structure.

    ------------------------------------------------------------
    Example setup_config
    ------------------------------------------------------------

    {
        "type": "android_injection_insert_sqlite_rows",
        "app": "app", / "package": "package"
        "database": "/data/data/com.example.recipes/databases/recipes.db",
        "table": "recipes",
        "rows": [
            {
                "name": "Chicken Soup",
                "description": "Test recipe"
            },
            {
                "name": "Fried Rice",
                "description": "Another recipe"
            }
        ]
    }

    ------------------------------------------------------------
    Parameters
    ------------------------------------------------------------

    database : str
        Absolute path of the SQLite database file on device.

    table : str
        Target table name.

    rows : List[Dict]
        List of dictionaries representing rows to insert.

        Built-in defaults (row dict overrides defaults):

        - ``events`` in ``.../com.simplemobiletools.calendar.pro/.../events.db``:
          need ``start_ts``, ``end_ts``, ``title``; optional ``location``, ``description``.
        - ``sms`` in ``.../com.android.providers.telephony/.../mmssms.db``:
          need ``address``, ``body``; optional ``type`` (default ``1`` = inbox).
          ``date`` defaults to now (epoch ms) when omitted.
        - ``threads`` in ``.../com.android.providers.telephony/.../mmssms.db``:
          optional helper rows for Messages UI. Usually auto-generated from ``sms`` when
          ``auto_threads`` is enabled.

    use_transaction : bool (optional)
        Wrap all inserts inside a transaction.

    auto_threads : bool (optional)
        When true, and when inserting into ``sms`` in ``mmssms.db``, also insert a best-
        effort matching row into ``threads`` so Messages UI can show the conversation list.
        Defaults to ``False`` to preserve compatibility with existing JSON tasks.

    **SQLite / UI note:** Many apps (e.g. Pro Expense) filter the main list by **date**.
    If ``created_date`` / ``modified_date`` are far in the past, rows still exist in SQL
    but the UI looks empty—use recent epoch-millis (e.g. ``int(time.time() * 1000)`` in
    generated tasks) for the default tab to show them.

    **Device sync:** Prefer pull → local Python ``sqlite3`` → push (WAL-consistent). If local
    insert fails (e.g. Windows host lacks FTS4 for Broccoli), fall back to ``adb shell
    sqlite3`` on the device (same as ``android_reset_clear_sqlite_rows``).

    ------------------------------------------------------------
    """

    op_type = EnvironmentInitializerPluginType.ADB_INSERT_SALITE

    @staticmethod
    def _find_pulled_db_file(staging: str, remote_db_dir: str, db_basename: str) -> Optional[str]:
        """Resolve local path to ``db_basename`` after ``adb pull <remote_db_dir> <staging>``."""
        dir_leaf = os.path.basename(os.path.normpath(remote_db_dir))
        candidates = [
            os.path.join(staging, dir_leaf, db_basename),
            os.path.join(staging, db_basename),
        ]
        for c in candidates:
            if os.path.isfile(c):
                return c
        for found in glob.glob(os.path.join(staging, "**", db_basename), recursive=True):
            if os.path.isfile(found):
                return found
        return None

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        staging: Optional[str] = None
        try:
            self.logger.info(
                "SQLite inject: begin (stop -> local pull/insert/push, else on-device sqlite3)"
            )
            # ====================== 1. 核心：获取Device实例（操作手机的关键） ======================
            device = meta.get("device")
            if not device:
                self.logger.error("meta has no 'device'")
                return False
            # ====================== 2. 校验核心参数（新JSON格式） ======================
            
            # 从params中读取已填充${xxx}的业务参数
            database = params.get("database")
            table = params.get("table")
            rows_config = params.get("rows")
            if(isinstance(rows_config,str)):
                rows_config = ast.literal_eval(rows_config)
            use_transaction = params.get("use_transaction", True)
            auto_threads = bool(params.get("auto_threads", False))

            # 必传参数校验
            if not database:
                self.logger.error("params missing 'database'")
                return False
            if not table:
                self.logger.error("params missing 'table'")
                return False
            if not rows_config:
                self.logger.error("params missing 'rows'")
                return False
            
            package_name = meta.get("app_package") or params.get("package") or params.get("app")
            if not package_name:
                self.logger.error("need package name in meta.app_package or params.package / params.app")
                return False

            # 处理app名称转包名
            if package_name.lower() != package_name:
                if not hasattr(device, "app_package_names"):
                    self.logger.error("device has no app_package_names map")
                    return False
                app_name = package_name.lower()
                if app_name not in device.app_package_names:
                    self.logger.error(
                        "unknown app alias %r; known: %s",
                        app_name,
                        list(device.app_package_names.keys()),
                    )
                    return False
                package_name = device.app_package_names[app_name]
            # ====================== 3. 解析行数据（仅保留静态列表，适配新架构占位符） ======================
            if not isinstance(rows_config, list):
                self.logger.error("'rows' must be a list of dicts after placeholder render")
                return False
            rows = rows_config
            if len(rows) == 0:
                self.logger.error("'rows' is empty")
                return False
            rows = _merge_known_table_defaults(database, table, rows)
            self.logger.info("inserting %d row(s) into table %r", len(rows), table)

            auto_thread_rows: List[Dict[str, Any]] = []
            if auto_threads and table == "sms" and "com.android.providers.telephony" in database:
                for row in rows:
                    if not isinstance(row, dict):
                        continue
                    thread_row = {
                        "_id": row.get("thread_id", 1),
                        "date": row.get("date", int(time.time() * 1000)),
                        "message_count": 1,
                        "snippet": row.get("body", ""),
                        "read": row.get("read", 1),
                    }
                    auto_thread_rows.append(thread_row)
                if auto_thread_rows:
                    self.logger.info(
                        "auto_threads enabled: generating %d helper row(s) for threads",
                        len(auto_thread_rows),
                    )

            # ====================== 4. 生成SQL插入语句 ======================
            quote_column_names = _is_org_tasks_table(database, table)
            if quote_column_names:
                self.logger.debug(
                    "quoting INSERT column names for org.tasks (reserved word: order)"
                )
            sql_statements = self._generate_sql_statements(
                table, rows, quote_column_names=quote_column_names
            )
            if not sql_statements:
                self.logger.error("failed to build INSERT SQL (check row dicts)")
                return False

            if auto_thread_rows:
                sql_statements.extend(
                    self._generate_sql_statements(
                        "threads", auto_thread_rows, quote_column_names=False
                    )
                )

            remote_db_dir = os.path.dirname(database)
            db_basename = os.path.basename(database)
            if not remote_db_dir or remote_db_dir == database:
                self.logger.error("database path has no parent directory: %r", database)
                return False

            # ====================== 5. 停应用 → checkpoint ======================
            self.logger.info("force-stop %s before DB inject", package_name)
            device.shell(f"am force-stop {package_name}")

            chk = device.shell(
                f"sqlite3 {_quote_posix_single(database)} {_quote_posix_single('PRAGMA wal_checkpoint(FULL);')}"
            )
            if chk.exit_code != 0:
                self.logger.warning(
                    "wal_checkpoint best-effort failed exit=%s err=%s",
                    chk.exit_code,
                    chk.error,
                )

            # ====================== 6. 优先本地 pull → insert → push ======================
            staging = tempfile.mkdtemp(prefix="unimobile_sqlinject_")
            if self._insert_via_local_pull_push(
                device,
                database,
                remote_db_dir,
                db_basename,
                staging,
                sql_statements,
                use_transaction,
            ):
                self.logger.info("SQLite inject finished OK (local pull/insert/push)")
                return True

            self.logger.warning(
                "local pull/insert/push failed; falling back to on-device sqlite3"
            )

            # ====================== 7. 回退：设备端 sqlite3（支持 FTS4 等扩展） ======================
            if not self._insert_via_device_sqlite3(
                device, database, sql_statements, use_transaction
            ):
                return False

            self.logger.info("SQLite inject finished OK (on-device sqlite3)")
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            return False
        finally:
            if staging and os.path.isdir(staging):
                shutil.rmtree(staging, ignore_errors=True)

    def _insert_via_local_pull_push(
        self,
        device: Any,
        database: str,
        remote_db_dir: str,
        db_basename: str,
        staging: str,
        sql_statements: List[str],
        use_transaction: bool,
    ) -> bool:
        """Pull DB dir, insert rows with host Python sqlite3, push back."""
        self.logger.info("pull DB dir device:%s -> host:%s", remote_db_dir, staging)
        result = device.pull(remote_db_dir, staging)
        if result.exit_code != 0:
            self.logger.error("pull directory failed: %s", result.error)
            return False

        tmp_db = self._find_pulled_db_file(staging, remote_db_dir, db_basename)
        if not tmp_db:
            self.logger.error(
                "after pull, could not find %r under staging %r (listing: %s)",
                db_basename,
                staging,
                os.listdir(staging),
            )
            return False
        self.logger.info("using pulled DB file at host:%s", tmp_db)

        try:
            conn = sqlite3.connect(tmp_db)
            cursor = conn.cursor()

            if use_transaction:
                cursor.execute("BEGIN")

            for sql in sql_statements:
                self.logger.debug("execute SQL (local): %s", sql)
                cursor.execute(sql)

            if use_transaction:
                conn.commit()
            conn.close()
            self.logger.info("local SQL inserts committed")
        except Exception as e:
            self.logger.error("local sqlite failed: %s", e, exc_info=True)
            return False

        clear_cmd = f"rm -rf -- {shlex.quote(remote_db_dir)}/*"
        clr = device.shell(clear_cmd)
        if clr.exit_code != 0:
            self.logger.error(
                "clear remote db dir failed cmd=%r exit=%s err=%s",
                clear_cmd,
                clr.exit_code,
                clr.error,
            )
            return False
        self.logger.info("cleared remote directory %r", remote_db_dir)

        self.logger.info("push DB host:%s -> device:%s", tmp_db, database)
        if not device.push_file(tmp_db, database):
            self.logger.error("push_file returned False when pushing DB back")
            return False

        mod = device.shell(f"chmod 777 {shlex.quote(database)}")
        if mod.exit_code != 0:
            self.logger.warning("chmod 777 failed exit=%s err=%s", mod.exit_code, mod.error)
        else:
            self.logger.info("chmod 777 applied to %r", database)
        return True

    def _insert_via_device_sqlite3(
        self,
        device: Any,
        database: str,
        sql_statements: List[str],
        use_transaction: bool,
    ) -> bool:
        """Run INSERT statements on device via ``sqlite3`` (FTS4-safe on Android)."""
        db_q = _quote_posix_single(database)
        if use_transaction:
            to_run = ["BEGIN; " + " ".join(sql_statements) + " COMMIT;"]
        else:
            to_run = list(sql_statements)

        for sql in to_run:
            self.logger.debug("execute SQL (device): %s", sql)
            cmd = f"sqlite3 {db_q} {_quote_posix_single(sql)}"
            result = device.shell(cmd)
            if result.exit_code != 0 or (result.error and result.error.strip()):
                self.logger.error(
                    "device sqlite3 failed sql=%r exit_code=%s stderr=%s",
                    sql,
                    result.exit_code,
                    result.error,
                )
                return False

        mod = device.shell(f"chmod 777 {shlex.quote(database)}")
        if mod.exit_code != 0:
            self.logger.warning("chmod 777 failed exit=%s err=%s", mod.exit_code, mod.error)
        else:
            self.logger.info("chmod 777 applied to %r", database)
        return True

    def _generate_sql_statements(
        self,
        table: str,
        rows: List[Dict[str, Any]],
        *,
        quote_column_names: bool = False,
    ) -> List[str]:
        """
        生成SQL插入语句（和你原代码逻辑一致）
        :param table: 目标表名
        :param rows: 已填充的行数据列表
        :param quote_column_names: 为列名加双引号（仅 org.tasks / tasks 表需要）
        :return: SQL语句列表
        """
        sql_statements = []
        for row in rows:
            if not isinstance(row, dict):
                self.logger.error("each row must be a dict, got %r", type(row))
                return []
            
            # 提取列名和值
            columns = _format_insert_column_list(row.keys(), quote_column_names)
            values = []
            for value in row.values():
                if value is None:
                    values.append("NULL")
                elif isinstance(value, (int, float)):
                    values.append(str(value))
                else:
                    # 转义单引号
                    escaped = str(value).replace("'", "''")
                    values.append(f"'{escaped}'")
            
            values_sql = ", ".join(values)
            sql = f"INSERT INTO {table} ({columns}) VALUES ({values_sql});"
            sql_statements.append(sql)
        
        return sql_statements
