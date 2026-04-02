import pyodbc
import logging
from datetime import datetime
from typing import List
from ..models.transfer_models import CartItem, TransferHeader, TransferDetail
from ..db import DatabaseManager

class TransferService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def execute_transfer(self, source_loc: str, dest_loc: str, cart_items: List[CartItem], notes: str = "", user: str = "Admin"):
        """
        Executes a transaction-safe multi-item inventory transfer.
        This is the core business logic.
        """
        if not cart_items:
            raise ValueError("Transfer cart is empty.")

        # Handles are needed for both databases
        # If they are on the same server, we could potentially use one connection with dual-part names,
        # but for maximum flexibility we use separate logic or nested transactions if same server.
        # Here we assume both are on HARSHIL\PCAMERICA.
        
        source_conn = self.db.get_source_connection()
        dest_conn = self.db.get_dest_connection()
        # History is typically in the destination or a management DB
        hist_conn = self.db.get_history_connection()

        try:
            # We must be very careful with multi-database transactions in Python.
            # Standard pyodbc doesn't support distributed transactions (MSDTC) easily.
            # Simpler approach: Lock source, perform all updates, then commit.
            
            source_cursor = source_conn.cursor()
            dest_cursor = dest_conn.cursor()
            hist_cursor = hist_conn.cursor()

            # 1. Fetch common columns (Internal helper logic)
            # This ensures we copy all required PCAmerica metadata (Category, Dept, etc.)
            source_cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Inventory'")
            src_cols = {row[0] for row in source_cursor.fetchall()}
            
            dest_cursor.execute("SELECT COLUMN_NAME FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_NAME = 'Inventory' AND COLUMNPROPERTY(OBJECT_ID('Inventory'), COLUMN_NAME, 'IsIdentity') = 0")
            dest_cols = {row[0] for row in dest_cursor.fetchall()}

            # Columns that exist in both tables and are NOT generated automatically
            common_cols = src_cols.intersection(dest_cols)
            # Filter out columns we handle manually or that cause issues
            skip_cols = {'RowID', 'In_Stock'} 
            sync_cols = [c for c in common_cols if c not in skip_cols]

            # 2. Create Transfer Header
            header_sql = """
            INSERT INTO dbo.TransferHeader (SourceLocation, DestinationLocation, CreatedBy, Notes)
            OUTPUT INSERTED.TransferID
            VALUES (?, ?, ?, ?);
            """
            hist_cursor.execute(header_sql, (source_loc, dest_loc, user, notes))
            transfer_id = hist_cursor.fetchone()[0]

            for item in cart_items:
                # 3. Fetch Full Source Data
                select_sql = f"SELECT {', '.join(sync_cols)}, In_Stock FROM dbo.Inventory WHERE ItemNum = ?"
                source_cursor.execute(select_sql, (item.item_num,))
                source_row = source_cursor.fetchone()
                
                if not source_row:
                    raise ValueError(f"Item {item.item_num} no longer exists in source.")
                
                current_source_stock = float(source_row[-1]) # In_Stock is the last column
                
                # 4. Get current destination stock
                dest_cursor.execute("SELECT In_Stock FROM dbo.Inventory WHERE ItemNum = ?", (item.item_num,))
                dest_row = dest_cursor.fetchone()
                current_dest_stock = float(dest_row[0] if dest_row else 0)

                # 5. Subtract from Source
                new_source_stock = current_source_stock - item.transfer_qty
                source_cursor.execute(
                    "UPDATE dbo.Inventory SET In_Stock = ? WHERE ItemNum = ?",
                    (new_source_stock, item.item_num)
                )

                # 6. Add to/Insert into Destination
                if dest_row:
                    new_dest_stock = current_dest_stock + item.transfer_qty
                    dest_cursor.execute(
                        "UPDATE dbo.Inventory SET In_Stock = ? WHERE ItemNum = ?",
                        (new_dest_stock, item.item_num)
                    )
                else:
                    new_dest_stock = item.transfer_qty
                    
                    # --- Dept_ID Foreign Key Safety Check ---
                    if 'Dept_ID' in sync_cols:
                        dept_idx = sync_cols.index('Dept_ID')
                        dept_id = source_row[dept_idx]
                        if dept_id:
                            dest_cursor.execute("SELECT Dept_ID FROM dbo.Departments WHERE Dept_ID = ?", (dept_id,))
                            if not dest_cursor.fetchone():
                                logging.warning(f"Dept_ID '{dept_id}' not found in destination. Defaulting to 'NONE'.")
                                dest_cursor.execute("SELECT Dept_ID FROM dbo.Departments WHERE Dept_ID = ?", ('NONE',))
                                if not dest_cursor.fetchone():
                                    dest_cursor.execute("INSERT INTO dbo.Departments (Dept_ID, Dept_Name) VALUES (?, ?)", ('NONE', 'System Default None'))
                                source_row_list = list(source_row)
                                source_row_list[dept_idx] = 'NONE'
                                source_row = tuple(source_row_list)
                    # ----------------------------------------

                    # Build Dynamic Insert
                    # source_row has [sync_cols..., In_Stock]
                    cols_to_insert = sync_cols + ['In_Stock']
                    placeholders = ', '.join(['?'] * len(cols_to_insert))
                    insert_sql = f"INSERT INTO dbo.Inventory ({', '.join(cols_to_insert)}) VALUES ({placeholders})"
                    
                    # Values from source_row, BUT override In_Stock with transfer_qty
                    insert_values = list(source_row[:-1]) + [new_dest_stock]
                    dest_cursor.execute(insert_sql, tuple(insert_values))

                # 7. Log Detail
                detail_sql = """
                INSERT INTO dbo.TransferDetail (
                    TransferID, ItemNum, ItemName, Quantity, Cost, 
                    SourceStockBefore, SourceStockAfter, 
                    DestinationStockBefore, DestinationStockAfter
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """
                # We need Cost and ItemName for history
                # Find their index in sync_cols
                try:
                    c_idx = sync_cols.index('Cost')
                    n_idx = sync_cols.index('ItemName')
                    item_cost = float(source_row[c_idx] or 0)
                    item_name = source_row[n_idx] or ""
                except (ValueError, IndexError):
                    item_cost = item.cost
                    item_name = item.item_name

                hist_cursor.execute(detail_sql, (
                    transfer_id, item.item_num, item_name, item.transfer_qty, item_cost,
                    current_source_stock, new_source_stock, current_dest_stock, new_dest_stock
                ))

            # 7. Commit All
            # NOTE: In a multi-machine environment, this is where two-phase commit would go.
            # On a single server, pyodbc usually handles auto-commit or manual.
            source_conn.commit()
            dest_conn.commit()
            hist_conn.commit()
            logging.info(f"Transfer {transfer_id} executed successfully.")
            return transfer_id

        except Exception as e:
            logging.error(f"Transfer failed. Rolling back. Error: {e}")
            try:
                source_conn.rollback()
                dest_conn.rollback()
                hist_conn.rollback()
            except:
                pass
            raise
        finally:
            source_conn.close()
            dest_conn.close()
            hist_conn.close()
            
    def get_history(self, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> List[TransferHeader]:
        """Fetches transfer history summary with total cost calculation and optional date filtering."""
        query = """
            SELECT h.TransferID, h.TransferDate, h.SourceLocation, h.DestinationLocation, h.CreatedBy, h.Notes,
                   COALESCE(SUM(d.Quantity * d.Cost), 0) as TotalCost
            FROM dbo.TransferHeader h
            LEFT JOIN dbo.TransferDetail d ON h.TransferID = d.TransferID
            WHERE 1=1
        """
        params = []
        if start_date:
            query += " AND h.TransferDate >= ?"
            params.append(start_date)
        if end_date:
            query += " AND h.TransferDate <= ?"
            # Ensure end_date covers the full day
            if end_date.hour == 0 and end_date.minute == 0:
                params.append(end_date.replace(hour=23, minute=59, second=59))
            else:
                params.append(end_date)
                
        query += " GROUP BY h.TransferID, h.TransferDate, h.SourceLocation, h.DestinationLocation, h.CreatedBy, h.Notes"
        query += " ORDER BY h.TransferDate DESC"
        
        history = []
        try:
            with self.db.get_history_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    history.append(TransferHeader(
                        transfer_id=row.TransferID,
                        transfer_date=row.TransferDate,
                        source_location=row.SourceLocation,
                        destination_location=row.DestinationLocation,
                        created_by=row.CreatedBy,
                        notes=row.Notes or "",
                        total_cost=float(row.TotalCost)
                    ))
        except Exception as e:
            logging.error(f"Error fetching history: {e}")
        return history

    def export_history_to_csv(self, file_path: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Generates a summary CSV report of transfers."""
        import csv
        history = self.get_history(start_date, end_date)
        
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Transfer ID", "Date", "Source", "Destination", "Created By", "Total Cost", "Notes"])
            
            grand_total = 0
            for h in history:
                writer.writerow([
                    h.transfer_id,
                    h.transfer_date.strftime("%Y-%m-%d %H:%M"),
                    h.source_location,
                    h.destination_location,
                    h.created_by,
                    f"{h.total_cost:.2f}",
                    h.notes
                ])
                grand_total += h.total_cost
            
            writer.writerow([])
            writer.writerow(["", "", "", "", "GRAND TOTAL", f"{grand_total:.2f}", ""])

    def export_detailed_history_to_csv(self, file_path: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Generates a detailed ITEM-LEVEL CSV report of all transfers."""
        import csv
        history = self.get_history(start_date, end_date)
        
        with open(file_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "Date", "Transfer ID", "Source", "Destination", 
                "Item Num", "Item Name", "Qty", "Cost", "Line Total", "Notes"
            ])
            
            grand_total = 0
            for h in history:
                details = self.get_transfer_details(h.transfer_id)
                for d in details:
                    line_total = d.quantity * d.cost
                    writer.writerow([
                        h.transfer_date.strftime("%Y-%m-%d %H:%M"),
                        h.transfer_id,
                        h.source_location,
                        h.destination_location,
                        d.item_num,
                        d.item_name,
                        d.quantity,
                        f"{d.cost:.2f}",
                        f"{line_total:.2f}",
                        h.notes
                    ])
                    grand_total += line_total
            
            writer.writerow([])
            writer.writerow(["", "", "", "", "", "", "GRAND TOTAL", "", f"{grand_total:.2f}", ""])

    def get_transfer_details(self, transfer_id: int) -> List[TransferDetail]:
        """Fetches details for a specific transfer."""
        query = "SELECT * FROM dbo.TransferDetail WHERE TransferID = ?"
        details = []
        try:
            with self.db.get_history_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (transfer_id,))
                for row in cursor.fetchall():
                    details.append(TransferDetail(
                        detail_id=row.TransferDetailID,
                        item_num=row.ItemNum,
                        item_name=row.ItemName,
                        quantity=float(row.Quantity),
                        cost=float(row.Cost or 0),
                        source_stock_before=float(row.SourceStockBefore or 0),
                        source_stock_after=float(row.SourceStockAfter or 0),
                        dest_stock_before=float(row.DestinationStockBefore or 0),
                        dest_stock_after=float(row.DestinationStockAfter or 0)
                    ))
        except Exception as e:
            logging.error(f"Error fetching details for transfer {transfer_id}: {e}")
        return details
