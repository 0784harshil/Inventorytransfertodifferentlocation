from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, 
    QTableWidgetItem, QLineEdit, QPushButton, QLabel, QHeaderView,
    QMessageBox, QSplitter, QFrame, QGroupBox
)
from PySide6.QtCore import Qt, Signal
import logging

from ..models.transfer_models import CartItem
from .dialogs import TransferDetailsDialog

class MainWindow(QMainWindow):
    def __init__(self, inventory_service, transfer_service):
        super().__init__()
        self.inventory_service = inventory_service
        self.transfer_service = transfer_service
        self.cart = {} # item_num -> CartItem

        self.setWindowTitle("Inventory Transfer Pro - Production Edition")
        self.resize(1200, 800)
        
        # Main Layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        # Top Bar: Search & Actions
        top_bar = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("Search by Item Number or Name...")
        self.search_input.returnPressed.connect(self.load_inventory)
        
        self.btn_search = QPushButton("Search")
        self.btn_search.clicked.connect(self.load_inventory)
        
        self.btn_history = QPushButton("View History")
        # To be connected in main.py
        
        top_bar.addWidget(QLabel("Find Items:"))
        top_bar.addWidget(self.search_input)
        top_bar.addWidget(self.btn_search)
        top_bar.addStretch()
        top_bar.addWidget(self.btn_history)
        main_layout.addLayout(top_bar)

        # Splitter for Inventory and Cart
        splitter = QSplitter(Qt.Horizontal)
        
        # --- Left Side: Source Inventory ---
        left_panel = QGroupBox("Available Inventory (Source)")
        left_layout = QVBoxLayout(left_panel)
        
        self.inventory_table = QTableWidget()
        self.inventory_table.setColumnCount(4)
        self.inventory_table.setHorizontalHeaderLabels(["Item Num", "Item Name", "Cost", "Stock"])
        self.inventory_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.inventory_table.setSelectionBehavior(QTableWidget.SelectRows)
        self.inventory_table.doubleClicked.connect(self.add_selected_to_cart)
        
        left_layout.addWidget(self.inventory_table)
        
        self.btn_add_to_cart = QPushButton("Add to Transfer Cart >>")
        self.btn_add_to_cart.setStyleSheet("background-color: #2ecc71; color: white; font-weight: bold; padding: 10px;")
        self.btn_add_to_cart.clicked.connect(self.add_selected_to_cart)
        left_layout.addWidget(self.btn_add_to_cart)
        
        # --- Right Side: Transfer Cart ---
        right_panel = QGroupBox("Transfer Cart (Destination)")
        right_layout = QVBoxLayout(right_panel)
        
        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(["Item Num", "Item Name", "Qty to Transfer", "Action"])
        self.cart_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        
        right_layout.addWidget(self.cart_table)
        
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.clicked.connect(self.remove_from_cart)
        right_layout.addWidget(self.btn_remove)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        main_layout.addWidget(splitter)

        # Bottom Bar: Summary & Confirm
        bottom_bar = QFrame()
        bottom_bar.setFrameShape(QFrame.StyledPanel)
        bottom_layout = QHBoxLayout(bottom_bar)
        
        self.lbl_status = QLabel("Ready")
        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional transfer notes...")
        
        self.btn_transfer = QPushButton("CONFIRM TRANSFER")
        self.btn_transfer.setStyleSheet("background-color: #e74c3c; color: white; font-weight: bold; font-size: 16px; padding: 15px;")
        self.btn_transfer.clicked.connect(self.perform_transfer)
        
        bottom_layout.addWidget(self.lbl_status)
        bottom_layout.addStretch()
        bottom_layout.addWidget(QLabel("Notes:"))
        bottom_layout.addWidget(self.notes_input)
        bottom_layout.addWidget(self.btn_transfer)
        main_layout.addWidget(bottom_bar)

        # Initial Load
        self.load_inventory()

    def load_inventory(self):
        self.lbl_status.setText("Loading inventory...")
        search_text = self.search_input.text()
        try:
            items = self.inventory_service.search_inventory(search_text)
            self.inventory_table.setRowCount(0)
            for i, item in enumerate(items):
                self.inventory_table.insertRow(i)
                self.inventory_table.setItem(i, 0, QTableWidgetItem(item.item_num))
                self.inventory_table.setItem(i, 1, QTableWidgetItem(item.item_name))
                self.inventory_table.setItem(i, 2, QTableWidgetItem(f"${item.cost:.2f}"))
                self.inventory_table.setItem(i, 3, QTableWidgetItem(str(item.in_stock)))
            self.lbl_status.setText(f"Found {len(items)} items")
        except Exception as e:
            QMessageBox.critical(self, "DB Error", f"Could not load inventory: {e}")

    def add_selected_to_cart(self):
        selected_rows = self.inventory_table.selectionModel().selectedRows()
        if not selected_rows:
            return

        for row_idx in selected_rows:
            i = row_idx.row()
            item_num = self.inventory_table.item(i, 0).text()
            item_name = self.inventory_table.item(i, 1).text()
            cost = float(self.inventory_table.item(i, 2).text().replace("$", ""))
            stock = float(self.inventory_table.item(i, 3).text())

            if item_num in self.cart:
                continue

            self.cart[item_num] = CartItem(
                item_num=item_num,
                item_name=item_name,
                cost=cost,
                source_stock=stock,
                transfer_qty=1.0
            )
        self.refresh_cart_table()

    def refresh_cart_table(self):
        self.cart_table.setRowCount(0)
        for i, (item_num, item) in enumerate(self.cart.items()):
            self.cart_table.insertRow(i)
            self.cart_table.setItem(i, 0, QTableWidgetItem(item_num))
            self.cart_table.setItem(i, 1, QTableWidgetItem(item.item_name))
            
            qty_item = QTableWidgetItem(str(item.transfer_qty))
            qty_item.setFlags(qty_item.flags() | Qt.ItemIsEditable)
            self.cart_table.setItem(i, 2, qty_item)
            
            remove_btn = QPushButton("X")
            remove_btn.clicked.connect(lambda checked=False, inum=item_num: self.remove_from_cart(inum))
            self.cart_table.setCellWidget(i, 3, remove_btn)

    def remove_from_cart(self, item_num=None):
        if item_num:
            self.cart.pop(item_num, None)
        else:
            # Remove selected row
            curr = self.cart_table.currentRow()
            if curr >= 0:
                inum = self.cart_table.item(curr, 0).text()
                self.cart.pop(inum, None)
        self.refresh_cart_table()

    def perform_transfer(self):
        if not self.cart:
            QMessageBox.warning(self, "Cart Empty", "Please add items to transfer first.")
            return

        # Update quantities from table
        for r in range(self.cart_table.rowCount()):
            inum = self.cart_table.item(r, 0).text()
            try:
                qty = float(self.cart_table.item(r, 2).text())
                if qty <= 0:
                    raise ValueError("Quantity must be positive.")
                self.cart[inum].transfer_qty = qty
            except ValueError as e:
                QMessageBox.critical(self, "Invalid Quantity", str(e))
                return

        reply = QMessageBox.question(
            self, "Confirm Transfer", 
            f"Are you sure you want to transfer {len(self.cart)} items?",
            QMessageBox.Yes | QMessageBox.No
        )
        
        if reply == QMessageBox.Yes:
            self.lbl_status.setText("Executing transfer transaction...")
            try:
                notes = self.notes_input.text()
                tid = self.transfer_service.execute_transfer(
                    source_loc="Source DB", 
                    dest_loc="Dest DB", 
                    cart_items=list(self.cart.values()),
                    notes=notes
                )
                QMessageBox.information(self, "Success", f"Transfer Successful! ID: {tid}")
                self.cart.clear()
                self.refresh_cart_table()
                self.load_inventory()
                self.notes_input.clear()
            except Exception as e:
                QMessageBox.critical(self, "Transfer Failed", f"Error during transaction: {e}")
                self.lbl_status.setText("Transfer failed.")
