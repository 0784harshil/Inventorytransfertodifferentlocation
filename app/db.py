import pyodbc
import logging
import configparser
from pathlib import Path

# Creates audit tables if missing (safe to run repeatedly)
TRANSFER_TABLES_SQL = """
IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TransferHeader' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.TransferHeader (
        TransferID INT IDENTITY(1,1) PRIMARY KEY,
        TransferDate DATETIME DEFAULT GETDATE(),
        SourceLocation NVARCHAR(255) NOT NULL,
        DestinationLocation NVARCHAR(255) NOT NULL,
        CreatedBy NVARCHAR(100) NULL,
        Notes NVARCHAR(MAX) NULL
    );
END

IF NOT EXISTS (SELECT * FROM sys.tables WHERE name = 'TransferDetail' AND schema_id = SCHEMA_ID('dbo'))
BEGIN
    CREATE TABLE dbo.TransferDetail (
        TransferDetailID INT IDENTITY(1,1) PRIMARY KEY,
        TransferID INT NOT NULL,
        ItemNum NVARCHAR(100) NOT NULL,
        ItemName NVARCHAR(255) NULL,
        Quantity DECIMAL(18, 4) NOT NULL,
        Cost DECIMAL(18, 4) NULL,
        SourceStockBefore DECIMAL(18, 4) NULL,
        SourceStockAfter DECIMAL(18, 4) NULL,
        DestinationStockBefore DECIMAL(18, 4) NULL,
        DestinationStockAfter DECIMAL(18, 4) NULL,
        CONSTRAINT FK_TransferHeader FOREIGN KEY (TransferID) REFERENCES dbo.TransferHeader(TransferID)
    );
    CREATE INDEX IX_TransferDetail_ItemNum ON dbo.TransferDetail(ItemNum);
END
"""

