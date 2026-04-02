# Inventory Transfer App (PySide6)

A professional desktop application for Windows to transfer inventory between store databases with full transaction integrity.

## Features
- **Modern User Interface**: Built with PySide6 for a clean, professional desktop experience.
- **Cart-based Workflow**: Select multiple items, adjust quantities, review, and confirm one atomic transaction.
- **Transaction Safety**: Uses SQL Server Transactions to ensure `In_Stock` is subtracted from source and added to destination simultaneously.
- **Audit Logging**: Full history of transfers with detail breakdown (Stock Before/After).
- **Searchable Inventory**: Real-time filtering by `ItemNum` or `ItemName`.

## Folder Structure
```text
inventory_transfer_app/
│
├── app/                  # Main Python Application
│   ├── ui/               # Layouts & Windows
│   ├── services/         # Business Logic (DB Transactions)
│   ├── models/           # Data Objects
│   ├── config.ini        # SQL Server Connection Details
│   ├── main.py           # Application Entry Point
│   └── logs/             # Daily Audit Logs
│
├── sql/                  # Setup Scripts
│   └── create_transfer_tables.sql
│
├── requirements.txt      # Python Dependencies
└── README.md             # Documentation
```

## Setup Instructions

### 1. Database Setup
1. Open SQL Server Management Studio (SSMS).
2. Connect to `HARSHIL\PCAMERICA`.
3. Locate `cresqlcat` (or your destination DB).
4. Run the script `sql/create_transfer_tables.sql`.

### 2. Python Environment
Install Python 3.11+ and the required libraries:
```powershell
pip install -r requirements.txt
```

### 3. Application Configuration
Ensure your SQL Server settings are correct in `app/config.ini`:
- `server`: Your SQL Server instance.
- `source_database`: Defaults to `cresql`.
- `destination_database`: Defaults to `cresqlcat`.

### 4. Running the App
Start the desktop application:
```powershell
python app/main.py
```

## How the Sync Works
The `transfer_service.py` handles the logic:
1. **Starts Transactions** on both source and destination connections.
2. **Validates Stock**: Re-checks availability in the source database immediately before updating.
3. **Subtracts Quantity**: Updates `dbo.Inventory` in `cresql`.
4. **Upserts Destination**:
    - If `ItemNum` exists in `cresqlcat`, it adds to the current `In_Stock`.
    - If it doesn't exist, it inserts the item with the transferred quantity.
5. **Records History**: Logs the move in `TransferHeader` and `TransferDetail`.
6. **Commits**: Only when every step above succeeds.

---
**Developed by Antigravity**
