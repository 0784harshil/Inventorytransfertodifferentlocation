from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QTableWidget, QTableWidgetItem,
    QPushButton, QLabel, QLineEdit, QMessageBox, QHeaderView, QFormLayout,
    QAbstractItemView,
)
from PySide6.QtCore import Qt
from .styles import configure_table


class StoreFormDialog(QDialog):
    def __init__(
        self,
        parent=None,
        title="Add Store",
        name="",
        server="",
        database="",
        db_manager=None,
    ):
        super().__init__(parent)
        self.db_manager = db_manager
        self.setWindowTitle(title)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        heading = QLabel(title)
        heading.setObjectName("PageTitle")
        layout.addWidget(heading)

        form_layout = QFormLayout()
        form_layout.setSpacing(10)

        self.txt_name = QLineEdit(name)
        self.txt_name.setPlaceholderText("e.g. Main Store")
        form_layout.addRow("Store Name", self.txt_name)

        self.txt_server = QLineEdit(server)
        self.txt_server.setPlaceholderText(r"e.g. localhost\PCAMERICA")
        form_layout.addRow("Server Address", self.txt_server)

        self.txt_database = QLineEdit(database)
        self.txt_database.setPlaceholderText("e.g. cresql")
        form_layout.addRow("Database Name", self.txt_database)

        layout.addLayout(form_layout)

        btn_layout = QHBoxLayout()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_save = QPushButton("Save Store")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.clicked.connect(self.validate_and_accept)
        btn_layout.addStretch()
        btn_layout.addWidget(self.btn_cancel)
        btn_layout.addWidget(self.btn_save)
        layout.addLayout(btn_layout)

    def validate_and_accept(self):
        if not self.txt_name.text().strip():
            QMessageBox.warning(self, "Validation Error", "Store Name is required.")
            return
        if not self.txt_server.text().strip():
            QMessageBox.warning(self, "Validation Error", "Server Address is required.")
            return
        if not self.txt_database.text().strip():
            QMessageBox.warning(self, "Validation Error", "Database Name is required.")
            return

        # Optional live connection test when a db manager is available
        db = getattr(self, "db_manager", None)
        if db is not None:
            server = self.txt_server.text().strip()
            database = self.txt_database.text().strip()
            try:
                db.test_connection(server, database)
            except Exception as e:
                reply = QMessageBox.question(
                    self,
                    "Connection Failed",
                    "Could not connect with the new server/database settings.\n\n"
                    f"{e}\n\n"
                    "Save anyway? The app will use these settings on the next request.",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return
        self.accept()

    def get_data(self):
        return {
            "name": self.txt_name.text().strip(),
            "server": self.txt_server.text().strip(),
            "database": self.txt_database.text().strip(),
        }


class ManageStoresDialog(QDialog):
    def __init__(self, db_manager, parent=None):
        super().__init__(parent)
        self.db = db_manager
        self.setWindowTitle("Manage Stores")
        self.resize(720, 440)
        self.setMinimumSize(560, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(12)

        title = QLabel("Manage Stores")
        title.setObjectName("PageTitle")
        info = QLabel(
            f"Changes save to:\n{self.db.config_path}"
        )
        info.setObjectName("PageSubtitle")
        info.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(info)

        main_layout = QHBoxLayout()
        main_layout.setSpacing(12)

        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.setHorizontalHeaderLabels(["Key", "Store Name", "Server / Instance", "Database"])
        configure_table(self.table)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.table.doubleClicked.connect(self.edit_store)
        main_layout.addWidget(self.table, 1)

        btn_sidebar = QVBoxLayout()
        btn_sidebar.setSpacing(8)
        self.btn_add = QPushButton("Add Store")
        self.btn_add.setObjectName("PrimaryButton")
        self.btn_add.clicked.connect(self.add_store)

        self.btn_edit = QPushButton("Edit")
        self.btn_edit.clicked.connect(self.edit_store)

        self.btn_delete = QPushButton("Delete")
        self.btn_delete.setObjectName("GhostDanger")
        self.btn_delete.clicked.connect(self.delete_store)

        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.accept)

        btn_sidebar.addWidget(self.btn_add)
        btn_sidebar.addWidget(self.btn_edit)
        btn_sidebar.addWidget(self.btn_delete)
        btn_sidebar.addStretch()
        btn_sidebar.addWidget(self.btn_close)
        main_layout.addLayout(btn_sidebar)
        layout.addLayout(main_layout)

        self.load_stores()

    def load_stores(self):
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        for i, (key, store) in enumerate(self.db.stores.items()):
            self.table.insertRow(i)
            self.table.setItem(i, 0, QTableWidgetItem(key))
            self.table.setItem(i, 1, QTableWidgetItem(store["name"]))
            self.table.setItem(i, 2, QTableWidgetItem(store["server"]))
            self.table.setItem(i, 3, QTableWidgetItem(store["database"]))
        self.table.setSortingEnabled(True)

    def add_store(self):
        dlg = StoreFormDialog(self, title="Add New Store", db_manager=self.db)
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                self.db.add_store(data["name"], data["server"], data["database"])
                self.load_stores()
                QMessageBox.information(
                    self,
                    "Store Added",
                    f"“{data['name']}” was saved.\n\n"
                    f"Server: {data['server']}\nDatabase: {data['database']}",
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Save Failed", f"Could not add the store.\n\n{e}"
                )

    def edit_store(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a store to edit.")
            return

        row = selected_rows[0].row()
        key = self.table.item(row, 0).text()
        store = self.db.stores[key]

        dlg = StoreFormDialog(
            self,
            title="Edit Store",
            name=store["name"],
            server=store["server"],
            database=store["database"],
            db_manager=self.db,
        )
        if dlg.exec() == QDialog.Accepted:
            data = dlg.get_data()
            try:
                self.db.update_store(key, data["name"], data["server"], data["database"])
                self.load_stores()
                QMessageBox.information(
                    self,
                    "Store Updated",
                    f"“{data['name']}” was updated and will be used immediately.\n\n"
                    f"Server: {data['server']}\nDatabase: {data['database']}",
                )
            except Exception as e:
                QMessageBox.critical(
                    self, "Save Failed", f"Could not update the store.\n\n{e}"
                )

    def delete_store(self):
        selected_rows = self.table.selectionModel().selectedRows()
        if not selected_rows:
            QMessageBox.information(self, "No Selection", "Please select a store to delete.")
            return

        row = selected_rows[0].row()
        key = self.table.item(row, 0).text()
        store_name = self.table.item(row, 1).text()

        reply = QMessageBox.question(
            self,
            "Confirm Delete",
            f"Delete the store “{store_name}” from configuration?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if reply == QMessageBox.Yes:
            self.db.delete_store(key)
            self.load_stores()
