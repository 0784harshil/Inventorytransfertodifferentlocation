from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView, QDialogButtonBox
from PySide6.QtCore import Qt

class TransferDetailsDialog(QDialog):
    def __init__(self, transfer_id, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Transfer Details - ID: {transfer_id}")
        self.resize(800, 400)
        
        layout = QVBoxLayout(self)
        
        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Item Num", "Item Name", "Qty", "Cost", 
            "Src Change", "Dest Change", "Total Value"
        ])
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        for i, d in enumerate(details):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(str(d.item_num)))
            self.table.setItem(i, 1, QTableWidgetItem(str(d.item_name)))
            self.table.setItem(i, 2, QTableWidgetItem(str(d.quantity)))
            self.table.setItem(i, 3, QTableWidgetItem(f"${d.cost:.2f}"))
            self.table.setItem(i, 4, QTableWidgetItem(f"{d.source_stock_before} -> {d.source_stock_after}"))
            self.table.setItem(i, 5, QTableWidgetItem(f"{d.dest_stock_before} -> {d.dest_stock_after}"))
            self.table.setItem(i, 6, QTableWidgetItem(f"${(d.quantity * d.cost):.2f}"))

        layout.addWidget(self.table)
        
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
