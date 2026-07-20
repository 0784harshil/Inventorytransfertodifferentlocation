import logging
from typing import List
from ..models.transfer_models import InventoryItem
from ..db import DatabaseManager
from ..search_utils import build_keyword_filter

# Cap unfiltered / broad results so the UI stays responsive
DEFAULT_RESULT_LIMIT = 500


class InventoryService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager

    def search_inventory(
        self,
        search_term: str = "",
        only_in_stock: bool = False,
        limit: int = DEFAULT_RESULT_LIMIT,
    ) -> List[InventoryItem]:
        """Fetches items from source inventory with multi-keyword filtering."""
        where_clause, params = build_keyword_filter(
            ["ItemNum", "ItemName"], search_term
        )

        query = f"""
        SELECT TOP ({int(limit)}) ItemNum, ItemName, Cost, In_Stock
        FROM dbo.Inventory
        WHERE ({where_clause})
        """
        if only_in_stock:
            query += " AND In_Stock > 0"
        query += " ORDER BY ItemName"

        items: List[InventoryItem] = []
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)

                for row in cursor.fetchall():
                    items.append(
                        InventoryItem(
                            item_num=row.ItemNum,
                            item_name=row.ItemName or "",
                            cost=float(row.Cost or 0),
                            in_stock=float(row.In_Stock or 0),
                        )
                    )
        except Exception as e:
            logging.error(f"Error searching inventory: {e}", exc_info=True)
            raise RuntimeError(
                f"Could not search inventory. Check the database connection.\n\nDetails: {e}"
            ) from e
        return items

    def get_item_stock(self, database_mode: str, item_num: str) -> float:
        """Helper to get stock from either source or destination."""
        query = "SELECT In_Stock FROM dbo.Inventory WHERE ItemNum = ?"
        conn_func = (
            self.db.get_source_connection
            if database_mode == "source"
            else self.db.get_dest_connection
        )

        try:
            with conn_func() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (item_num,))
                row = cursor.fetchone()
                if row is None:
                    return 0.0
                return float(row[0] if row[0] is not None else 0)
        except Exception as e:
            logging.error(
                f"Error fetching stock for {item_num} from {database_mode}: {e}",
                exc_info=True,
            )
            raise RuntimeError(
                f"Could not read stock for item '{item_num}' from {database_mode}.\n\nDetails: {e}"
            ) from e
