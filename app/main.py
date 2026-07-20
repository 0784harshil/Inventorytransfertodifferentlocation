import sys
import os
import logging
import argparse
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QPalette, QColor
from datetime import datetime

# Adjust path to allow absolute imports
current_dir = Path(__file__).resolve().parent
if str(current_dir.parent) not in sys.path:
    sys.path.append(str(current_dir.parent))

from app.db import DatabaseManager
from app.services.inventory_service import InventoryService
from app.services.transfer_service import TransferService
from app.services.dashboard_service import DashboardService
from app.ui.main_window import MainWindow
from app.ui.history_window import HistoryWindow
from app.ui.dashboard_window import DashboardWindow
from app.ui.styles import app_stylesheet, COLORS
from app.config_loader import resolve_config_path, app_dir, describe_config_binding


def setup_logging(log_dir: Path):
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"app_{today}.log"
    
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout)
        ]
    )

def main():
    parser = argparse.ArgumentParser(description="Inventory Transfer Application")
    parser.add_argument("--config", type=str, default="config.ini", help="Path to config file")
    args = parser.parse_args()

    config_path = resolve_config_path(args.config)

    log_dir = app_dir() / "logs"
    setup_logging(log_dir)
    
    logging.info(f"Starting Inventory Transfer Application")
    logging.info(describe_config_binding(config_path))
    
    # Create QApplication early so we can show error dialogs even on startup failure
    app = QApplication(sys.argv)
    app.setStyle("Fusion")  # Consistent look across Windows versions
    app.setStyleSheet(app_stylesheet())

    # Dark, high-contrast selection for text fields, date edits, and tables
    palette = app.palette()
    palette.setColor(QPalette.Highlight, QColor(COLORS["selection"]))
    palette.setColor(QPalette.HighlightedText, QColor(COLORS["selection_text"]))
    palette.setColor(QPalette.Inactive, QPalette.Highlight, QColor(COLORS["primary_pressed"]))
    palette.setColor(QPalette.Inactive, QPalette.HighlightedText, QColor(COLORS["selection_text"]))
    app.setPalette(palette)

    if not config_path.exists():
        logging.error(f"Config file not found: {config_path}")
        QMessageBox.critical(
            None,
            "Configuration Missing",
            f"Could not find the configuration file:\n{config_path}\n\n"
            "Place config.ini next to the application executable (or in the app folder) and try again.",
        )
        sys.exit(1)

    try:
        db_manager = DatabaseManager(config_path)
        inv_service = InventoryService(db_manager)
        trans_service = TransferService(db_manager)
        dash_service = DashboardService(db_manager)

        store_name = db_manager.config.get(
            "APP", "store_name", fallback="Inventory Transfer Pro"
        )

        main_win = MainWindow(inv_service, trans_service)
        main_win.setWindowTitle(f"{store_name} - Inventory Transfer")
        main_win.set_config_path_display(str(config_path))

        history_win = HistoryWindow(trans_service)
        history_win.setWindowTitle(f"{store_name} - Transfer History")

        dash_win = DashboardWindow(dash_service)
        dash_win.setWindowTitle(f"{store_name} - Stock Dashboard")

        def show_history():
            try:
                history_win.load_history()
                history_win.showMaximized()
                history_win.raise_()
                history_win.activateWindow()
            except Exception as e:
                logging.error(f"Could not open history: {e}", exc_info=True)
                QMessageBox.critical(
                    main_win, "History Error", f"Could not open transfer history.\n\n{e}"
                )

        def return_from_history():
            history_win.hide()
            main_win.showMaximized()
            main_win.raise_()
            main_win.activateWindow()

        def show_dashboard():
            try:
                dash_win.refresh_all()
                dash_win.showMaximized()
                dash_win.raise_()
                dash_win.activateWindow()
            except Exception as e:
                logging.error(f"Could not open dashboard: {e}", exc_info=True)
                QMessageBox.critical(
                    main_win, "Dashboard Error", f"Could not open the stock dashboard.\n\n{e}"
                )

        def return_from_dashboard():
            dash_win.hide()
            main_win.showMaximized()
            main_win.raise_()
            main_win.activateWindow()

        # Prefer wired navigation so Back always returns to the main transfer screen
        history_win.btn_back.clicked.disconnect()
        history_win.btn_back.clicked.connect(return_from_history)
        dash_win.btn_back.clicked.disconnect()
        dash_win.btn_back.clicked.connect(return_from_dashboard)

        main_win.btn_history.clicked.connect(show_history)
        main_win.btn_dashboard.clicked.connect(show_dashboard)
        dash_win.add_to_cart_requested.connect(main_win.add_rec_to_cart)

        main_win.showMaximized()
        sys.exit(app.exec())

    except Exception as e:
        logging.critical(f"Application crashed: {e}", exc_info=True)
        QMessageBox.critical(
            None,
            "Application Error",
            "The application failed to start.\n\n"
            f"{e}\n\n"
            "Check the log file in the logs folder for details.",
        )
        sys.exit(1)

if __name__ == "__main__":
    main()
