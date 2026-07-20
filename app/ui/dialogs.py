from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QLabel, QTableWidget, QTableWidgetItem,
    QHeaderView, QDialogButtonBox, QHBoxLayout,
)
from PySide6.QtCore import Qt
from .styles import configure_table


class TransferDetailsDialog(QDialog):
    def __init__(self, transfer_id, details, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Transfer {transfer_id} — Details")
        self.resize(900, 460)
        self.setMinimumSize(700, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel(f"Transfer Details  ·  ID {transfer_id}")
        title.setObjectName("PageTitle")
        count = QLabel(f"{len(details)} line item{'s' if len(details) != 1 else ''}")
        count.setObjectName("MutedLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(count)
        layout.addLayout(header)

        self.table = QTableWidget()
        self.table.setColumnCount(7)
        self.table.setHorizontalHeaderLabels([
            "Item Num", "Item Name", "Qty", "Cost",
            "Source Change", "Destination Change", "Line Value",
        ])
        configure_table(self.table)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)

        total_value = 0.0
        for i, d in enumerate(details):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(str(d.item_num)))
            self.table.setItem(i, 1, QTableWidgetItem(str(d.item_name)))
            qty = QTableWidgetItem(f"{d.quantity:g}")
            qty.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cost = QTableWidgetItem(f"${d.cost:,.2f}")
            cost.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            line = d.quantity * d.cost
            total_value += line
            value = QTableWidgetItem(f"${line:,.2f}")
            value.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(i, 2, qty)
            self.table.setItem(i, 3, cost)
            self.table.setItem(
                i, 4, QTableWidgetItem(f"{d.source_stock_before:g} → {d.source_stock_after:g}")
            )
            self.table.setItem(
                i, 5, QTableWidgetItem(f"{d.dest_stock_before:g} → {d.dest_stock_after:g}")
            )
            self.table.setItem(i, 6, value)

        layout.addWidget(self.table, 1)

        footer = QHBoxLayout()
        total_lbl = QLabel(f"Total Value: ${total_value:,.2f}")
        total_lbl.setObjectName("CartSummary")
        footer.addWidget(total_lbl)
        footer.addStretch()
        buttons = QDialogButtonBox(QDialogButtonBox.Ok)
        buttons.accepted.connect(self.accept)
        footer.addWidget(buttons)
        layout.addLayout(footer)
