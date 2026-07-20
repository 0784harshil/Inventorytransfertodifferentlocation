from PySide6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QTableWidget,
    QTableWidgetItem, QLineEdit, QPushButton, QLabel, QHeaderView,
    QMessageBox, QSplitter, QFrame, QGroupBox, QComboBox, QApplication,
    QAbstractItemView, QSizePolicy, QSpinBox,
)
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut, QGuiApplication
import logging

from ..models.transfer_models import CartItem, TransferRecommendation
from .manage_stores_dialog import ManageStoresDialog
from .styles import configure_table


class MainWindow(QMainWindow):
    def __init__(self, inventory_service, transfer_service):
        super().__init__()
        self.inventory_service = inventory_service
        self.transfer_service = transfer_service
        self.db = inventory_service.db
        self.cart = {}  # item_num -> CartItem
        self._remembered_qty = {}  # item_num -> last qty (survives remove/re-add)
        self._syncing_cart = False

        self.setWindowTitle("Inventory Transfer Pro")
        self.resize(1280, 840)
        self.setMinimumSize(960, 640)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        root = QVBoxLayout(central_widget)
        root.setContentsMargins(16, 14, 16, 12)
        root.setSpacing(12)

        # --- Header ---
        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        self.lbl_title = QLabel("Inventory Transfer")
        self.lbl_title.setObjectName("PageTitle")
        self.lbl_subtitle = QLabel(
            "Search items, build a cart, and move stock between stores in one transaction."
        )
        self.lbl_subtitle.setObjectName("PageSubtitle")
        title_block.addWidget(self.lbl_title)
        title_block.addWidget(self.lbl_subtitle)
        header.addLayout(title_block, 1)

        self.btn_dashboard = QPushButton("Dashboard")
        self.btn_dashboard.setObjectName("SecondaryButton")
        self.btn_dashboard.setToolTip("Open stock insights and recommendations")

        self.btn_history = QPushButton("History")
        self.btn_history.setToolTip("View transfer audit trail and exports")

        self.btn_manage_stores = QPushButton("Stores")
        self.btn_manage_stores.setToolTip("Add, edit, or remove store connections")

        header.addWidget(self.btn_dashboard)
        header.addWidget(self.btn_history)
        header.addWidget(self.btn_manage_stores)
        root.addLayout(header)

        # --- Route card ---
        route_card = QFrame()
        route_card.setObjectName("RouteCard")
        route_layout = QHBoxLayout(route_card)
        route_layout.setContentsMargins(14, 12, 14, 12)
        route_layout.setSpacing(10)

        src_wrap = QVBoxLayout()
        src_wrap.setSpacing(4)
        src_lbl = QLabel("FROM  Source Store")
        src_lbl.setObjectName("MutedLabel")
        self.combo_source = QComboBox()
        self.combo_source.setMinimumWidth(260)
        self.combo_source.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        src_wrap.addWidget(src_lbl)
        src_wrap.addWidget(self.combo_source)

        self.btn_swap = QPushButton("⇄")
        self.btn_swap.setObjectName("SwapButton")
        self.btn_swap.setToolTip("Swap source and destination stores")
        self.btn_swap.setFixedWidth(52)
        self.btn_swap.setFixedHeight(36)
        self.btn_swap.setStyleSheet("font-size: 20px; font-weight: 700;")
        self.btn_swap.clicked.connect(self.swap_stores)

        dest_wrap = QVBoxLayout()
        dest_wrap.setSpacing(4)
        dest_lbl = QLabel("TO  Destination Store")
        dest_lbl.setObjectName("MutedLabel")
        self.combo_dest = QComboBox()
        self.combo_dest.setMinimumWidth(260)
        self.combo_dest.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        dest_wrap.addWidget(dest_lbl)
        dest_wrap.addWidget(self.combo_dest)

        route_layout.addLayout(src_wrap, 1)
        route_layout.addWidget(self.btn_swap, 0, Qt.AlignBottom)
        route_layout.addLayout(dest_wrap, 1)
        root.addWidget(route_card)

        for key, store in self.db.stores.items():
            display_name = f"{store['name']}  ·  {store['server'].split(chr(92))[0]}"
            self.combo_source.addItem(display_name, key)
            self.combo_dest.addItem(display_name, key)

        src_idx = self.combo_source.findData(self.db.active_source_key)
        if src_idx >= 0:
            self.combo_source.setCurrentIndex(src_idx)
        dest_idx = self.combo_dest.findData(self.db.active_dest_key)
        if dest_idx >= 0:
            self.combo_dest.setCurrentIndex(dest_idx)

        # --- Search toolbar ---
        search_card = QFrame()
        search_card.setObjectName("ToolbarCard")
        search_layout = QHBoxLayout(search_card)
        search_layout.setContentsMargins(12, 10, 12, 10)
        search_layout.setSpacing(8)

        search_hint = QLabel("Find")
        search_hint.setObjectName("MutedLabel")
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText(
            "Type keywords (e.g. blue shirt) — matches item number or name"
        )
        self.search_input.setClearButtonEnabled(True)
        self.search_input.returnPressed.connect(self.load_inventory)

        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self.load_inventory)
        self.search_input.textChanged.connect(self._on_search_text_changed)

        self.btn_search = QPushButton("Search")
        self.btn_search.setObjectName("PrimaryButton")
        self.btn_search.clicked.connect(self.load_inventory)

        self.btn_refresh_inv = QPushButton("Refresh")
        self.btn_refresh_inv.setToolTip("Reload inventory from the source store")
        self.btn_refresh_inv.clicked.connect(self.load_inventory)

        search_layout.addWidget(search_hint)
        search_layout.addWidget(self.search_input, 1)
        search_layout.addWidget(self.btn_search)
        search_layout.addWidget(self.btn_refresh_inv)
        root.addWidget(search_card)

        # --- Inventory + Cart ---
        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QGroupBox("Source Inventory")
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 18, 12, 12)
        left_layout.setSpacing(8)

        self.lbl_inv_hint = QLabel("Double-click a row or press Enter to add selected items.")
        self.lbl_inv_hint.setObjectName("MutedLabel")
        left_layout.addWidget(self.lbl_inv_hint)

        self.inventory_table = QTableWidget()
        self.inventory_table.setColumnCount(4)
        self.inventory_table.setHorizontalHeaderLabels(
            ["Item Num", "Item Name", "Cost", "Stock"]
        )
        configure_table(self.inventory_table)
        self.inventory_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.inventory_table.doubleClicked.connect(self.add_selected_to_cart)
        left_layout.addWidget(self.inventory_table)

        self.btn_add_to_cart = QPushButton("Add Selected to Cart")
        self.btn_add_to_cart.setObjectName("PrimaryButton")
        self.btn_add_to_cart.setToolTip("Add selected inventory rows (Enter)")
        self.btn_add_to_cart.clicked.connect(self.add_selected_to_cart)
        left_layout.addWidget(self.btn_add_to_cart)

        right_panel = QGroupBox("Transfer Cart")
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(12, 18, 12, 12)
        right_layout.setSpacing(8)

        cart_header = QHBoxLayout()
        self.lbl_cart_summary = QLabel("0 items  ·  qty 0")
        self.lbl_cart_summary.setObjectName("CartSummary")
        cart_header.addWidget(self.lbl_cart_summary)
        cart_header.addStretch()
        self.btn_clear_cart = QPushButton("Clear Cart")
        self.btn_clear_cart.setToolTip("Remove all items from the cart")
        self.btn_clear_cart.clicked.connect(self.clear_cart)
        cart_header.addWidget(self.btn_clear_cart)
        right_layout.addLayout(cart_header)

        self.lbl_cart_hint = QLabel(
            "Use the Qty arrows or type a number. Quantities are kept when you add or remove other items."
        )
        self.lbl_cart_hint.setObjectName("MutedLabel")
        self.lbl_cart_hint.setWordWrap(True)
        right_layout.addWidget(self.lbl_cart_hint)

        self.cart_table = QTableWidget()
        self.cart_table.setColumnCount(4)
        self.cart_table.setHorizontalHeaderLabels(
            ["Item Num", "Item Name", "Qty", ""]
        )
        configure_table(self.cart_table)
        # Qty uses spin boxes — keep table itself non-editable and unsorted for stable editing
        self.cart_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.cart_table.setSortingEnabled(False)
        self.cart_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.cart_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Fixed)
        self.cart_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Fixed)
        self.cart_table.setColumnWidth(2, 110)
        self.cart_table.setColumnWidth(3, 90)
        right_layout.addWidget(self.cart_table)

        cart_actions = QHBoxLayout()
        self.btn_remove = QPushButton("Remove Selected")
        self.btn_remove.setToolTip("Remove selected cart rows (Delete)")
        self.btn_remove.clicked.connect(lambda: self.remove_from_cart())
        cart_actions.addWidget(self.btn_remove)
        cart_actions.addStretch()
        right_layout.addLayout(cart_actions)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        root.addWidget(splitter, 1)

        # --- Footer ---
        footer = QFrame()
        footer.setObjectName("FooterCard")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(14, 10, 14, 10)
        footer_layout.setSpacing(10)

        self.lbl_status = QLabel("Ready")
        self.lbl_status.setObjectName("StatusLabel")
        self.lbl_status.setMinimumWidth(220)

        self.lbl_config = QLabel("")
        self.lbl_config.setObjectName("MutedLabel")
        self.lbl_config.setToolTip("Active configuration file used for store and database settings")

        self.notes_input = QLineEdit()
        self.notes_input.setPlaceholderText("Optional transfer notes…")
        self.notes_input.setClearButtonEnabled(True)

        self.btn_transfer = QPushButton("Confirm Transfer")
        self.btn_transfer.setObjectName("DangerButton")
        self.btn_transfer.setToolTip("Commit the cart as one transaction")
        self.btn_transfer.clicked.connect(self.perform_transfer)

        footer_layout.addWidget(self.lbl_status, 1)
        footer_layout.addWidget(self.lbl_config)
        notes_lbl = QLabel("Notes")
        notes_lbl.setObjectName("MutedLabel")
        footer_layout.addWidget(notes_lbl)
        footer_layout.addWidget(self.notes_input, 2)
        footer_layout.addWidget(self.btn_transfer)
        root.addWidget(footer)

        # Show which config.ini this session is bound to
        self.set_config_path_display(str(self.db.config_path))

        # Signals
        self.combo_source.currentIndexChanged.connect(self.on_source_store_changed)
        self.combo_dest.currentIndexChanged.connect(self.on_destination_store_changed)
        self.btn_manage_stores.clicked.connect(self.open_manage_stores)

        # Shortcuts
        QShortcut(QKeySequence(Qt.Key_Return), self.inventory_table, activated=self.add_selected_to_cart)
        QShortcut(QKeySequence(Qt.Key_Enter), self.inventory_table, activated=self.add_selected_to_cart)
        QShortcut(QKeySequence(Qt.Key_Delete), self.cart_table, activated=lambda: self.remove_from_cart())
        QShortcut(QKeySequence("Ctrl+F"), self, activated=self._focus_search)
        QShortcut(QKeySequence("F5"), self, activated=self.load_inventory)

        self._update_cart_summary()
        self.load_inventory()
        self.search_input.setFocus()

    def set_config_path_display(self, config_path: str):
        """Show the bound config.ini path in the footer."""
        path = str(config_path or "")
        short = path
        if len(short) > 64:
            short = "…" + short[-63:]
        self.lbl_config.setText(f"Config: {short}")
        self.lbl_config.setToolTip(f"Connected to configuration file:\n{path}")

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, "_did_maximize", False):
            self._did_maximize = True
            self.showMaximized()

    def _focus_search(self):
        self.search_input.setFocus()
        self.search_input.selectAll()

    def _on_search_text_changed(self, _text: str):
        self._search_timer.start()

    def _set_busy(self, busy: bool, message: str = ""):
        QApplication.setOverrideCursor(Qt.WaitCursor) if busy else QApplication.restoreOverrideCursor()
        self.btn_transfer.setEnabled(not busy)
        self.btn_add_to_cart.setEnabled(not busy)
        self.btn_search.setEnabled(not busy)
        if message:
            self.lbl_status.setText(message)

    def _numeric_item(self, value, fmt: str = None) -> QTableWidgetItem:
        item = QTableWidgetItem()
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if fmt:
            item.setText(fmt)
            try:
                item.setData(Qt.UserRole, float(str(value).replace(",", "")))
            except ValueError:
                pass
        else:
            item.setData(Qt.DisplayRole, value)
        return item

    def _update_cart_summary(self):
        count = len(self.cart)
        total_qty = sum(int(round(float(i.transfer_qty or 0))) for i in self.cart.values())
        total_value = sum(float(i.transfer_qty or 0) * float(i.cost or 0) for i in self.cart.values())
        self.lbl_cart_summary.setText(
            f"{count} item{'s' if count != 1 else ''}  ·  qty {total_qty}  ·  ~${total_value:,.2f}"
        )
        self.btn_clear_cart.setEnabled(count > 0)
        self.btn_transfer.setEnabled(count > 0)
        self.btn_remove.setEnabled(count > 0)

    def swap_stores(self):
        src = self.combo_source.currentIndex()
        dest = self.combo_dest.currentIndex()
        if src < 0 or dest < 0:
            return
        self.combo_source.blockSignals(True)
        self.combo_dest.blockSignals(True)
        self.combo_source.setCurrentIndex(dest)
        self.combo_dest.setCurrentIndex(src)
        self.combo_source.blockSignals(False)
        self.combo_dest.blockSignals(False)
        # Apply both changes intentionally
        self.on_source_store_changed(self.combo_source.currentIndex())
        self.on_destination_store_changed(self.combo_dest.currentIndex())
        self.lbl_status.setText("Source and destination stores swapped.")

    def clear_cart(self):
        if not self.cart:
            return
        reply = QMessageBox.question(
            self,
            "Clear Cart",
            f"Remove all {len(self.cart)} item(s) from the cart?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        self._sync_cart_quantities_from_table()
        for inum, item in self.cart.items():
            self._remembered_qty[inum] = item.transfer_qty
        self.cart.clear()
        self.refresh_cart_table()
        self.lbl_status.setText("Cart cleared.")

    def on_source_store_changed(self, index):
        key = self.combo_source.itemData(index)
        if key:
            self.db.active_source_key = key
            self.db.sync_database_section()
            try:
                self.db.save_stores()
            except Exception as e:
                logging.warning(f"Could not persist source store selection: {e}")
            logging.info(
                f"Switched Source Store to: {key} ({self.db.stores[key]['name']})"
            )
            self.load_inventory()

    def on_destination_store_changed(self, index):
        key = self.combo_dest.itemData(index)
        if key:
            self.db.active_dest_key = key
            self.db.sync_database_section()
            try:
                self.db.save_stores()
            except Exception as e:
                logging.warning(f"Could not persist destination store selection: {e}")
            logging.info(
                f"Switched Destination Store to: {key} ({self.db.stores[key]['name']})"
            )
            try:
                self.db.ensure_transfer_tables()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "History Tables",
                    f"Could not verify transfer history tables on the destination.\n\n{e}",
                )
            self._sync_cart_quantities_from_table()
            self.cart.clear()
            self.refresh_cart_table()
            self.lbl_status.setText(
                f"Destination changed to {self.db.stores[key]['name']}. Cart cleared."
            )

    def open_manage_stores(self):
        try:
            dlg = ManageStoresDialog(self.db, self)
            dlg.exec()
            # Apply store/IP changes immediately in the live UI
            self.refresh_store_comboboxes()
            try:
                self.db.ensure_transfer_tables()
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "History Tables",
                    "Store settings were saved, but transfer history tables could not be verified "
                    f"on the current destination.\n\n{e}",
                )
            self.load_inventory()
            self.lbl_status.setText("Store settings applied. Connections refreshed.")
        except Exception as e:
            logging.error(f"Manage stores failed: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Manage Stores Error", f"Could not open store manager.\n\n{e}"
            )

    def refresh_store_comboboxes(self):
        curr_src_key = self.db.active_source_key
        curr_dest_key = self.db.active_dest_key

        self.combo_source.blockSignals(True)
        self.combo_dest.blockSignals(True)

        self.combo_source.clear()
        self.combo_dest.clear()

        for key, store in self.db.stores.items():
            display_name = f"{store['name']}  ·  {store['server'].split(chr(92))[0]}"
            self.combo_source.addItem(display_name, key)
            self.combo_dest.addItem(display_name, key)

        if curr_src_key in self.db.stores:
            src_idx = self.combo_source.findData(curr_src_key)
            self.combo_source.setCurrentIndex(src_idx)
            self.db.active_source_key = curr_src_key
        else:
            self.combo_source.setCurrentIndex(0)
            if self.combo_source.count() > 0:
                self.db.active_source_key = self.combo_source.itemData(0)
            else:
                self.db.active_source_key = None

        if curr_dest_key in self.db.stores:
            dest_idx = self.combo_dest.findData(curr_dest_key)
            self.combo_dest.setCurrentIndex(dest_idx)
            self.db.active_dest_key = curr_dest_key
        else:
            dest_idx = 1 if self.combo_dest.count() > 1 else 0
            self.combo_dest.setCurrentIndex(dest_idx)
            if self.combo_dest.count() > 0:
                self.db.active_dest_key = self.combo_dest.itemData(dest_idx)
            else:
                self.db.active_dest_key = None

        if curr_dest_key != self.db.active_dest_key:
            self._sync_cart_quantities_from_table()
            self.cart.clear()
            self.refresh_cart_table()
            self.lbl_status.setText("Destination changed. Cart cleared.")

        self.combo_source.blockSignals(False)
        self.combo_dest.blockSignals(False)

        self.load_inventory()

    def load_inventory(self):
        self.lbl_status.setText("Loading inventory…")
        search_text = self.search_input.text().strip()
        try:
            was_sorting = self.inventory_table.isSortingEnabled()
            self.inventory_table.setSortingEnabled(False)
            items = self.inventory_service.search_inventory(search_text)
            self.inventory_table.setRowCount(0)
            for i, item in enumerate(items):
                self.inventory_table.insertRow(i)
                self.inventory_table.setItem(i, 0, QTableWidgetItem(item.item_num))
                self.inventory_table.setItem(i, 1, QTableWidgetItem(item.item_name))

                cost_item = QTableWidgetItem(f"${item.cost:,.2f}")
                cost_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                cost_item.setData(Qt.UserRole, float(item.cost))
                self.inventory_table.setItem(i, 2, cost_item)

                stock_item = QTableWidgetItem(f"{item.in_stock:g}")
                stock_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                stock_item.setData(Qt.UserRole, float(item.in_stock))
                if item.in_stock <= 0:
                    stock_item.setForeground(Qt.red)
                self.inventory_table.setItem(i, 3, stock_item)

            self.inventory_table.setSortingEnabled(was_sorting)

            if not items:
                self.lbl_status.setText(
                    "No items found. Try fewer or different keywords."
                    if search_text
                    else "No inventory rows returned from the source store."
                )
            elif search_text:
                self.lbl_status.setText(f"{len(items)} match{'es' if len(items) != 1 else ''} for “{search_text}”")
            else:
                self.lbl_status.setText(
                    f"Showing {len(items)} items — type keywords to narrow results"
                )
        except Exception as e:
            logging.error(f"Inventory load failed: {e}", exc_info=True)
            self.lbl_status.setText("Inventory load failed.")
            QMessageBox.critical(
                self,
                "Inventory Error",
                f"Could not load inventory from the source store.\n\n{e}",
            )

    @staticmethod
    def _as_int_qty(value) -> int:
        """Cart transfer quantities are whole units only."""
        try:
            qty = int(round(float(value)))
        except (TypeError, ValueError):
            return 1
        return max(1, qty)

    def _make_qty_spin(self, item_num: str, value) -> QSpinBox:
        """Create an integer qty editor that reliably allows increasing/decreasing."""
        spin = QSpinBox()
        spin.setMinimum(1)
        spin.setMaximum(1_000_000)
        spin.setSingleStep(1)
        spin.setAlignment(Qt.AlignRight)
        spin.setButtonSymbols(QSpinBox.UpDownArrows)
        # Keep cart in sync while typing so values don't snap back to 1
        spin.setKeyboardTracking(True)
        spin.setToolTip("Use arrows or type a whole-number quantity")
        spin.setProperty("item_num", item_num)
        spin.setValue(self._as_int_qty(value))
        spin.valueChanged.connect(
            lambda qty, inum=item_num: self._on_qty_spin_changed(inum, qty)
        )
        spin.editingFinished.connect(
            lambda inum=item_num, s=spin: self._on_qty_spin_changed(inum, s.value())
        )
        return spin

    def _on_qty_spin_changed(self, item_num: str, qty):
        if self._syncing_cart:
            return
        if item_num not in self.cart:
            return
        qty = self._as_int_qty(qty)
        self.cart[item_num].transfer_qty = qty
        self._remembered_qty[item_num] = qty
        self._update_cart_summary()

    def _sync_cart_quantities_from_table(self):
        """Persist qty spinbox values into the cart dict before any refresh."""
        for r in range(self.cart_table.rowCount()):
            num_item = self.cart_table.item(r, 0)
            if not num_item:
                continue
            inum = num_item.text()
            if inum not in self.cart:
                continue
            spin = self.cart_table.cellWidget(r, 2)
            if isinstance(spin, QSpinBox):
                # Commit any in-progress typed text before reading value()
                spin.interpretText()
                qty = self._as_int_qty(spin.value())
                self.cart[inum].transfer_qty = qty
                self._remembered_qty[inum] = qty

    def add_selected_to_cart(self):
        selected_rows = self.inventory_table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(
                self, "No Selection", "Select one or more inventory rows to add."
            )
            return

        self._sync_cart_quantities_from_table()
        added = 0
        kept = 0

        for row_idx in selected_rows:
            i = row_idx.row()
            try:
                item_num = self.inventory_table.item(i, 0).text()
                item_name = self.inventory_table.item(i, 1).text()
                cost_cell = self.inventory_table.item(i, 2)
                stock_cell = self.inventory_table.item(i, 3)
                cost = float(
                    cost_cell.data(Qt.UserRole)
                    if cost_cell.data(Qt.UserRole) is not None
                    else cost_cell.text().replace("$", "").replace(",", "")
                )
                stock = float(
                    stock_cell.data(Qt.UserRole)
                    if stock_cell.data(Qt.UserRole) is not None
                    else stock_cell.text().replace(",", "")
                )
            except (AttributeError, ValueError, TypeError) as e:
                QMessageBox.warning(
                    self, "Invalid Row", f"Could not read inventory row {i + 1}.\n\n{e}"
                )
                continue

            if item_num in self.cart:
                # Already in cart — keep quantity; do not rebuild the row (avoids reset)
                self.cart[item_num].source_stock = stock
                kept += 1
                continue

            qty = self._as_int_qty(self._remembered_qty.get(item_num, 1))

            self.cart[item_num] = CartItem(
                item_num=item_num,
                item_name=item_name,
                cost=cost,
                source_stock=stock,
                transfer_qty=qty,
            )
            self._remembered_qty[item_num] = qty
            added += 1

        # Only rebuild table when new rows were added; otherwise keep spinboxes intact
        if added:
            self.refresh_cart_table()
        else:
            self._update_cart_summary()

        if added or kept:
            parts = []
            if added:
                parts.append(f"added {added}")
            if kept:
                parts.append(f"kept quantity for {kept} already in cart")
            self.lbl_status.setText("Cart updated: " + ", ".join(parts) + ".")

    def refresh_cart_table(self):
        self._sync_cart_quantities_from_table()
        self._syncing_cart = True
        try:
            desired = list(self.cart.items())
            current_keys = []
            for r in range(self.cart_table.rowCount()):
                cell = self.cart_table.item(r, 0)
                current_keys.append(cell.text() if cell else None)

            desired_keys = [k for k, _ in desired]
            # Fast path: same items in same order — just push qty into existing spinboxes
            if current_keys == desired_keys and desired_keys:
                for r, (item_num, item) in enumerate(desired):
                    spin = self.cart_table.cellWidget(r, 2)
                    if isinstance(spin, QSpinBox):
                        want = self._as_int_qty(item.transfer_qty)
                        if spin.value() != want:
                            spin.blockSignals(True)
                            spin.setValue(want)
                            spin.blockSignals(False)
                    name_item = self.cart_table.item(r, 1)
                    if name_item and name_item.text() != item.item_name:
                        name_item.setText(item.item_name)
            else:
                self.cart_table.setRowCount(0)
                for i, (item_num, item) in enumerate(desired):
                    self.cart_table.insertRow(i)

                    num_item = QTableWidgetItem(item_num)
                    num_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    name_item = QTableWidgetItem(item.item_name)
                    name_item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    self.cart_table.setItem(i, 0, num_item)
                    self.cart_table.setItem(i, 1, name_item)

                    spin = self._make_qty_spin(item_num, item.transfer_qty)
                    self.cart_table.setCellWidget(i, 2, spin)

                    remove_btn = QPushButton("Remove")
                    remove_btn.setObjectName("GhostDanger")
                    remove_btn.setCursor(Qt.PointingHandCursor)
                    remove_btn.clicked.connect(
                        lambda checked=False, inum=item_num: self.remove_from_cart(inum)
                    )
                    self.cart_table.setCellWidget(i, 3, remove_btn)
        finally:
            self._syncing_cart = False
        self._update_cart_summary()

    def remove_from_cart(self, item_num=None):
        self._sync_cart_quantities_from_table()
        if item_num:
            if item_num in self.cart:
                self._remembered_qty[item_num] = self.cart[item_num].transfer_qty
            self.cart.pop(item_num, None)
        else:
            selected = self.cart_table.selectionModel().selectedRows()
            if not selected:
                curr = self.cart_table.currentRow()
                if curr >= 0:
                    selected = [self.cart_table.model().index(curr, 0)]
                else:
                    QMessageBox.information(
                        self,
                        "No Selection",
                        "Select a cart row to remove, or use Remove on that row.",
                    )
                    return
            for idx in selected:
                row = idx.row() if hasattr(idx, "row") else idx
                cell = self.cart_table.item(row, 0)
                if not cell:
                    continue
                inum = cell.text()
                if inum in self.cart:
                    self._remembered_qty[inum] = self.cart[inum].transfer_qty
                self.cart.pop(inum, None)
        self.refresh_cart_table()
        self.lbl_status.setText("Item removed from cart.")

    def perform_transfer(self):
        self._sync_cart_quantities_from_table()

        if not self.cart:
            QMessageBox.warning(
                self, "Cart Empty", "Please add items to transfer first."
            )
            return

        if self.db.active_source_key == self.db.active_dest_key:
            QMessageBox.warning(
                self,
                "Same Store Selected",
                "Source and destination stores must be different.",
            )
            return

        for r in range(self.cart_table.rowCount()):
            inum = self.cart_table.item(r, 0).text()
            try:
                spin = self.cart_table.cellWidget(r, 2)
                if isinstance(spin, QSpinBox):
                    spin.interpretText()
                    qty = self._as_int_qty(spin.value())
                else:
                    qty = self._as_int_qty(self.cart_table.item(r, 2).text().strip())
                # Negative / zero source stock is allowed — do not block on available qty
                self.cart[inum].transfer_qty = qty
                self._remembered_qty[inum] = qty
            except ValueError as e:
                QMessageBox.critical(self, "Invalid Quantity", str(e))
                return
            except Exception as e:
                QMessageBox.critical(
                    self, "Invalid Quantity", f"Could not read quantity for '{inum}'.\n\n{e}"
                )
                return

        src_name = self.db.stores[self.db.active_source_key]["name"]
        dest_name = self.db.stores[self.db.active_dest_key]["name"]
        total_qty = sum(self._as_int_qty(i.transfer_qty) for i in self.cart.values())
        negative_lines = [
            i.item_num
            for i in self.cart.values()
            if float(i.transfer_qty) > float(i.source_stock or 0)
        ]
        warn = ""
        if negative_lines:
            preview = ", ".join(negative_lines[:5])
            more = f" (+{len(negative_lines) - 5} more)" if len(negative_lines) > 5 else ""
            warn = (
                f"\n\nNote: {len(negative_lines)} item(s) will drive source stock negative "
                f"({preview}{more}). This is allowed."
            )

        reply = QMessageBox.question(
            self,
            "Confirm Transfer",
            f"Transfer {len(self.cart)} line(s) / qty {total_qty}\n\n"
            f"From:  {src_name}\n"
            f"To:      {dest_name}"
            f"{warn}\n\n"
            "This will update stock in both stores.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply != QMessageBox.Yes:
            return

        self._set_busy(True, "Executing transfer…")
        QGuiApplication.processEvents()
        try:
            notes = self.notes_input.text()
            tid = self.transfer_service.execute_transfer(
                source_loc=src_name,
                dest_loc=dest_name,
                cart_items=list(self.cart.values()),
                notes=notes,
            )
            QMessageBox.information(
                self, "Success", f"Transfer completed successfully.\n\nTransfer ID: {tid}"
            )
            for inum in list(self.cart.keys()):
                self._remembered_qty.pop(inum, None)
            self.cart.clear()
            self.refresh_cart_table()
            self.load_inventory()
            self.notes_input.clear()
            self.lbl_status.setText(f"Transfer {tid} completed.")
        except Exception as e:
            logging.error(f"Transfer failed: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Transfer Failed",
                "The transfer could not be completed. No partial changes should remain "
                "if rollback succeeded.\n\n"
                f"{e}",
            )
            self.lbl_status.setText("Transfer failed.")
        finally:
            while QApplication.overrideCursor() is not None:
                QApplication.restoreOverrideCursor()
            self.btn_add_to_cart.setEnabled(True)
            self.btn_search.setEnabled(True)
            self._update_cart_summary()

    def add_rec_to_cart(self, rec: TransferRecommendation):
        """Adds a recommendation to the current cart, preserving existing qty if present."""
        try:
            self._sync_cart_quantities_from_table()
            if rec.item_num in self.cart:
                self.cart[rec.item_num].source_stock = rec.src_stock
                self.refresh_cart_table()
                self.lbl_status.setText(
                    f"{rec.item_name} is already in the cart — quantity kept."
                )
                self.raise_()
                self.activateWindow()
                return

            qty = self._as_int_qty(
                self._remembered_qty.get(rec.item_num, rec.recommended_qty or 1)
            )

            self.cart[rec.item_num] = CartItem(
                item_num=rec.item_num,
                item_name=rec.item_name,
                cost=rec.cost,
                source_stock=rec.src_stock,
                transfer_qty=qty,
            )
            self._remembered_qty[rec.item_num] = qty
            self.refresh_cart_table()
            self.lbl_status.setText(f"Added {rec.item_name} from dashboard.")
            self.raise_()
            self.activateWindow()
        except Exception as e:
            logging.error(f"Error adding recommendation to cart: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Add to Cart Failed",
                f"Could not add '{getattr(rec, 'item_name', rec)}' to the cart.\n\n{e}",
            )
