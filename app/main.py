import sys
import os
import logging
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication
from datetime import datetime

# Adjust path to allow absolute imports
current_dir = Path(__file__).resolve().parent
if str(current_dir.parent) not in sys.path:
    sys.path.append(str(current_dir.parent))

from app.db import DatabaseManager
from app.services.inventory_service import InventoryService
from app.services.transfer_service import TransferService
from app.ui.main_window import MainWindow
from app.ui.history_window import HistoryWindow

def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"app_{today}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    parser = argparse.ArgumentParser(description="Inventory Transfer Application")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to config file")
    args = parser.parse_args()

    # Determine config path correctly for both dev and compiled (frozen) mode
    if os.path.isabs(args.config):
        config_path = Path(args.config)
    elif getattr(sys, 'frozen', False):
        # Running as a compiled .exe
        exe_dir = Path(sys.executable).parent
        config_path = exe_dir / args.config
    else:
        # Running as source script
        config_path = current_dir / args.config

    log_dir = current_dir / "logs"
    if getattr(sys, 'frozen', False):
        log_dir = Path(sys.executable).parent / "logs"
        
    setup_logging(log_dir)
    
    logging.info(f"Starting Inventory Transfer Application with config: {config_path}")
    
    if not config_path.exists():
        logging.error(f"Config file not found: {config_path}")
        print(f"ERROR: Config file not found: {config_path}")
        sys.exit(1)

    try:
        db_manager = DatabaseManager(config_path)
        inv_service = InventoryService(db_manager)
        trans_service = TransferService(db_manager)
        
        # Get Store Name from config
        store_name = db_manager.config.get("APP", "store_name", fallback="Inventory Transfer Pro")
        
        app = QApplication(sys.argv)
        app.setStyle("Fusion") # Consistent look across Windows versions
        
        main_win = MainWindow(inv_service, trans_service)
        main_win.setWindowTitle(f"{store_name} - Inventory Transfer")
        
        history_win = HistoryWindow(trans_service)
        history_win.setWindowTitle(f"{store_name} - Transfer History")
        
        # Connect History Button in Main Window to Show History Window
        main_win.btn_history.clicked.connect(history_win.show)
        
        main_win.show()
        sys.exit(app.exec())
        
    except Exception as e:
        logging.critical(f"Application crashed: {e}", exc_info=True)
        print(f"FATAL ERROR: {e}")

if __name__ == "__main__":
    main()
