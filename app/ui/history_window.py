from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QTableWidget,
    QTableWidgetItem, QPushButton, QLabel, QHeaderView,
    QHBoxLayout, QFrame, QDateEdit, QFileDialog, QMessageBox,
    QAbstractItemView,
)
from PySide6.QtCore import Qt, QDate
from datetime import datetime
from .dialogs import TransferDetailsDialog
from .styles import configure_table


class HistoryWindow(QMainWindow):
    def __init__(self, transfer_service):
        super().__init__()
        self.transfer_service = transfer_service
        self.setWindowTitle("Transfer History")
        self.resize(1180, 760)
        self.setMinimumSize(900, 560)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Transfer History")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Audit trail of completed transfers with summary and detailed exports.")
        subtitle.setObjectName("PageSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block, 1)

        self.btn_back = QPushButton("←  Back to Transfer")
        self.btn_back.setObjectName("BackButton")
        self.btn_back.setToolTip("Return to the main transfer screen")
        self.btn_back.clicked.connect(self.go_back)
        header.addWidget(self.btn_back, 0, Qt.AlignTop)
        layout.addLayout(header)

        filter_card = QFrame()
        filter_card.setObjectName("ToolbarCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        filter_layout.setSpacing(8)

        from_lbl = QLabel("From")
        from_lbl.setObjectName("MutedLabel")
        self.date_from = QDateEdit()
        self.date_from.setCalendarPopup(True)
        self.date_from.setDate(QDate.currentDate().addMonths(-1))

        to_lbl = QLabel("To")
        to_lbl.setObjectName("MutedLabel")
        self.date_to = QDateEdit()
        self.date_to.setCalendarPopup(True)
        self.date_to.setDate(QDate.currentDate())

        self.btn_filter = QPushButton("Apply")
        self.btn_filter.setObjectName("PrimaryButton")
        self.btn_filter.clicked.connect(self.load_history)

        self.btn_refresh = QPushButton("Reset")
        self.btn_refresh.clicked.connect(self.reset_filters)

        filter_layout.addWidget(from_lbl)
        filter_layout.addWidget(self.date_from)
        filter_layout.addWidget(to_lbl)
        filter_layout.addWidget(self.date_to)
        filter_layout.addWidget(self.btn_filter)
        filter_layout.addWidget(self.btn_refresh)
        filter_layout.addStretch()
        layout.addWidget(filter_card)

        export_card = QFrame()
        export_card.setObjectName("ToolbarCard")
        export_layout = QHBoxLayout(export_card)
        export_layout.setContentsMargins(12, 10, 12, 10)
        export_layout.setSpacing(8)

        export_lbl = QLabel("Exports")
        export_lbl.setObjectName("MutedLabel")
        self.btn_export = QPushButton("Summary CSV")
        self.btn_export.clicked.connect(self.export_csv)
        self.btn_export_pdf = QPushButton("Summary PDF")
        self.btn_export_pdf.clicked.connect(self.export_pdf)
        self.btn_export_detail = QPushButton("Detailed CSV")
        self.btn_export_detail.clicked.connect(self.export_detail_csv)
        self.btn_export_detail_pdf = QPushButton("Detailed PDF")
        self.btn_export_detail_pdf.clicked.connect(self.export_detail_pdf)

        export_layout.addWidget(export_lbl)
        export_layout.addWidget(self.btn_export)
        export_layout.addWidget(self.btn_export_pdf)
        export_layout.addWidget(self.btn_export_detail)
        export_layout.addWidget(self.btn_export_detail_pdf)
        export_layout.addStretch()
        layout.addWidget(export_card)

        self.history_table = QTableWidget()
        self.history_table.setColumnCount(6)
        self.history_table.setHorizontalHeaderLabels(
            ["ID", "Date", "Source", "Destination", "Created By", "Total Cost"]
        )
        configure_table(self.history_table)
        self.history_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.history_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        self.history_table.doubleClicked.connect(self.view_details)
        layout.addWidget(self.history_table, 1)

        footer = QFrame()
        footer.setObjectName("FooterCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_count = QLabel("0 transfers")
        self.lbl_count.setObjectName("MutedLabel")
        self.lbl_grand_total = QLabel("Grand Total: $0.00")
        self.lbl_grand_total.setObjectName("CartSummary")

        self.btn_view_details = QPushButton("View Details")
        self.btn_view_details.setObjectName("SecondaryButton")
        self.btn_view_details.clicked.connect(self.view_details)

        footer_layout.addWidget(self.lbl_count)
        footer_layout.addStretch()
        footer_layout.addWidget(self.lbl_grand_total)
        footer_layout.addWidget(self.btn_view_details)
        layout.addWidget(footer)

        self.load_history()

    def go_back(self):
        """Close history and return focus to the main transfer window."""
        self.hide()
        parent = self.parent()
        if parent is not None:
            parent.raise_()
            parent.activateWindow()
        # Also try to find the main transfer window among top-levels
        from PySide6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            title = (w.windowTitle() or "").lower()
            if "inventory transfer" in title and w is not self and w.isVisible():
                w.raise_()
                w.activateWindow()
                break

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
            self.history_table.setSortingEnabled(False)
            self.history_table.setRowCount(0)

            grand_total = 0.0
            for i, h in enumerate(history):
                self.history_table.insertRow(i)
                self.history_table.setItem(i, 0, QTableWidgetItem(str(h.transfer_id)))
                self.history_table.setItem(
                    i, 1, QTableWidgetItem(h.transfer_date.strftime("%Y-%m-%d %H:%M"))
                )
                self.history_table.setItem(i, 2, QTableWidgetItem(h.source_location))
                self.history_table.setItem(i, 3, QTableWidgetItem(h.destination_location))
                self.history_table.setItem(i, 4, QTableWidgetItem(h.created_by))

                cost_item = QTableWidgetItem(f"${h.total_cost:,.2f}")
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.history_table.setItem(i, 5, cost_item)
                grand_total += h.total_cost

            self.history_table.setSortingEnabled(True)
            count = len(history)
            self.lbl_count.setText(f"{count} transfer{'s' if count != 1 else ''}")
            self.lbl_grand_total.setText(f"Grand Total: ${grand_total:,.2f}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Error loading history:\n\n{e}")

    def export_csv(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Summary Report (CSV)", "", "CSV Files (*.csv)"
            )
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_history_to_csv(file_path, start, end)
                QMessageBox.information(
                    self, "Export Complete", f"Summary CSV saved to:\n{file_path}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export CSV:\n\n{e}")

    def export_pdf(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Summary Report (PDF)", "", "PDF Files (*.pdf)"
            )
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_history_to_pdf(file_path, start, end)
                QMessageBox.information(
                    self, "Export Complete", f"Summary PDF saved to:\n{file_path}"
                )
        except Exception as e:
            QMessageBox.critical(self, "Export Error", f"Failed to export PDF:\n\n{e}")

    def export_detail_csv(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Detailed Item Report (CSV)", "", "CSV Files (*.csv)"
            )
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_detailed_history_to_csv(file_path, start, end)
                QMessageBox.information(
                    self, "Export Complete", f"Detailed CSV saved to:\n{file_path}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", f"Failed to export Detailed CSV:\n\n{e}"
            )

    def export_detail_pdf(self):
        try:
            file_path, _ = QFileDialog.getSaveFileName(
                self, "Save Detailed Item Report (PDF)", "", "PDF Files (*.pdf)"
            )
            if file_path:
                start, end = self.get_dates()
                self.transfer_service.export_detailed_history_to_pdf(file_path, start, end)
                QMessageBox.information(
                    self, "Export Complete", f"Detailed PDF saved to:\n{file_path}"
                )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", f"Failed to export Detailed PDF:\n\n{e}"
            )

    def view_details(self):
        curr = self.history_table.currentRow()
        if curr < 0:
            QMessageBox.information(self, "No Selection", "Select a transfer row first.")
            return

        try:
            transfer_id = int(self.history_table.item(curr, 0).text())
            details = self.transfer_service.get_transfer_details(transfer_id)
            if not details:
                QMessageBox.information(
                    self,
                    "No Details",
                    f"No line items were found for transfer {transfer_id}.",
                )
                return
            dialog = TransferDetailsDialog(transfer_id, details, self)
            dialog.exec()
        except Exception as e:
            QMessageBox.critical(
                self, "Details Error", f"Could not open transfer details.\n\n{e}"
            )
