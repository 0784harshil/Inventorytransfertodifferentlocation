from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QLineEdit, QPushButton, QLabel, QHeaderView, QTabWidget, QFrame,
    QComboBox, QMessageBox, QAbstractItemView, QDoubleSpinBox, QFormLayout,
)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor
import logging

from .styles import configure_table, status_color, COLORS
from ..recommendation_rules import RecommendationRules, DEFAULT_LOW_STOCK_AT, DEFAULT_SURPLUS_ABOVE, DEFAULT_TARGET_STOCK


class DashboardWindow(QWidget):
    add_to_cart_requested = Signal(object)

    def __init__(self, dashboard_service):
        super().__init__()
        self.service = dashboard_service
        self.recommendations = []
        self.pair_analysis = []
        self.server_info = {"source": "--", "destination": "--"}
        self.setWindowTitle("Stock Dashboard")
        self.resize(1180, 780)
        self.setMinimumSize(900, 600)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        header = QHBoxLayout()
        title_block = QVBoxLayout()
        title_block.setSpacing(2)
        title = QLabel("Stock Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Monitor stock health and push recommended transfers into the cart.")
        subtitle.setObjectName("PageSubtitle")
        title_block.addWidget(title)
        title_block.addWidget(subtitle)
        header.addLayout(title_block, 1)

        self.btn_back = QPushButton("←  Back to Transfer")
        self.btn_back.setObjectName("BackButton")
        self.btn_back.setToolTip("Return to the main transfer screen")
        self.btn_back.clicked.connect(self.go_back)
        header.addWidget(self.btn_back, 0, Qt.AlignTop)

        self.btn_refresh = QPushButton("Refresh")
        self.btn_refresh.setObjectName("PrimaryButton")
        self.btn_refresh.clicked.connect(self.refresh_all)
        header.addWidget(self.btn_refresh, 0, Qt.AlignTop)
        layout.addLayout(header)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(12)
        self.card_out = self._create_card("Out of Stock", "0", COLORS["danger"])
        self.card_low = self._create_card("Low Stock", "0", COLORS["warning"])
        self.card_over = self._create_card("Overstocked", "0", COLORS["info"])
        cards_layout.addWidget(self.card_out)
        cards_layout.addWidget(self.card_low)
        cards_layout.addWidget(self.card_over)
        layout.addLayout(cards_layout)

        filter_card = QFrame()
        filter_card.setObjectName("ToolbarCard")
        filter_layout = QHBoxLayout(filter_card)
        filter_layout.setContentsMargins(12, 10, 12, 10)
        find_lbl = QLabel("Find")
        find_lbl.setObjectName("MutedLabel")
        self.status_search = QLineEdit()
        self.status_search.setPlaceholderText("Keyword search across status and planner…")
        self.status_search.setClearButtonEnabled(True)
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(350)
        self._search_timer.timeout.connect(self.on_search_changed)
        self.status_search.textChanged.connect(lambda _: self._search_timer.start())

        self.status_filter = QComboBox()
        self.status_filter.addItems(["All Statuses", "Out of Stock", "Low Stock", "Overstocked"])
        self.status_filter.currentTextChanged.connect(self.load_status_data)

        filter_layout.addWidget(find_lbl)
        filter_layout.addWidget(self.status_search, 1)
        filter_layout.addWidget(QLabel("Status"))
        filter_layout.addWidget(self.status_filter)
        layout.addWidget(filter_card)

        layout.addWidget(self._build_rules_panel())

        self.tabs = QTabWidget()
        self.status_tab = QWidget()
        self._setup_status_tab()
        self.tabs.addTab(self.status_tab, "Stock Status")

        self.rec_tab = QWidget()
        self._setup_rec_tab()
        self.tabs.addTab(self.rec_tab, "Recommendations")

        self.compare_tab = QWidget()
        self._setup_compare_tab()
        self.tabs.addTab(self.compare_tab, "Transfer Planner")
        layout.addWidget(self.tabs, 1)

        self._load_rules_into_ui()
        self.refresh_all()

    def go_back(self):
        """Close dashboard and return focus to the main transfer window."""
        self.hide()
        from PySide6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            title = (w.windowTitle() or "").lower()
            if "inventory transfer" in title and w is not self and w.isVisible():
                w.raise_()
                w.activateWindow()
                break

    def _build_rules_panel(self) -> QFrame:
        """Editable recommendation rules; defaults apply until the user changes them."""
        card = QFrame()
        card.setObjectName("ToolbarCard")
        root = QVBoxLayout(card)
        root.setContentsMargins(12, 10, 12, 10)
        root.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Recommendation Rules")
        title.setStyleSheet("font-weight: 700;")
        self.lbl_rules_active = QLabel("")
        self.lbl_rules_active.setObjectName("MutedLabel")
        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.lbl_rules_active)
        root.addLayout(header)

        hint = QLabel(
            "Leave these at the defaults unless you need different thresholds. "
            f"Defaults: Dest ≤ {DEFAULT_LOW_STOCK_AT:g}, Source > {DEFAULT_SURPLUS_ABOVE:g}, "
            f"Target {DEFAULT_TARGET_STOCK:g}."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        root.addWidget(hint)

        form_row = QHBoxLayout()
        form_row.setSpacing(16)

        def _make_spin(default: float) -> QDoubleSpinBox:
            spin = QDoubleSpinBox()
            spin.setDecimals(2)
            spin.setRange(-1_000_000, 1_000_000)
            spin.setSingleStep(1)
            spin.setValue(default)
            spin.setMaximumWidth(110)
            return spin

        self.spin_low_stock = _make_spin(DEFAULT_LOW_STOCK_AT)
        self.spin_low_stock.setToolTip("Destination is considered low when stock is at or below this")
        self.spin_surplus = _make_spin(DEFAULT_SURPLUS_ABOVE)
        self.spin_surplus.setToolTip("Source has surplus when stock is above this")
        self.spin_target = _make_spin(DEFAULT_TARGET_STOCK)
        self.spin_target.setToolTip("Recommended qty aims to bring destination up to this level")

        for label, spin in (
            ("Low stock at (Dest ≤)", self.spin_low_stock),
            ("Surplus above (Source >)", self.spin_surplus),
            ("Target stock", self.spin_target),
        ):
            col = QVBoxLayout()
            col.setSpacing(2)
            lbl = QLabel(label)
            lbl.setObjectName("MutedLabel")
            col.addWidget(lbl)
            col.addWidget(spin)
            form_row.addLayout(col)

        form_row.addStretch()

        self.btn_apply_rules = QPushButton("Apply Rules")
        self.btn_apply_rules.setObjectName("PrimaryButton")
        self.btn_apply_rules.setToolTip("Apply these thresholds and refresh recommendations")
        self.btn_apply_rules.clicked.connect(self.apply_rules)

        self.btn_reset_rules = QPushButton("Reset Defaults")
        self.btn_reset_rules.setToolTip("Restore Dest ≤ 5, Source > 20, Target 10")
        self.btn_reset_rules.clicked.connect(self.reset_rules)

        form_row.addWidget(self.btn_apply_rules, 0, Qt.AlignBottom)
        form_row.addWidget(self.btn_reset_rules, 0, Qt.AlignBottom)
        root.addLayout(form_row)
        return card

    def _load_rules_into_ui(self):
        rules = self.service.get_rules()
        self.spin_low_stock.blockSignals(True)
        self.spin_surplus.blockSignals(True)
        self.spin_target.blockSignals(True)
        self.spin_low_stock.setValue(rules.low_stock_at)
        self.spin_surplus.setValue(rules.surplus_above)
        self.spin_target.setValue(rules.target_stock)
        self.spin_low_stock.blockSignals(False)
        self.spin_surplus.blockSignals(False)
        self.spin_target.blockSignals(False)
        self.lbl_rules_active.setText(f"Active: {rules.describe()}")
        self._update_rules_labels()

    def _rules_from_ui(self) -> RecommendationRules:
        return RecommendationRules(
            low_stock_at=float(self.spin_low_stock.value()),
            surplus_above=float(self.spin_surplus.value()),
            target_stock=float(self.spin_target.value()),
        )

    def _update_rules_labels(self):
        rules = self.service.get_rules()
        text = (
            f"Rules: destination ≤ {rules.low_stock_at:g}, "
            f"source > {rules.surplus_above:g}, "
            f"target level {rules.target_stock:g}."
        )
        if hasattr(self, "lbl_rec_rules"):
            self.lbl_rec_rules.setText(
                text + "  Select rows, then Add Selected — or double-click a row."
            )

    def apply_rules(self):
        try:
            rules = self._rules_from_ui()
            self.service.set_rules(rules, persist=True)
            self.lbl_rules_active.setText(f"Active: {rules.describe()}")
            self._update_rules_labels()
            self.refresh_all()
            QMessageBox.information(
                self,
                "Rules Applied",
                f"Recommendations now use:\n{rules.describe()}\n\n"
                "Saved to config.ini for next launch.",
            )
        except Exception as e:
            QMessageBox.warning(self, "Invalid Rules", str(e))

    def reset_rules(self):
        try:
            rules = self.service.reset_rules_to_defaults(persist=True)
            self._load_rules_into_ui()
            self.refresh_all()
            QMessageBox.information(
                self,
                "Defaults Restored",
                f"Back to default rules:\n{rules.describe()}",
            )
        except Exception as e:
            QMessageBox.critical(self, "Reset Failed", str(e))

    def _create_card(self, title, value, color):
        frame = QFrame()
        frame.setObjectName("StatCard")
        frame.setMinimumHeight(96)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)

        lbl_title = QLabel(title.upper())
        lbl_title.setAlignment(Qt.AlignLeft)
        lbl_title.setStyleSheet(
            f"color: {color}; font-weight: 700; font-size: 11px; letter-spacing: 0.6px; border: none;"
        )

        lbl_value = QLabel(value)
        lbl_value.setAlignment(Qt.AlignLeft)
        lbl_value.setStyleSheet(
            f"font-size: 28px; font-weight: 700; border: none; color: {COLORS['text']};"
        )

        layout.addWidget(lbl_title)
        layout.addWidget(lbl_value)
        layout.addStretch()
        frame.value_label = lbl_value
        return frame

    def _setup_status_tab(self):
        layout = QVBoxLayout(self.status_tab)
        layout.setContentsMargins(10, 12, 10, 10)
        self.status_table = QTableWidget()
        self.status_table.setColumnCount(5)
        self.status_table.setHorizontalHeaderLabels(
            ["Item Num", "Item Name", "Location", "Stock", "Status"]
        )
        configure_table(self.status_table)
        self.status_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        layout.addWidget(self.status_table)

    def _setup_rec_tab(self):
        layout = QVBoxLayout(self.rec_tab)
        layout.setContentsMargins(10, 12, 10, 10)
        self.lbl_rec_rules = QLabel(
            "Rules: destination ≤ 5, source > 20, target level 10.  "
            "Select one or more rows, then click Add Selected — or double-click a row."
        )
        self.lbl_rec_rules.setObjectName("MutedLabel")
        self.lbl_rec_rules.setWordWrap(True)
        layout.addWidget(self.lbl_rec_rules)

        self.rec_table = QTableWidget()
        self.rec_table.setColumnCount(6)
        self.rec_table.setHorizontalHeaderLabels([
            "Item Name", "From", "To", "Src Stock", "Dest Stock", "Recommended"
        ])
        configure_table(self.rec_table)
        self.rec_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.rec_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.rec_table.doubleClicked.connect(self._add_rec_row_from_index)
        layout.addWidget(self.rec_table)

        btn_row = QHBoxLayout()
        self.btn_add_selected_rec = QPushButton("Add Selected to Cart")
        self.btn_add_selected_rec.setObjectName("PrimaryButton")
        self.btn_add_selected_rec.setToolTip("Add only the highlighted recommendation rows")
        self.btn_add_selected_rec.clicked.connect(self.handle_add_selected_recommendations)

        self.btn_add_all_rec = QPushButton("Add All Recommended")
        self.btn_add_all_rec.setObjectName("SecondaryButton")
        self.btn_add_all_rec.setToolTip("Add every recommendation in this list")
        self.btn_add_all_rec.clicked.connect(self.handle_add_all_recommendations)

        btn_row.addWidget(self.btn_add_selected_rec)
        btn_row.addWidget(self.btn_add_all_rec)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        # Keep old attribute name for any external wiring
        self.btn_add_to_cart = self.btn_add_selected_rec

    def _setup_compare_tab(self):
        layout = QVBoxLayout(self.compare_tab)
        layout.setContentsMargins(10, 12, 10, 10)

        route_header = QFrame()
        route_header.setObjectName("RouteCard")
        rh_layout = QHBoxLayout(route_header)
        rh_layout.setContentsMargins(14, 10, 14, 10)

        self.lbl_src_ip = QLabel("FROM  Source: --")
        self.lbl_src_ip.setStyleSheet(f"font-weight: 700; color: {COLORS['text']};")
        arrow_lbl = QLabel("→")
        arrow_lbl.setObjectName("RouteArrow")
        self.lbl_dest_ip = QLabel("TO  Destination: --")
        self.lbl_dest_ip.setStyleSheet(f"font-weight: 700; color: {COLORS['text']};")

        rh_layout.addWidget(self.lbl_src_ip)
        rh_layout.addStretch()
        rh_layout.addWidget(arrow_lbl)
        rh_layout.addStretch()
        rh_layout.addWidget(self.lbl_dest_ip)
        layout.addWidget(route_header)

        hint = QLabel(
            "Select rows with a recommended qty, then Add Selected — or add all recommended moves."
        )
        hint.setObjectName("MutedLabel")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        self.compare_table = QTableWidget()
        self.compare_table.setColumnCount(5)
        configure_table(self.compare_table)
        self.compare_table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.compare_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.compare_table.doubleClicked.connect(self._add_compare_row_from_index)
        layout.addWidget(self.compare_table)

        btn_row = QHBoxLayout()
        self.btn_add_selected_pair = QPushButton("Add Selected to Cart")
        self.btn_add_selected_pair.setObjectName("PrimaryButton")
        self.btn_add_selected_pair.setToolTip("Add only the highlighted planner rows")
        self.btn_add_selected_pair.clicked.connect(self.handle_add_selected_pair_to_cart)

        self.btn_add_pair_suggestions = QPushButton("Add All Recommended Moves")
        self.btn_add_pair_suggestions.setObjectName("SecondaryButton")
        self.btn_add_pair_suggestions.clicked.connect(self.handle_add_pair_to_cart)

        btn_row.addWidget(self.btn_add_selected_pair)
        btn_row.addWidget(self.btn_add_pair_suggestions)
        btn_row.addStretch()
        layout.addLayout(btn_row)

    def on_search_changed(self):
        self.load_status_data()
        self.load_compare_data()

    def refresh_all(self):
        try:
            summary = self.service.get_summary()
            self.card_out.value_label.setText(str(summary.out_of_stock_count))
            self.card_low.value_label.setText(str(summary.low_stock_count))
            self.card_over.value_label.setText(str(summary.overstocked_count))

            self.server_info = self.service.get_server_ips()
            self.lbl_src_ip.setText(f"FROM  Source: {self.server_info['source']}")
            self.lbl_dest_ip.setText(f"TO  Destination: {self.server_info['destination']}")

            self.compare_table.setHorizontalHeaderLabels([
                "Item Name",
                f"Src ({self.server_info['source']})",
                f"Dest ({self.server_info['destination']})",
                "Recommended",
                "Status",
            ])

            self.load_status_data()
            self.load_rec_data()
            self.load_compare_data()
        except Exception as e:
            logging.error(f"Dashboard refresh failed: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Dashboard Error", f"Could not refresh the dashboard.\n\n{e}"
            )

    def load_status_data(self):
        search = self.status_search.text()
        filter_val = self.status_filter.currentText()
        try:
            data = self.service.get_inventory_status(search)
            if filter_val != "All Statuses":
                data = [d for d in data if d.status == filter_val]

            self.status_table.setSortingEnabled(False)
            self.status_table.setRowCount(0)
            for i, item in enumerate(data):
                self.status_table.insertRow(i)
                self.status_table.setItem(i, 0, QTableWidgetItem(item.item_num))
                self.status_table.setItem(i, 1, QTableWidgetItem(item.item_name))
                self.status_table.setItem(i, 2, QTableWidgetItem(item.location_name))
                stock_item = QTableWidgetItem(f"{item.in_stock:.2f}")
                stock_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.status_table.setItem(i, 3, stock_item)
                status_item = QTableWidgetItem(item.status)
                status_item.setForeground(status_color(item.status))
                self.status_table.setItem(i, 4, status_item)
            self.status_table.setSortingEnabled(True)
        except Exception as e:
            logging.error(f"Error loading status table: {e}", exc_info=True)
            QMessageBox.critical(
                self, "Stock Status Error", f"Could not load stock status.\n\n{e}"
            )

    def load_rec_data(self):
        try:
            self.recommendations = self.service.get_recommendations()
            self.rec_table.setSortingEnabled(False)
            self.rec_table.setRowCount(0)
            for i, rec in enumerate(self.recommendations):
                self.rec_table.insertRow(i)
                name_item = QTableWidgetItem(rec.item_name)
                name_item.setData(Qt.UserRole, rec)
                self.rec_table.setItem(i, 0, name_item)
                self.rec_table.setItem(i, 1, QTableWidgetItem(rec.src_location))
                self.rec_table.setItem(i, 2, QTableWidgetItem(rec.dest_location))
                src = QTableWidgetItem(f"{rec.src_stock:g}")
                src.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                dest = QTableWidgetItem(f"{rec.dest_stock:g}")
                dest.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                qty_item = QTableWidgetItem(f"{rec.recommended_qty:g}")
                qty_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                qty_item.setData(Qt.UserRole, rec)
                self.rec_table.setItem(i, 3, src)
                self.rec_table.setItem(i, 4, dest)
                self.rec_table.setItem(i, 5, qty_item)
            self.rec_table.setSortingEnabled(True)
        except Exception as e:
            logging.error(f"Error loading rec table: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Recommendations Error",
                f"Could not load transfer recommendations.\n\n{e}",
            )

    def load_compare_data(self):
        search = self.status_search.text()
        try:
            self.pair_analysis = self.service.get_cross_server_analysis(search)
            self.compare_table.setSortingEnabled(False)
            self.compare_table.setRowCount(len(self.pair_analysis))

            for r, item in enumerate(self.pair_analysis):
                name_item = QTableWidgetItem(item.item_name)
                name_item.setData(Qt.UserRole, item)
                self.compare_table.setItem(r, 0, name_item)
                src = QTableWidgetItem(f"{item.src_stock:g}")
                src.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                dest = QTableWidgetItem(f"{item.dest_stock:g}")
                dest.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rec_item = QTableWidgetItem(f"{item.recommended_qty:g}")
                rec_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                rec_item.setData(Qt.UserRole, item)
                self.compare_table.setItem(r, 1, src)
                self.compare_table.setItem(r, 2, dest)
                self.compare_table.setItem(r, 3, rec_item)

                status_item = QTableWidgetItem(item.status)
                if item.recommended_qty > 0:
                    status_item.setBackground(QColor("#ecfdf3"))
                    status_item.setForeground(QColor(COLORS["success"]))
                elif "Dest Low" in item.status:
                    status_item.setBackground(QColor("#fef3f2"))
                    status_item.setForeground(QColor(COLORS["danger"]))
                self.compare_table.setItem(r, 4, status_item)
            self.compare_table.setSortingEnabled(True)
        except Exception as e:
            logging.error(f"Error loading cross-server analysis table: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Transfer Planner Error",
                f"Could not load the transfer planner.\n\n{e}",
            )

    def _selected_row_indexes(self, table: QTableWidget):
        rows = sorted({idx.row() for idx in table.selectionModel().selectedRows()})
        if not rows and table.currentRow() >= 0:
            rows = [table.currentRow()]
        return rows

    def _rec_from_row(self, row: int):
        item = self.rec_table.item(row, 0) or self.rec_table.item(row, 5)
        return item.data(Qt.UserRole) if item else None

    def _compare_from_row(self, row: int):
        item = self.compare_table.item(row, 0) or self.compare_table.item(row, 3)
        return item.data(Qt.UserRole) if item else None

    def _pair_to_recommendation(self, item):
        from ..models.transfer_models import TransferRecommendation
        rules = self.service.get_rules()
        qty = float(item.recommended_qty or 0)
        if qty <= 0:
            qty = 1.0
        return TransferRecommendation(
            item_num=item.item_num,
            item_name=item.item_name,
            dest_store_id="Destination Server",
            dest_location=self.server_info.get("destination", "Destination"),
            dest_stock=item.dest_stock,
            src_store_id="Source Server",
            src_location=self.server_info.get("source", "Source"),
            src_stock=item.src_stock,
            cost=item.cost,
            shortage_qty=max(0, rules.target_stock - item.dest_stock),
            excess_qty=max(0, item.src_stock - rules.surplus_above),
            recommended_qty=qty,
        )

    def _add_rec_row_from_index(self, index):
        rec = self._rec_from_row(index.row())
        if not rec:
            return
        self.add_to_cart_requested.emit(rec)
        QMessageBox.information(
            self, "Added to Cart", f"Added “{rec.item_name}” (qty {rec.recommended_qty:g})."
        )

    def _add_compare_row_from_index(self, index):
        item = self._compare_from_row(index.row())
        if not item:
            return
        rec = self._pair_to_recommendation(item)
        self.add_to_cart_requested.emit(rec)
        QMessageBox.information(
            self, "Added to Cart", f"Added “{rec.item_name}” (qty {rec.recommended_qty:g})."
        )

    def handle_add_selected_recommendations(self):
        rows = self._selected_row_indexes(self.rec_table)
        if not rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Select one or more recommendation rows first.\n\n"
                "Tip: click a row to highlight it (Ctrl+click for multiple).",
            )
            return

        count = 0
        for row in rows:
            rec = self._rec_from_row(row)
            if rec:
                self.add_to_cart_requested.emit(rec)
                count += 1

        if count:
            QMessageBox.information(
                self, "Added to Cart", f"Added {count} selected item(s) to the cart."
            )
        else:
            QMessageBox.warning(self, "Nothing Added", "Could not read the selected rows.")

    def handle_add_all_recommendations(self):
        if self.rec_table.rowCount() == 0:
            QMessageBox.information(self, "Empty", "There are no recommendations to add.")
            return
        reply = QMessageBox.question(
            self,
            "Add All?",
            f"Add all {self.rec_table.rowCount()} recommendation(s) to the cart?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        count = 0
        for r in range(self.rec_table.rowCount()):
            rec = self._rec_from_row(r)
            if rec:
                self.add_to_cart_requested.emit(rec)
                count += 1
        QMessageBox.information(
            self, "Added to Cart", f"Added {count} recommendation(s) to the cart."
        )

    def handle_add_selected_pair_to_cart(self):
        rows = self._selected_row_indexes(self.compare_table)
        if not rows:
            QMessageBox.information(
                self,
                "No Selection",
                "Select one or more planner rows first.\n\n"
                "Tip: click a row to highlight it (Ctrl+click for multiple).",
            )
            return

        count = 0
        for row in rows:
            item = self._compare_from_row(row)
            if not item:
                continue
            self.add_to_cart_requested.emit(self._pair_to_recommendation(item))
            count += 1

        if count:
            QMessageBox.information(
                self, "Added to Cart", f"Added {count} selected item(s) to the cart."
            )
        else:
            QMessageBox.warning(self, "Nothing Added", "Could not read the selected rows.")

    def handle_add_pair_to_cart(self):
        count = 0
        for item in self.pair_analysis:
            if item.recommended_qty > 0:
                self.add_to_cart_requested.emit(self._pair_to_recommendation(item))
                count += 1

        if count > 0:
            QMessageBox.information(
                self,
                "Added to Cart",
                f"Added {count} recommended move(s) from {self.server_info['source']} "
                f"to {self.server_info['destination']}.",
            )
        else:
            QMessageBox.warning(
                self, "No Moves", "No recommended moves found for this route."
            )

    def handle_add_to_cart(self):
        """Backward-compatible alias for Add Selected. """
        self.handle_add_selected_recommendations()
