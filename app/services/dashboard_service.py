import logging
from typing import List, Tuple, Optional
from ..db import DatabaseManager
from ..models.transfer_models import StockSummary, InventoryStatus, TransferRecommendation, StorePairAnalysis
from ..search_utils import build_keyword_filter
from ..recommendation_rules import (
    RecommendationRules,
    load_rules_from_config,
    save_rules_to_config,
)


class DashboardService:
    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.rules = load_rules_from_config(db_manager.config)

    def get_rules(self) -> RecommendationRules:
        return self.rules.copy()

    def set_rules(self, rules: RecommendationRules, persist: bool = True) -> RecommendationRules:
        rules = rules.copy()
        rules.validate()
        self.rules = rules
        if persist:
            save_rules_to_config(self.db.config, self.db.config_path, rules)
        return self.rules.copy()

    def reset_rules_to_defaults(self, persist: bool = True) -> RecommendationRules:
        return self.set_rules(RecommendationRules(), persist=persist)

    def _get_store_join_sql(self, use_setup=True):
        """Helper to return conditional join logic for Setup table."""
        if use_setup:
            return "LEFT JOIN dbo.Setup s ON i.Store_ID = s.Store_ID", "ISNULL(s.StoreName, i.Store_ID)"
        return "", "i.Store_ID"

    def get_summary(self) -> StockSummary:
        """Fetch summary counts for dashboard cards using current rules."""
        low = self.rules.low_stock_at
        surplus = self.rules.surplus_above
        query = """
        SELECT 
            SUM(CASE WHEN ISNULL(In_Stock, 0) <= 0 THEN 1 ELSE 0 END) as OutOfStockCount,
            SUM(CASE WHEN ISNULL(In_Stock, 0) > 0 AND ISNULL(In_Stock, 0) <= ? THEN 1 ELSE 0 END) as LowStockCount,
            SUM(CASE WHEN ISNULL(In_Stock, 0) > ? THEN 1 ELSE 0 END) as OverstockedCount
        FROM dbo.Inventory
        """
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, (low, surplus))
                row = cursor.fetchone()
                if row:
                    return StockSummary(
                        out_of_stock_count=int(row[0] or 0),
                        low_stock_count=int(row[1] or 0),
                        overstocked_count=int(row[2] or 0)
                    )
        except Exception as e:
            logging.error(f"Error fetching dashboard summary: {e}")
        return StockSummary(0, 0, 0)

    def get_inventory_status(self, search_term: str = "", store_filter: str = "") -> List[InventoryStatus]:
        """Fetch detailed inventory status list."""
        results = []
        try:
            results = self._fetch_inventory_status(search_term, store_filter, use_setup=True)
        except Exception as e:
            err_str = str(e)
            if "Invalid object name 'dbo.Setup'" in err_str or "Invalid column name" in err_str:
                logging.warning(f"Setup table/column issue ({err_str}), falling back to Store_ID only.")
                results = self._fetch_inventory_status(search_term, store_filter, use_setup=False)
            else:
                logging.error(f"Error fetching inventory status: {e}")
                raise
        return results

    def _fetch_inventory_status(self, search_term: str, store_filter: str, use_setup: bool) -> List[InventoryStatus]:
        join_sql, name_sql = self._get_store_join_sql(use_setup)
        kw_sql, kw_params = build_keyword_filter(["i.ItemNum", "i.ItemName"], search_term)
        low = self.rules.low_stock_at
        surplus = self.rules.surplus_above
        query = f"""
        SELECT TOP (500)
            i.ItemNum,
            i.ItemName,
            i.Store_ID,
            {name_sql} as LocationName,
            i.In_Stock,
            i.Cost,
            CASE 
                WHEN ISNULL(i.In_Stock, 0) <= 0 THEN 'Out of Stock'
                WHEN ISNULL(i.In_Stock, 0) <= ? THEN 'Low Stock'
                WHEN ISNULL(i.In_Stock, 0) > ? THEN 'Overstocked'
                ELSE 'Healthy'
            END as Status
        FROM dbo.Inventory i
        {join_sql}
        WHERE ({kw_sql})
        """
        params = [low, surplus] + list(kw_params)
        if store_filter:
            query += " AND i.Store_ID = ?"
            params.append(store_filter)
        
        query += " ORDER BY i.ItemName"

        items = []
        with self.db.get_source_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                items.append(InventoryStatus(
                    item_num=row[0],
                    item_name=row[1] or "",
                    store_id=row[2],
                    location_name=row[3] or row[2],
                    in_stock=float(row[4] or 0),
                    cost=float(row[5] or 0),
                    status=row[6]
                ))
        return items

    def get_recommendations(self) -> List[TransferRecommendation]:
        """Calculate transfer recommendations based on current rules."""
        try:
            return self._fetch_recommendations(use_setup=True)
        except Exception as e:
            err_str = str(e)
            if "Invalid object name 'dbo.Setup'" in err_str or "Invalid column name" in err_str:
                return self._fetch_recommendations(use_setup=False)
            logging.error(f"Error fetching recommendations: {e}")
            raise

    def _fetch_recommendations(self, use_setup: bool) -> List[TransferRecommendation]:
        join_sql_dest = "LEFT JOIN dbo.Setup ds ON dest.Store_ID = ds.Store_ID" if use_setup else ""
        join_sql_src = "LEFT JOIN dbo.Setup ss ON src.Store_ID = ss.Store_ID" if use_setup else ""
        name_sql_dest = "ISNULL(ds.StoreName, dest.Store_ID)" if use_setup else "dest.Store_ID"
        name_sql_src = "ISNULL(ss.StoreName, src.Store_ID)" if use_setup else "src.Store_ID"

        low = self.rules.low_stock_at
        surplus = self.rules.surplus_above
        target = self.rules.target_stock

        query = f"""
        SELECT 
            dest.ItemNum,
            dest.ItemName,
            dest.Store_ID as Dest_Store_ID,
            {name_sql_dest} as Dest_Location,
            dest.In_Stock as Dest_Stock,
            src.Store_ID as Src_Store_ID,
            {name_sql_src} as Src_Location,
            src.In_Stock as Src_Stock,
            dest.Cost,
            (? - ISNULL(dest.In_Stock, 0)) as Shortage_Qty,
            (ISNULL(src.In_Stock, 0) - ?) as Excess_Qty,
            CASE 
                WHEN (? - ISNULL(dest.In_Stock, 0)) < (ISNULL(src.In_Stock, 0) - ?) 
                THEN (? - ISNULL(dest.In_Stock, 0))
                ELSE (ISNULL(src.In_Stock, 0) - ?)
            END as Recommended_Transfer_Qty
        FROM dbo.Inventory dest
        INNER JOIN dbo.Inventory src ON dest.ItemNum = src.ItemNum AND dest.Store_ID <> src.Store_ID
        {join_sql_dest}
        {join_sql_src}
        WHERE ISNULL(dest.In_Stock, 0) <= ?
          AND ISNULL(src.In_Stock, 0) > ?
          AND (? - ISNULL(dest.In_Stock, 0)) > 0
          AND (ISNULL(src.In_Stock, 0) - ?) > 0
        """
        params = [
            target, surplus,
            target, surplus,
            target, surplus,
            low, surplus,
            target, surplus,
        ]
        
        recommendations = []
        with self.db.get_source_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            for row in cursor.fetchall():
                recommendations.append(TransferRecommendation(
                    item_num=row[0],
                    item_name=row[1] or "",
                    dest_store_id=row[2],
                    dest_location=row[3] or row[2],
                    dest_stock=float(row[4] or 0),
                    src_store_id=row[5],
                    src_location=row[6] or row[5],
                    src_stock=float(row[7] or 0),
                    cost=float(row[8] or 0),
                    shortage_qty=float(row[9]),
                    excess_qty=float(row[10]),
                    recommended_qty=float(row[11])
                ))
        return recommendations

    def get_all_stores(self) -> List[Tuple[str, str]]:
        """Fetch unique list of Store IDs and names."""
        query_with_setup = "SELECT i.Store_ID, ISNULL(s.StoreName, i.Store_ID) FROM dbo.Inventory i LEFT JOIN dbo.Setup s ON i.Store_ID = s.Store_ID GROUP BY i.Store_ID, s.StoreName"
        query_simple = "SELECT Store_ID, Store_ID FROM dbo.Inventory GROUP BY Store_ID"
        
        stores = []
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                try:
                    cursor.execute(query_with_setup)
                except Exception:
                    cursor.execute(query_simple)
                
                for row in cursor.fetchall():
                    stores.append((row[0], row[1]))
        except Exception as e:
            logging.error(f"Error fetching stores: {e}")
        return stores

    def get_comparison_data(self, search_term: str = "") -> dict:
        """Fetch stock levels pivoted by item and store."""
        kw_sql, kw_params = build_keyword_filter(["ItemNum", "ItemName"], search_term)
        query = f"""
        SELECT TOP (500) ItemNum, ItemName, Store_ID, In_Stock
        FROM dbo.Inventory
        WHERE ({kw_sql})
        ORDER BY ItemName
        """
        
        comparison = {}
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, kw_params)
                for row in cursor.fetchall():
                    item_num, item_name, store_id, in_stock = row
                    if item_num not in comparison:
                        comparison[item_num] = {"name": item_name or "", "stocks": {}}
                    comparison[item_num]["stocks"][store_id] = float(in_stock or 0)
        except Exception as e:
            logging.error(f"Error fetching comparison data: {e}", exc_info=True)
            raise RuntimeError(f"Could not load comparison data.\n\nDetails: {e}") from e
        return comparison

    def _analyze_pair(self, inum, iname, src_stock, dest_stock, cost) -> StorePairAnalysis:
        low = self.rules.low_stock_at
        surplus = self.rules.surplus_above
        target = self.rules.target_stock

        shortage = max(0, target - dest_stock)
        excess = max(0, src_stock - surplus)

        rec_qty = 0.0
        status = "Balanced"

        if dest_stock <= low and src_stock > surplus:
            rec_qty = min(shortage, excess)
            status = f"Transfer Recommended ({rec_qty:g})"
        elif dest_stock <= low and src_stock <= surplus:
            status = "Dest Low - No Surplus at Source"
        elif dest_stock > low and dest_stock <= target:
            status = "Healthy"
        elif src_stock > surplus:
            status = "Surplus at Source"
        elif dest_stock > surplus:
            status = "Surplus at Destination"

        return StorePairAnalysis(
            item_num=inum,
            item_name=iname,
            src_stock=src_stock,
            dest_stock=dest_stock,
            recommended_qty=rec_qty,
            cost=cost,
            status=status,
        )

    def get_store_pair_analysis(self, src_id: str, dest_id: str, search_term: str = "") -> List[StorePairAnalysis]:
        """Deep analysis for transfers between two specific locations."""
        kw_sql, kw_params = build_keyword_filter(["i.ItemNum", "i.ItemName"], search_term)
        query = f"""
        SELECT i.ItemNum, i.ItemName, i.Store_ID, i.In_Stock, i.Cost
        FROM dbo.Inventory i
        WHERE i.Store_ID IN (?, ?) 
          AND ({kw_sql})
        ORDER BY i.ItemName
        """
        params = [src_id, dest_id] + list(kw_params)
        
        raw_data = {}
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                for row in cursor.fetchall():
                    inum, iname, sid, stock, cost = row
                    if inum not in raw_data:
                        raw_data[inum] = {"name": iname or "", "src": 0.0, "dest": 0.0, "cost": float(cost or 0)}
                    
                    if sid == src_id:
                        raw_data[inum]["src"] = float(stock or 0)
                    else:
                        raw_data[inum]["dest"] = float(stock or 0)
        except Exception as e:
            logging.error(f"Error fetching store pair analysis: {e}", exc_info=True)
            raise RuntimeError(f"Could not analyze store pair.\n\nDetails: {e}") from e

        analysis = []
        for inum, data in raw_data.items():
            analysis.append(
                self._analyze_pair(
                    inum, data["name"], data["src"], data["dest"], data["cost"]
                )
            )
        return analysis

    def get_cross_server_analysis(self, search_term: str = "") -> List[StorePairAnalysis]:
        """Deep analysis comparing the Source Server (IP) vs Destination Server (IP)."""
        kw_sql, kw_params = build_keyword_filter(["ItemNum", "ItemName"], search_term)
        query = f"SELECT TOP (500) ItemNum, ItemName, In_Stock, Cost FROM dbo.Inventory WHERE ({kw_sql})"

        src_data = {}
        try:
            with self.db.get_source_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, kw_params)
                for row in cursor.fetchall():
                    src_data[row[0]] = {"name": row[1] or "", "stock": float(row[2] or 0), "cost": float(row[3] or 0)}
        except Exception as e:
            logging.error(f"Error fetching from source server: {e}", exc_info=True)
            raise RuntimeError(f"Could not load source inventory for planner.\n\nDetails: {e}") from e

        dest_data = {}
        try:
            with self.db.get_dest_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, kw_params)
                for row in cursor.fetchall():
                    dest_data[row[0]] = {"name": row[1] or "", "stock": float(row[2] or 0), "cost": float(row[3] or 0)}
        except Exception as e:
            logging.error(f"Error fetching from destination server: {e}", exc_info=True)
            raise RuntimeError(f"Could not load destination inventory for planner.\n\nDetails: {e}") from e

        analysis = []
        all_item_nums = set(src_data.keys()) | set(dest_data.keys())
        
        for inum in all_item_nums:
            s_info = src_data.get(inum, {"name": "", "stock": 0.0, "cost": 0.0})
            d_info = dest_data.get(inum, {"name": "", "stock": 0.0, "cost": 0.0})
            iname = s_info["name"] or d_info["name"]
            cost = s_info["cost"] or d_info["cost"]
            pair = self._analyze_pair(inum, iname, s_info["stock"], d_info["stock"], cost)
            if "No Surplus at Source" in pair.status:
                pair.status = "Dest Low - No Surplus at Source Server"
            analysis.append(pair)
        
        return sorted(analysis, key=lambda x: x.item_name)

    def get_server_ips(self) -> dict:
        """Returns source and destination server IPs for display."""
        return self.db.get_server_info()
