import time
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType
from zhixing.core.factory import PluginRegistry


@PluginRegistry.register(namespace="benchmark.environment.reset", name="android_reset_clear_sqlite_rows")
class ADBResetClearSqliteTableGenerator(BaseEnvironmentInitializerOperation):
    """Run DELETE FROM on device via sqlite3 shell. Params: database, tables[], package or app."""

    op_type = EnvironmentInitializerPluginType.ADB_CLEAR_SQLITE_TABLE

    def execute(self
                , meta: Dict[str, Any]
                , params: Dict[str, Any]) -> bool:
        """
        Args:
            meta (Dict[str, Any]): 包含device实例
            params (Dict[str, Any]): 
            {
                "database": "database"
                "tables": ["table1", "table2"],
                "app/package": "",
                "keep_table_structure": True
            }

        Returns:
            bool: 操作是否成功
        """
        self.logger.info("[SQLiteClear] 开始执行数据库清空操作")
        # ====================== 1. 获取Device实例 ======================
        device = meta.get("device")
        if not device:
            self.logger.error("meta has no 'device'")
            return False

        database = params.get("database")
        tables = params.get("tables")
        if not database:
            self.logger.error("params missing 'database'")
            return False
        if not tables or not isinstance(tables, list):
            self.logger.error("params 'tables' must be a non-empty list of table names")
            return False

        package_name = params.get("package")
        app_name = params.get("app")
        if not package_name and not app_name:
            self.logger.error("params need 'package' or 'app'")
            return False

        resolved = package_name
        if not resolved and app_name:
            key = app_name.lower()
            names = getattr(device, "app_package_names", None)
            if not names or key not in names:
                self.logger.error(
                    "unknown app %r; known: %s",
                    app_name,
                    list(names.keys()) if names else [],
                )
                return False
            resolved = names[key]

        if not resolved:
            self.logger.error("could not resolve target package")
            return False

        sql_statements = self._generate_sql_statements(tables)
        if not sql_statements:
            self.logger.error("no SQL generated (empty tables list?)")
            return False

        self.logger.info(
            "clearing %d table(s) on %r for package %s",
            len(sql_statements),
            database,
            resolved,
        )

        for sql in sql_statements:
            result = device.shell(f"sqlite3 {database} '{sql}'")
            if result.exit_code != 0 or (result.error and result.error.strip()):
                self.logger.error(
                    "sqlite3 failed sql=%r exit_code=%s stderr=%s",
                    sql,
                    result.exit_code,
                    result.error,
                )
                return False
            time.sleep(1)

        self.logger.info("force-stop %s after table clear", resolved)
        device.shell(f"am force-stop {resolved}")
        self.logger.info("SQLite table clear finished OK")
        return True
    
    def _generate_sql_statements(self, tables: List[str]) -> List[str]:
        """生成 删除 database 的语句

        Args:
            database (List[str]): _description_

        Returns:
            List[str]: _description_
        """
        sql_statements = []
        for table in tables:
            sql = f"DELETE FROM {table};"
            sql_statements.append(sql)
        
        return sql_statements
    
    