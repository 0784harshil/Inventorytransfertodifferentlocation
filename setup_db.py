import pyodbc
import configparser
import argparse
import os
import sys
from pathlib import Path

# Embedded SQL script for zero-dependency execution
SQL_SCRIPT = """
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

def setup_db():
    parser = argparse.ArgumentParser(description="Inventory Transfer DB Setup Utility")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to config file")
    args = parser.parse_args()

    # Determine config path correctly for both dev and compiled (frozen) mode
    if os.path.isabs(args.config):
        config_path = Path(args.config)
    elif getattr(sys, 'frozen', False):
        exe_dir = Path(sys.executable).parent
        config_path = exe_dir / args.config
    else:
        config_path = Path(args.config)

    if not config_path.exists():
        print(f"ERROR: Config file not found at: {config_path.absolute()}")
        input("\nPress ENTER to exit...")
        return

    config = configparser.ConfigParser()
    config.read(config_path)
    
    if "DATABASE" not in config:
        print(f"ERROR: [DATABASE] section missing in {config_path}")
        input("\nPress ENTER to exit...")
        return

    db_cfg = config["DATABASE"]
    
    # We use the history settings to initialize the audit tables
    server = db_cfg.get("history_server", db_cfg["destination_server"])
    database = db_cfg.get("history_database", db_cfg["destination_database"])
    driver = db_cfg["driver"]
    auth_mode = db_cfg.get("auth_mode", "windows").lower()
    
    if auth_mode == "windows":
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};Trusted_Connection=yes;"
    else:
        user = db_cfg["username"]
        pwd = db_cfg["password"]
        conn_str = f"DRIVER={{{driver}}};SERVER={server};DATABASE={database};UID={user};PWD={pwd};"
    
    print(f"--- DATABASE INITIALIZATION ---")
    print(f"Config: {config_path.name}")
    print(f"Server: {server}")
    print(f"Target: {database}")
    print(f"--------------------------------")
    
    try:
        with pyodbc.connect(conn_str, autocommit=True) as conn:
            cursor = conn.cursor()
            # Split by GO and execute each batch (if any)
            batches = SQL_SCRIPT.split("GO")
            for batch in batches:
                if batch.strip():
                    cursor.execute(batch)
            print("\nSUCCESS: Database setup complete.")
    except Exception as e:
        print(f"\nFAILED: Database setup error: {e}")

    print("\nInitialization finished.")
    input("Press ENTER to exit...")

if __name__ == "__main__":
    setup_db()
