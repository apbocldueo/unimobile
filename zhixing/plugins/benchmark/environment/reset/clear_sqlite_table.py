import os
import time
import shlex
import sqlite3
import tempfile
import subprocess
import logging
from typing import Dict, Any, List

from zhixing.core.benchmark.interface import BaseEnvironmentInitializerOperation
from zhixing.core.benchmark.protocol import EnvironmentInitializerPluginType

logger = logging.getLogger(__name__)

class ADBResetClearSqliteTableGenerator(BaseEnvironmentInitializerOperation):

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
        logger.info("[SQLiteClear] 开始执行数据库清空操作")
        # ====================== 1. 获取Device实例 ======================
        device = meta.get("device")
        if not device:
            logger.error("[SQLiteInsert] meta中缺少device实例！")
            return False
        
        database = params.get("database")
        tables = params.get("tables")
        keep_table_structure = params.get("keep_table_structure", True)

        # 参数检验
        if not database:
            logger.error("[SQLiteClear] params中缺少database参数")
            return False
        
        package_name = params.get("package")
        app_name = params.get("app")

        if not package_name and not app_name:
            logger.error("[SQLiteClear] params必须包含 package 或 app参数")
            return False
        
        # 解析包名
        resolved_package = None
        if package_name:
            resolved_package = package_name
            logger.info(f"[SQLiteClear] 使用显式包名：{resolved_package}")
        elif app_name:
            app_name_lower = app_name.lower()
            if not hasattr(device.device, "app_package_names"):
                logger.error("[SQLiteClear] Device实例未暴露'app_package_names'属性")
                return False
            if app_name_lower not in device.device.app_package_names:
                logger.error(f"[SQLiteClear] 未知应用'{app_name}'，可用应用：{list(device.device.app_package_names.keys())}")
                return False
            resolved_package = device.device.app_package_names[app_name_lower]
            logger.info(f"[SQLiteClear] 解析应用名'{app_name}' → 包名'{resolved_package}'")

        if not resolved_package:
            logger.error("[SQLiteClear] 包名解析失败")
            return False
        
        database = params.get("database")
        
        # 生成 sql 语句（保留原有逻辑）
        sql_statements = self._generate_sql_statements(tables=tables)
        if not sql_statements:
            logger.error("[SQLiteClear] 生成SQL语句失败")
            return False
        
        # 拉取设备端数据库到本地
        # tmp_db = os.path.join(tempfile.gettempdir(), "unimobile_tmp.db")
        # logger.info(f"[SQLiteClear] 拉取数据库：{database} → 本地{tmp_db}")
        # device.device.shell(f"sqlite3 {database} 'PRAGMA wal_checkpoint(FULL);'")

        # 运行 adb 指令
        for sql in sql_statements:
            result = device.device.shell(f"sqlite3 {database} '{sql}'")
            if result.error: 
                logger.error(f"[SQLiteClear] cmd 执行失败, 错误: {result.error}")
                return False
            time.sleep(1)

        # 推送修改后的数据库回设备
        logger.info(f"[SQLiteClear] 强制停止应用：{resolved_package}")  # 修复：用resolved_package而非package_name
        device.device.shell(f"am force-stop {resolved_package}")

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
    
    