class DatabaseManager:
    def __init__(self, config_path: Path):
        self.config_path = Path(config_path).resolve()
        self.config = configparser.ConfigParser(interpolation=None)
        # Keep option names as written in config.ini
        self.config.optionxform = str

        self._load_config_file()
        self._parse_stores()
        self._select_active_stores_from_config()

        logging.info(f"Bound to config file: {self.config_path}")
        logging.info(
            f"Loaded {len(self.stores)} store(s) from config.ini: "
            + ", ".join(
                f"{k}={v['name']}@{v['server']}/{v['database']}"
                for k, v in self.stores.items()
            )
        )
        src = self.stores.get(self.active_source_key, {})
        dest = self.stores.get(self.active_dest_key, {})
        logging.info(
            f"Active route from config — "
            f"SOURCE {self.active_source_key}: {src.get('server')}/{src.get('database')} -> "
            f"DEST {self.active_dest_key}: {dest.get('server')}/{dest.get('database')}"
        )

        # Ensure transfer history tables exist so transfers don't fail on a fresh DB
        self.ensure_transfer_tables()

    def _load_config_file(self):
        """Read and validate config.ini from the bound path."""
        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Config file not found:\n{self.config_path}\n\n"
                "Place config.ini in the app folder (or next to the .exe)."
            )

        read_ok = self.config.read(self.config_path, encoding="utf-8")
        if not read_ok:
            raise RuntimeError(
                f"Could not read config file (empty or unreadable):\n{self.config_path}"
            )

        if "DATABASE" not in self.config:
            raise RuntimeError(
                f"[DATABASE] section is missing in:\n{self.config_path}"
            )

        self.db_cfg = self.config["DATABASE"]
        required = ["driver"]
        missing = [k for k in required if not self.db_cfg.get(k)]
        auth_mode = self.db_cfg.get("auth_mode", "windows").lower()
        if auth_mode == "sql":
            for k in ("username", "password"):
                if not self.db_cfg.get(k):
                    missing.append(k)
        if missing:
            raise RuntimeError(
                f"Config file is missing required DATABASE keys: {', '.join(missing)}\n"
                f"File: {self.config_path}"
            )

    def _parse_stores(self):
        self.stores = {}
        if "STORES" in self.config:
            for key, value in self.config.items("STORES"):
                parts = [p.strip() for p in value.split("|")]
                if len(parts) >= 3:
                    self.stores[key] = {
                        "name": parts[0],
                        "server": parts[1],
                        "database": parts[2],
                    }

        # Fallback if [STORES] is missing/empty
        if not self.stores:
            self.stores["source"] = {
                "name": self.config.get("APP", "store_name", fallback="Source Store"),
                "server": self.db_cfg.get("source_server", ""),
                "database": self.db_cfg.get("source_database", ""),
            }
            self.stores["destination"] = {
                "name": "Destination Store",
                "server": self.db_cfg.get("destination_server", ""),
                "database": self.db_cfg.get("destination_database", ""),
            }

    def _select_active_stores_from_config(self):
        """Pick active source/dest from [DATABASE] when possible, else first two stores."""
        store_keys = list(self.stores.keys())
        if not store_keys:
            raise RuntimeError(f"No stores defined in config.ini:\n{self.config_path}")

        src_server = (self.db_cfg.get("source_server") or "").strip()
        src_db = (self.db_cfg.get("source_database") or "").strip()
        dest_server = (self.db_cfg.get("destination_server") or "").strip()
        dest_db = (self.db_cfg.get("destination_database") or "").strip()

        matched_src = None
        matched_dest = None
        for key, store in self.stores.items():
            if (
                matched_src is None
                and src_server
                and src_db
                and store["server"].lower() == src_server.lower()
                and store["database"].lower() == src_db.lower()
            ):
                matched_src = key
            if (
                matched_dest is None
                and dest_server
                and dest_db
                and store["server"].lower() == dest_server.lower()
                and store["database"].lower() == dest_db.lower()
            ):
                matched_dest = key

        self.active_source_key = matched_src or store_keys[0]
        if matched_dest and matched_dest != self.active_source_key:
            self.active_dest_key = matched_dest
        else:
            self.active_dest_key = (
                store_keys[1] if len(store_keys) > 1 else store_keys[0]
            )

        # Keep [DATABASE] aligned with the resolved active stores
        self.sync_database_section()

    def _get_conn_str(self, server_override=None, database_override=None):
        server = server_override or self.db_cfg["source_server"]
        database = database_override or self.db_cfg["source_database"]
        driver = self.db_cfg["driver"]
        auth_mode = self.db_cfg.get("auth_mode", "windows").lower()

        # Connection Timeout helps fail fast when an IP/server is wrong after Manage Stores edits
        timeout = self.db_cfg.get("connection_timeout", "8")

        if auth_mode == "windows":
            return (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"Trusted_Connection=yes;Connection Timeout={timeout};"
            )
        else:
            user = self.db_cfg["username"]
            pwd = self.db_cfg["password"]
            return (
                f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};"
                f"UID={user};PWD={pwd};Connection Timeout={timeout};"
            )

    def test_connection(self, server: str, database: str):
        """Validate that a server/database can be reached with current auth settings."""
        conn_str = self._get_conn_str(server, database)
        conn = pyodbc.connect(conn_str, timeout=8)
        try:
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.fetchone()
        finally:
            conn.close()

    def get_source_connection(self):
        if not self.active_source_key or self.active_source_key not in self.stores:
            raise ValueError("No active source store configured.")
        store = self.stores[self.active_source_key]
        conn_str = self._get_conn_str(store["server"], store["database"])
        return pyodbc.connect(conn_str, timeout=8)

    def get_dest_connection(self):
        if not self.active_dest_key or self.active_dest_key not in self.stores:
            raise ValueError("No active destination store configured.")
        store = self.stores[self.active_dest_key]
        conn_str = self._get_conn_str(store["server"], store["database"])
        return pyodbc.connect(conn_str, timeout=8)
        
    def get_history_connection(self):
        """History follows the active destination store so Manage Stores IP edits apply immediately."""
        if self.active_dest_key and self.active_dest_key in self.stores:
            store = self.stores[self.active_dest_key]
            conn_str = self._get_conn_str(store["server"], store["database"])
            return pyodbc.connect(conn_str, timeout=8)

        history_svr = self.db_cfg.get("history_server")
        history_db = self.db_cfg.get("history_database")
        if history_svr and history_db:
            conn_str = self._get_conn_str(history_svr, history_db)
            return pyodbc.connect(conn_str, timeout=8)

        raise ValueError("No active destination store configured for history.")

    def ensure_transfer_tables(self, raise_on_error: bool = False):
        """Create TransferHeader/TransferDetail on the history DB if they are missing.

        Safe to call on any machine — uses whatever history/destination DB is in config.ini.
        """
        try:
            with self.get_history_connection() as conn:
                conn.autocommit = True
                cursor = conn.cursor()
                cursor.execute(TRANSFER_TABLES_SQL)
                # Confirm tables are actually present
                cursor.execute(
                    "SELECT COUNT(*) FROM sys.tables WHERE name IN ('TransferHeader','TransferDetail') "
                    "AND schema_id = SCHEMA_ID('dbo')"
                )
                count = cursor.fetchone()[0]
                if count < 2:
                    raise RuntimeError(
                        "TransferHeader/TransferDetail could not be created. "
                        "Check that the SQL login has CREATE TABLE permission on the history database."
                    )
            logging.info("Transfer history tables verified (TransferHeader / TransferDetail).")
        except Exception as e:
            logging.error(f"Could not ensure transfer tables exist: {e}")
            if raise_on_error:
                raise RuntimeError(
                    f"Transfer history tables are not set up and could not be created automatically.\n\n{e}"
                ) from e

    def get_server_info(self) -> dict:
        """Returns the server addresses for display."""
        src_store = self.stores.get(self.active_source_key) if self.active_source_key else None
        dest_store = self.stores.get(self.active_dest_key) if self.active_dest_key else None
        
        src_host = src_store["server"].split('\\')[0] if src_store else "None"
        dest_host = dest_store["server"].split('\\')[0] if dest_store else "None"
        src_name = src_store["name"] if src_store else "No Source Store"
        dest_name = dest_store["name"] if dest_store else "No Destination Store"
        
        return {
            "source": f"{src_name} ({src_host})",
            "destination": f"{dest_name} ({dest_host})"
        }

    def sync_database_section(self):
        """Keep [DATABASE] source/destination/history in sync with active store selections."""
        if "DATABASE" not in self.config:
            self.config.add_section("DATABASE")

        if self.active_source_key and self.active_source_key in self.stores:
            src = self.stores[self.active_source_key]
            self.config["DATABASE"]["source_server"] = src["server"]
            self.config["DATABASE"]["source_database"] = src["database"]

        if self.active_dest_key and self.active_dest_key in self.stores:
            dest = self.stores[self.active_dest_key]
            self.config["DATABASE"]["destination_server"] = dest["server"]
            self.config["DATABASE"]["destination_database"] = dest["database"]
            self.config["DATABASE"]["history_server"] = dest["server"]
            self.config["DATABASE"]["history_database"] = dest["database"]

        # Refresh in-memory view used by connection builders
        self.db_cfg = self.config["DATABASE"]

    def save_stores(self):
        """Saves current stores dictionary back to the bound config.ini."""
        if "STORES" not in self.config:
            self.config.add_section("STORES")
        else:
            self.config.remove_section("STORES")
            self.config.add_section("STORES")

        for key, store in self.stores.items():
            self.config["STORES"][key] = (
                f"{store['name']} | {store['server']} | {store['database']}"
            )

        self.sync_database_section()

        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as configfile:
            self.config.write(configfile)
        logging.info(f"Store configuration saved to {self.config_path}")

    def reload_from_disk(self):
        """Re-read the bound config.ini (useful after external edits)."""
        self.config = configparser.ConfigParser(interpolation=None)
        self.config.optionxform = str
        self._load_config_file()
        self._parse_stores()
        self._select_active_stores_from_config()
        logging.info(f"Reloaded configuration from {self.config_path}")

    def add_store(self, name: str, server: str, database: str) -> str:
        """Adds a new store configuration and saves it."""
        i = 1
        while f"store{i}" in self.stores:
            i += 1
        key = f"store{i}"
        self.stores[key] = {
            "name": name,
            "server": server,
            "database": database
        }

        # If we only had 0 or 1 store, re-initialize active keys
        if len(self.stores) == 1:
            self.active_source_key = key
            self.active_dest_key = key
        elif len(self.stores) == 2 and self.active_source_key == self.active_dest_key:
            self.active_dest_key = key

        self.save_stores()
        return key

    def update_store(self, key: str, name: str, server: str, database: str):
        """Updates an existing store configuration and saves it."""
        if key in self.stores:
            self.stores[key] = {
                "name": name,
                "server": server,
                "database": database
            }
            self.save_stores()

    def delete_store(self, key: str):
        """Deletes a store configuration and saves the changes."""
        if key in self.stores:
            self.stores.pop(key)
            self.save_stores()

            # Reassign active keys if needed
            store_keys = list(self.stores.keys())
            if store_keys:
                if self.active_source_key == key or self.active_source_key not in self.stores:
                    self.active_source_key = store_keys[0]
                if self.active_dest_key == key or self.active_dest_key not in self.stores:
                    self.active_dest_key = store_keys[1] if len(store_keys) > 1 else store_keys[0]
            else:
                self.active_source_key = None
                self.active_dest_key = None
