import pyodbc
import logging
import configparser
from pathlib import Path

class DatabaseManager:
    def __init__(self, config_path: Path):
        self.config = configparser.ConfigParser()
        self.config.read(config_path)
        self.db_cfg = self.config["DATABASE"]

    def _get_conn_str(self, server_override=None, database_override=None):
        server = server_override or self.db_cfg["source_server"]
        database = database_override or self.db_cfg["source_database"]
        driver = self.db_cfg["driver"]
        auth_mode = self.db_cfg.get("auth_mode", "windows").lower()

        if auth_mode == "windows":
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
        else:
            user = self.db_cfg["username"]
            pwd = self.db_cfg["password"]
            return f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={user};PWD={pwd};"

    def get_source_connection(self):
        conn_str = self._get_conn_str(self.db_cfg["source_server"], self.db_cfg["source_database"])
        return pyodbc.connect(conn_str)

    def get_dest_connection(self):
        conn_str = self._get_conn_str(self.db_cfg["destination_server"], self.db_cfg["destination_database"])
        return pyodbc.connect(conn_str)
        
    def get_history_connection(self):
        # By default, history is stored in the destination server/DB
        history_svr = self.db_cfg.get("history_server", self.db_cfg["destination_server"])
        history_db = self.db_cfg.get("history_database", self.db_cfg["destination_database"])
        conn_str = self._get_conn_str(history_svr, history_db)
        return pyodbc.connect(conn_str)
