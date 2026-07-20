-- Inventory Transfer Dashboard Queries
-- These queries implement the business rules for stock management and transfers.

-- 1. Summary Counts
/*
   Calculates counts for Out of Stock, Low Stock, and Overstocked items.
   Rule:
   - Out of Stock: In_Stock <= 0
   - Low Stock: In_Stock <= 5 (but > 0)
   - Overstocked: In_Stock > 20
*/
SELECT 
    SUM(CASE WHEN ISNULL(In_Stock, 0) <= 0 THEN 1 ELSE 0 END) as OutOfStockCount,
    SUM(CASE WHEN ISNULL(In_Stock, 0) > 0 AND ISNULL(In_Stock, 0) <= 5 THEN 1 ELSE 0 END) as LowStockCount,
    SUM(CASE WHEN ISNULL(In_Stock, 0) > 20 THEN 1 ELSE 0 END) as OverstockedCount
FROM dbo.Inventory;

-- 2. Detailed Stock Status by Location
-- Lists all items and identifies their status.
SELECT 
    i.ItemNum,
    i.ItemName,
    i.Store_ID,
    ISNULL(s.StoreName, i.Store_ID) as LocationName, -- Fallback to Store_ID if Setup doesn't exist or name is missing
    i.In_Stock,
    CASE 
        WHEN ISNULL(i.In_Stock, 0) <= 0 THEN 'Out of Stock'
        WHEN ISNULL(i.In_Stock, 0) <= 5 THEN 'Low Stock'
        WHEN ISNULL(i.In_Stock, 0) > 20 THEN 'Overstocked'
        ELSE 'Healthy'
    END as Status
FROM dbo.Inventory i
LEFT JOIN dbo.Setup s ON i.Store_ID = s.Store_ID
ORDER BY i.ItemName, i.Store_ID;

-- 3. Recommended Item Transfers
/*
   Rules:
   - destination needs stock if In_Stock <= 5
   - source is overstocked if In_Stock > 20
   - desired stock level for destination = 10
   - shortage_qty = 10 - destination_stock
   - excess_qty = source_stock - 20
   - recommended_transfer_qty = minimum(shortage_qty, excess_qty)
   - only show recommendations where recommended_transfer_qty > 0
*/
SELECT 
    dest.ItemNum,
    dest.ItemName,
    dest.Store_ID as Dest_Store_ID,
    ISNULL(ds.StoreName, dest.Store_ID) as Dest_Location,
    dest.In_Stock as Dest_Stock,
    src.Store_ID as Src_Store_ID,
    ISNULL(ss.StoreName, src.Store_ID) as Src_Location,
    src.In_Stock as Src_Stock,
    (10 - ISNULL(dest.In_Stock, 0)) as Shortage_Qty,
    (ISNULL(src.In_Stock, 0) - 20) as Excess_Qty,
    CASE 
        WHEN (10 - ISNULL(dest.In_Stock, 0)) < (ISNULL(src.In_Stock, 0) - 20) 
        THEN (10 - ISNULL(dest.In_Stock, 0))
        ELSE (ISNULL(src.In_Stock, 0) - 20)
    END as Recommended_Transfer_Qty
FROM dbo.Inventory dest
INNER JOIN dbo.Inventory src ON dest.ItemNum = src.ItemNum AND dest.Store_ID <> src.Store_ID
LEFT JOIN dbo.Setup ds ON dest.Store_ID = ds.Store_ID
LEFT JOIN dbo.Setup ss ON src.Store_ID = ss.Store_ID
WHERE ISNULL(dest.In_Stock, 0) <= 5
  AND ISNULL(src.In_Stock, 0) > 20
  AND (10 - ISNULL(dest.In_Stock, 0)) > 0
  AND (ISNULL(src.In_Stock, 0) - 20) > 0;
