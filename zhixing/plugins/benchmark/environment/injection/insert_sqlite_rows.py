import os
import sqlite3
import tempfile
import ast
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


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

    use_transaction : bool (optional)
        Wrap all inserts inside a transaction.

    ------------------------------------------------------------
    """

    op_type = EnvironmentInitializerPluginType.ADB_INSERT_SALITE

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]
                ) -> bool:
        try:
            self.logger.info("SQLite inject: begin (pull -> local insert -> push)")
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
            self.logger.info("inserting %d row(s) into table %r", len(rows), table)

            # ====================== 4. 生成SQL插入语句 ======================
            sql_statements = self._generate_sql_statements(table, rows)
            if not sql_statements:
                self.logger.error("failed to build INSERT SQL (check row dicts)")
                return False
            
            # ====================== 5. 拉取设备端数据库到本地 ======================
            tmp_db = os.path.join(tempfile.gettempdir(), "unimobile_tmp.db")
            self.logger.info("pull DB device:%s -> host:%s", database, tmp_db)

            # 执行wal_checkpoint（确保数据落盘）
            device.shell(f"sqlite3 {database} 'PRAGMA wal_checkpoint(FULL);'")

            # 拉取数据库文件（替换为你原代码的_execute_command）
            result = device.pull(database, tmp_db)
            if result.exit_code != 0:
                self.logger.error("pull failed: %s", result.error)
                return False
            if not os.path.exists(tmp_db):
                self.logger.error("temp DB missing after pull: %s", tmp_db)
                return False
            
            # ====================== 6. 本地执行SQL插入 ======================
            try:
                conn = sqlite3.connect(tmp_db)
                cursor = conn.cursor()
                
                if use_transaction:
                    cursor.execute("BEGIN")
                
                for sql in sql_statements:
                    self.logger.debug("execute SQL: %s", sql)
                    cursor.execute(sql)
                
                if use_transaction:
                    conn.commit()
                conn.close()
                self.logger.info("local SQL inserts committed")
            except Exception as e:
                self.logger.error("local sqlite failed: %s", e, exc_info=True)
                return False
            
            # ====================== 7. 推送修改后的数据库回设备 ======================
            self.logger.info("force-stop %s before push-back", package_name)
            device.shell(f"am force-stop {package_name}")
            
            self.logger.info("push DB host:%s -> device:%s", tmp_db, database)
            push_result = device.push_file(tmp_db, database)
            if not push_result:
                self.logger.error("push_file returned False when pushing DB back")
                return False

            # ====================== 8. 清理临时文件 ======================
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

            self.logger.info("SQLite inject finished OK")
            return True

        except Exception as e:
            self.logger.error("execute failed: %s", e, exc_info=True)
            # 清理临时文件
            tmp_db = os.path.join(tempfile.gettempdir(), "unimobile_tmp.db")
            if os.path.exists(tmp_db):
                os.remove(tmp_db)
            return False
        
        
    def _generate_sql_statements(self, table: str, rows: List[Dict[str, Any]]) -> List[str]:
        """
        生成SQL插入语句（和你原代码逻辑一致）
        :param table: 目标表名
        :param rows: 已填充的行数据列表
        :return: SQL语句列表
        """
        sql_statements = []
        for row in rows:
            if not isinstance(row, dict):
                self.logger.error("each row must be a dict, got %r", type(row))
                return []
            
            # 提取列名和值
            columns = ", ".join(row.keys())
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
