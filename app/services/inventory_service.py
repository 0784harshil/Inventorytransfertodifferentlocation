import pyodbc
import logging
from typing import List
from ..models.transfer_models import InventoryItem
from ..db import DatabaseManager

class InventoryService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def search_inventory(self, search_term: str = "", only_in_stock: bool = False) -> List[InventoryItem]:
        """Fetches items from source inventory with filtering."""
        query = """
        SELECT ItemNum, ItemName, Cost, In_Stock 
        FROM dbo.Inventory
        WHERE (ItemNum LIKE ? OR ItemName LIKE ?)
        """
        if only_in_stock:
            query += " AND In_Stock > 0"
        query += " ORDER BY ItemName"

        items = []
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                wildcard = f"%{search_term}%"
                cursor.execute(query, (wildcard, wildcard))
                
                for row in cursor.fetchall():
                    items.append(InventoryItem(
                        item_num=row.ItemNum,
                        item_name=row.ItemName or "",
                        cost=float(row.Cost or 0),
                        in_stock=float(row.In_Stock or 0)
                    ))
        except Exception as e:
            logging.error(f"Error searching inventory: {e}")
            raise
        return items

    def get_item_stock(self, database_mode: str, item_num: str) -> float:
        """Helper to get stock from either source or destination."""
        query = "SELECT In_Stock FROM dbo.Inventory WHERE ItemNum = ?"
        conn_func = self.db.get_source_connection if database_mode == "source" else self.db.get_dest_connection
        
        try:
            with conn_func() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (item_num,))
                row = cursor.fetchone()
                return float(row[0] if row else 0)
        except Exception as e:
            logging.error(f"Error fetching stock for {item_num} from {database_mode}: {e}")
            return 0.0
