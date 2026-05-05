import os
import sqlite3
import tempfile
import logging
import ast
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry

logger = logging.getLogger(__name__)

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
            logger.info("[SQLiteInsert] 开始执行数据库插入操作")
            # ====================== 1. 核心：获取Device实例（操作手机的关键） ======================
            device = meta.get("device")
            if not device:
                logger.error("[SQLiteInsert] meta中缺少device实例！")
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
                logger.error("[SQLiteInsert] params中缺少database参数")
                return False
            if not table:
                logger.error("[SQLiteInsert] params中缺少table参数")
                return False
            if not rows_config:
                logger.error("[SQLiteInsert] params中缺少rows参数")
                return False
            
            package_name = meta.get("app_package") or params.get("package") or params.get("app")
            if not package_name:
                logger.error("[SQLiteInsert] 缺少package/app参数（meta或params中必须配置）")
                return False

            # 处理app名称转包名
            if package_name.lower() != package_name:
                if not hasattr(device.device, "app_package_names"):
                    logger.error("[SQLiteInsert] Device实例未暴露app_package_names属性")
                    return False
                app_name = package_name.lower()
                if app_name not in device.device.app_package_names:
                    logger.error(f"[SQLiteInsert] 未知应用'{app_name}'，可用应用：{list(device.device.app_package_names.keys())}")
                    return False
                package_name = device.device.app_package_names[app_name]
            # ====================== 3. 解析行数据（仅保留静态列表，适配新架构占位符） ======================
            if not isinstance(rows_config, list):
                logger.error("[SQLiteInsert] rows必须是列表格式（已填充${xxx}占位符）")
                return False
            rows = rows_config
            if len(rows) == 0:
                logger.error("[SQLiteInsert] 解析后的rows列表为空")
                return False
            logger.info(f"[SQLiteInsert] 准备插入{len(rows)}行数据到表'{table}'")

            # ====================== 4. 生成SQL插入语句 ======================
            sql_statements = self._generate_sql_statements(table, rows)
            if not sql_statements:
                logger.error("[SQLiteInsert] 生成SQL语句失败")
                return False
            
            # ====================== 5. 拉取设备端数据库到本地 ======================
            tmp_db = os.path.join(tempfile.gettempdir(), "unimobile_tmp.db")
            logger.info(f"[SQLiteInsert] 拉取数据库：{database} → 本地{tmp_db}")

            # 执行wal_checkpoint（确保数据落盘）
            device.device.shell(f"sqlite3 {database} 'PRAGMA wal_checkpoint(FULL);'")

            # 拉取数据库文件（替换为你原代码的_execute_command）
            pull_cmd = f"{device.device._adb_prefix()} pull {database} {tmp_db}"
            result = device.device.pull(database, tmp_db)
            if result.exit_code != 0:
                logger.error(f"[SQLiteInsert] 拉取数据库失败：{result.error}")
                return False
            if not os.path.exists(tmp_db):
                logger.error("[SQLiteInsert] 本地临时数据库文件不存在")
                return False
            
            # ====================== 6. 本地执行SQL插入 ======================
            try:
                conn = sqlite3.connect(tmp_db)
                cursor = conn.cursor()
                
                if use_transaction:
                    cursor.execute("BEGIN")
                
                for sql in sql_statements:
                    logger.debug(f"[SQLiteInsert] 执行SQL：{sql}")
                    cursor.execute(sql)
                
                if use_transaction:
                    conn.commit()
                conn.close()
                logger.info("[SQLiteInsert] 本地SQL插入完成")
            except Exception as e:
                logger.error(f"[SQLiteInsert] 本地SQL执行失败：{str(e)}", exc_info=True)
                return False
            
            # ====================== 7. 推送修改后的数据库回设备 ======================
            logger.info(f"[SQLiteInsert] 强制停止应用：{package_name}")
            device.device.shell(f"am force-stop {package_name}")
            
            logger.info(f"[SQLiteInsert] 推送数据库回设备：{tmp_db} → {database}")
            push_result = device.push_file(tmp_db, database)
            if not push_result:
                logger.error("[SQLiteInsert] 推送数据库回设备失败")
                return False

            # ====================== 8. 清理临时文件 ======================
            if os.path.exists(tmp_db):
                os.remove(tmp_db)

            logger.info("[SQLiteInsert] SQLite数据插入操作成功完成")
            return True

        except Exception as e:
            logger.error(f"[SQLiteInsert] 执行异常：{str(e)}", exc_info=True)
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
                logger.error("[SQLiteInsert] 每行数据必须是字典格式")
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
