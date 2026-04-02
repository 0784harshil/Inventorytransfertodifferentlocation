from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTableWidget, 
    QTableWidgetItem, QPushButton, QLabel, QHeaderView,
    QHBoxLayout, QFrame, QDateEdit, QFileDialog, QMessageBox
)
from PySide6.QtCore import Qt, QDate
from datetime import datetime
from .dialogs import TransferDetailsDialog

class HistoryWindow(QMainWindow):
    def __init__(self, transfer_service):
        super().__init__()
        self.transfer_service = transfer_service
        self.setWindowTitle("Transfer History & Audit Trail")
        self.resize(1100, 700)
        
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # --- Filter Bar ---
        filter_layout = QHBoxLayout()
        
        filter_layout.addWidget(QLabel("From:"))
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        filter_layout.addWidget(self.date_from)
        
        filter_layout.addWidget(QLabel("To:"))
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())
        filter_layout.addWidget(self.date_to)
        
        self.btn_filter = QPushButton("Apply Filter")
        self.btn_filter.setStyleSheet("background-color: #3498db; color: white; font-weight: bold;")
        self.btn_filter.clicked.connect(self.load_history)
        filter_layout.addWidget(self.btn_filter)
        
        filter_layout.addStretch()
        
        self.btn_export = QPushButton("Export Summary")
        self.btn_export.setStyleSheet("background-color: #27ae60; color: white; font-weight: bold;")
        self.btn_export.clicked.connect(self.export_csv)
        filter_layout.addWidget(self.btn_export)

        self.btn_export_detail = QPushButton("Export Detailed ")
        self.btn_export_detail.setStyleSheet("background-color: #f39c12; color: white; font-weight: bold;")
        self.btn_export_detail.clicked.connect(self.export_detail_csv)
        filter_layout.addWidget(self.btn_export_detail)
        
        layout.addLayout(filter_layout)
        
        # --- History Table ---
        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(["ID", "Date", "Source", "Destination", "Created By", "Total Cost"])
        self.history_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.history_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.history_table.doubleClicked.connect(self.view_details)
        
        layout.addWidget(self.history_table)
        
        # --- Footer Summary ---
        footer_layout = QHBoxLayout()
        self.lbl_grand_total = QLabel("Grand Total Cost: $0.00")
        self.lbl_grand_total.setStyleSheet("font-size: 16px; font-weight: bold; color: #2c3e50;")
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_grand_total)
        layout.addLayout(footer_layout)
        
        btn_bar = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh All")
        self.btn_refresh.clicked.connect(self.reset_filters)
        
        self.btn_view_details = QPushButton("View Selected Details")
        self.btn_view_details.clicked.connect(self.view_details)
        
        btn_bar.addWidget(self.btn_refresh)
        btn_bar.addWidget(self.btn_view_details)
        btn_bar.addStretch()
        layout.addLayout(btn_bar)
        
        self.load_history()

    def get_dates(self):
        start = datetime.combine(self.date_from.date().toPython(), datetime.min.time())
        end = datetime.combine(self.date_to.date().toPython(), datetime.max.time())
        return start, end

    def reset_filters(self):
        self.date_from.setDate(QDate.currentDate().addMonths(-1))
        self.date_to.setDate(QDate.currentDate())
        self.load_history()

    def load_history(self):
        try:
            start, end = self.get_dates()
            history = self.transfer_service.get_history(start, end)
            self.history_table.setRowCount(0)
            
            grand_total = 0.0
            for i, h in enumerate(history):
                self.history_table.insertRow(i)
                self.history_table.setItem(i, 0, QTableWidgetItem(str(h.transfer_id)))
                self.history_table.setItem(i, 1, QTableWidgetItem(h.transfer_date.strftime("%Y-%m-%d %H:%M")))
                self.history_table.setItem(i, 2, QTableWidgetItem(h.source_location))
                self.history_table.setItem(i, 3, QTableWidgetItem(h.destination_location))
                self.history_table.setItem(i, 4, QTableWidgetItem(h.created_by))
                
                cost_item = QTableWidgetItem(f"${h.total_cost:,.2f}")
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.history_table.setItem(i, 5, cost_item)
                
                grand_total += h.total_cost
            
            self.lbl_grand_total.setText(f"Grand Total Cost: ${grand_total:,.2f}")
            
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading history: {e}")

    def export_csv(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Summary Report", "", "CSV Files (*.csv)")
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_history_to_csv(file_path, start, end)
                QMessageBox.information(self, "Success", f"Summary report exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV: {e}")

    def export_detail_csv(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(self, "Save Detailed Item Report", "", "CSV Files (*.csv)")
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_detailed_history_to_csv(file_path, start, end)
                QMessageBox.information(self, "Success", f"Detailed item-level report exported successfully to:\n{file_path}")
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export Detailed CSV: {e}")

    def view_details(self):
        curr = self.history_table.currentRow()
        if curr < 0:
            return
            
        transfer_id = int(self.history_table.item(curr, 0).text())
        details = self.transfer_service.get_transfer_details(transfer_id)
        
        dialog = TransferDetailsDialog(transfer_id, details, self)
        dialog.exec()
