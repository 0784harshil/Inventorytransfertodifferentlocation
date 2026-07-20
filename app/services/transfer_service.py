import pyodbc
import logging
from datetime import datetime
from typing import List, Optional
from PySide6.QtGui import QTextDocument
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtCore import QSizeF
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

        if source_loc.strip().lower() == dest_loc.strip().lower():
            raise ValueError("Source and destination locations must be different.")

        for item in cart_items:
            if item.transfer_qty is None or float(item.transfer_qty) <= 0:
                raise ValueError(
                    f"Invalid quantity for item '{item.item_num}'. Quantity must be greater than zero."
                )

        # Ensure audit tables exist on this machine's history DB (merchant-safe, first-run OK)
        self.db.ensure_transfer_tables(raise_on_error=True)

        # Handles are needed for both databases
        # If they are on the same server, we could potentially use one connection with dual-part names,
        # but for maximum flexibility we use separate logic or nested transactions if same server.
        
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
                # 3. Fetch Full Source Data with row lock for safer concurrent transfers
                select_sql = (
                    f"SELECT {', '.join(sync_cols)}, In_Stock FROM dbo.Inventory "
                    f"WITH (UPDLOCK, ROWLOCK) WHERE ItemNum = ?"
                )
                source_cursor.execute(select_sql, (item.item_num,))
                source_row = source_cursor.fetchone()
                
                if not source_row:
                    raise ValueError(f"Item {item.item_num} no longer exists in source.")
                
                current_source_stock = float(source_row[-1]) # In_Stock is the last column
                # Negative stock is allowed (business requirement for this POS environment)
                
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
            logging.error(f"Transfer failed. Rolling back. Error: {e}", exc_info=True)
            rollback_errors = []
            for label, conn in (
                ("source", source_conn),
                ("destination", dest_conn),
                ("history", hist_conn),
            ):
                try:
                    conn.rollback()
                except Exception as rb_err:
                    rollback_errors.append(f"{label}: {rb_err}")
                    logging.error(f"Rollback failed on {label}: {rb_err}", exc_info=True)
            if rollback_errors:
                raise RuntimeError(
                    f"Transfer failed: {e}\n\nAdditionally, rollback had issues:\n"
                    + "\n".join(rollback_errors)
                ) from e
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
            logging.error(f"Error fetching history: {e}", exc_info=True)
            raise RuntimeError(
                f"Could not load transfer history. Check the history database connection.\n\nDetails: {e}"
            ) from e
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
            logging.error(f"Error fetching details for transfer {transfer_id}: {e}", exc_info=True)
            raise RuntimeError(
                f"Could not load details for transfer {transfer_id}.\n\nDetails: {e}"
            ) from e
        return details

    def export_history_to_pdf(self, file_path: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Generates a professional PDF summary report."""
        history = self.get_history(start_date, end_date)
        store_name = self.db.config.get("APP", "store_name", fallback="Inventory Transfer Pro")
        store_address = self.db.config.get("APP", "store_address", fallback="")
        store_phone = self.db.config.get("APP", "store_phone", fallback="")
        
        date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}" if start_date and end_date else "All Records"
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 20px; color: #333; }}
                .header {{ text-align: center; border-bottom: 2px solid #2c3e50; padding-bottom: 20px; margin-bottom: 30px; }}
                .store-name {{ font-size: 28px; font-weight: bold; color: #2c3e50; margin: 0; }}
                .store-info {{ font-size: 14px; color: #7f8c8d; margin-top: 5px; }}
                .report-title {{ font-size: 20px; font-weight: bold; text-align: left; margin-top: 20px; color: #2980b9; }}
                .report-meta {{ font-size: 12px; color: #95a5a6; margin-bottom: 20px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
                th {{ border-bottom: 2px solid #bdc3c7; padding: 12px 8px; text-align: left; background-color: #f8f9fa; color: #2c3e50; font-weight: bold; }}
                td {{ padding: 10px 8px; border-bottom: 1px solid #ecf0f1; font-size: 13px; }}
                .alt-row {{ background-color: #fcfcfc; }}
                .right {{ text-align: right; }}
                .grand-total {{ margin-top: 30px; text-align: right; border-top: 2px solid #2c3e50; padding-top: 10px; font-size: 18px; font-weight: bold; color: #2c3e50; }}
                .footer {{ margin-top: 50px; font-size: 10px; color: #bdc3c7; text-align: center; border-top: 1px solid #ecf0f1; padding-top: 10px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <p class="store-name">{store_name}</p>
                <p class="store-info">{store_address}{' | ' + store_phone if store_phone else ''}</p>
            </div>
            
            <div class="report-title">Inventory Transfer Summary Report</div>
            <div class="report-meta">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Range: {date_range}</div>
            
            <table>
                <thead>
                    <tr>
                        <th>ID</th>
                        <th>Date</th>
                        <th>Source</th>
                        <th>Destination</th>
                        <th>Created By</th>
                        <th class="right">Total Cost</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        grand_total = 0
        for i, h in enumerate(history):
            row_class = ' class="alt-row"' if i % 2 == 1 else ''
            html += f"""
                    <tr{row_class}>
                        <td>{h.transfer_id}</td>
                        <td>{h.transfer_date.strftime('%Y-%m-%d %H:%M')}</td>
                        <td>{h.source_location}</td>
                        <td>{h.destination_location}</td>
                        <td>{h.created_by}</td>
                        <td class="right">${h.total_cost:,.2f}</td>
                    </tr>
            """
            grand_total += h.total_cost
            
        html += f"""
                </tbody>
            </table>
            
            <div class="grand-total">GRAND TOTAL: ${grand_total:,.2f}</div>
            
            <div class="footer">
                Inventory Transfer Pro | Internal Professional Report
            </div>
        </body>
        </html>
        """
        self._render_pdf(html, file_path)

    def export_detailed_history_to_pdf(self, file_path: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None):
        """Generates a professional detailed (item-level) PDF report."""
        history = self.get_history(start_date, end_date)
        store_name = self.db.config.get("APP", "store_name", fallback="Inventory Transfer Pro")
        store_address = self.db.config.get("APP", "store_address", fallback="")
        store_phone = self.db.config.get("APP", "store_phone", fallback="")
        
        date_range = f"{start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}" if start_date and end_date else "All Records"
        
        html = f"""
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Arial, sans-serif; margin: 15px; color: #333; }}
                .header {{ text-align: center; border-bottom: 2px solid #2c3e50; padding-bottom: 15px; margin-bottom: 20px; }}
                .store-name {{ font-size: 24px; font-weight: bold; color: #2c3e50; margin: 0; }}
                .store-info {{ font-size: 13px; color: #7f8c8d; margin-top: 5px; }}
                .report-title {{ font-size: 18px; font-weight: bold; text-align: left; margin-top: 15px; color: #c0392b; }}
                .report-meta {{ font-size: 11px; color: #95a5a6; margin-bottom: 15px; }}
                table {{ width: 100%; border-collapse: collapse; margin-top: 10px; table-layout: fixed; }}
                th {{ border-bottom: 2px solid #bdc3c7; padding: 8px 5px; text-align: left; background-color: #f8f9fa; color: #2c3e50; font-weight: bold; font-size: 12px; }}
                td {{ padding: 8px 5px; border-bottom: 1px solid #ecf0f1; font-size: 11px; word-wrap: break-word; }}
                .alt-row {{ background-color: #fcfcfc; }}
                .right {{ text-align: right; }}
                .grand-total {{ margin-top: 25px; text-align: right; border-top: 2px solid #2c3e50; padding-top: 8px; font-size: 16px; font-weight: bold; color: #2c3e50; }}
                .footer {{ margin-top: 40px; font-size: 9px; color: #bdc3c7; text-align: center; border-top: 1px solid #ecf0f1; padding-top: 8px; }}
            </style>
        </head>
        <body>
            <div class="header">
                <p class="store-name">{store_name}</p>
                <p class="store-info">{store_address}{' | ' + store_phone if store_phone else ''}</p>
            </div>
            
            <div class="report-title">Inventory Transfer Detailed Item Report</div>
            <div class="report-meta">Generated on: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Range: {date_range}</div>
            
            <table>
                <thead>
                    <tr>
                        <th style="width: 15%;">Date</th>
                        <th style="width: 8%;">ID</th>
                        <th style="width: 15%;">Item Num</th>
                        <th style="width: 25%;">Item Name</th>
                        <th style="width: 7%;" class="right">Qty</th>
                        <th style="width: 10%;" class="right">Cost</th>
                        <th style="width: 10%;" class="right">Total</th>
                        <th style="width: 10%;">Source</th>
                    </tr>
                </thead>
                <tbody>
        """
        
        grand_total = 0
        row_count = 0
        for h in history:
            details = self.get_transfer_details(h.transfer_id)
            for d in details:
                line_total = d.quantity * d.cost
                row_class = ' class="alt-row"' if row_count % 2 == 1 else ''
                html += f"""
                        <tr{row_class}>
                            <td>{h.transfer_date.strftime('%Y-%m-%d')}</td>
                            <td>{h.transfer_id}</td>
                            <td>{d.item_num}</td>
                            <td>{d.item_name}</td>
                            <td class="right">{d.quantity:,.0f}</td>
                            <td class="right">${d.cost:,.2f}</td>
                            <td class="right">${line_total:,.2f}</td>
                            <td>{h.source_location}</td>
                        </tr>
                """
                grand_total += line_total
                row_count += 1
            
        html += f"""
                </tbody>
            </table>
            
            <div class="grand-total">GRAND TOTAL: ${grand_total:,.2f}</div>
            
            <div class="footer">
                Inventory Transfer Pro | Internal Detailed Performance Audit
            </div>
        </body>
        </html>
        """
        self._render_pdf(html, file_path)

    def _render_pdf(self, html_content: str, file_path: str):
        """Helper to render HTML to a high-resolution PDF."""
        printer = QPrinter(QPrinter.HighResolution)
        printer.setOutputFormat(QPrinter.PdfFormat)
        printer.setOutputFileName(file_path)
        
        # Adjust page sizing/margins
        doc = QTextDocument()
        doc.setHtml(html_content)
        doc.setPageSize(QSizeF(printer.pageLayout().fullRectPoints().size()))
        doc.print_(printer)
