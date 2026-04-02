from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

@dataclass
class InventoryItem:
    item_num: str
    item_name: str
    cost: float
    in_stock: float

@dataclass
class CartItem:
    item_num: str
    item_name: str
    cost: float
    source_stock: float
    transfer_qty: float

    @property
    def est_dest_stock_after(self) -> float:
        # This will be updated by the service when added to cart
        return self.transfer_qty

@dataclass
class TransferHeader:
    transfer_id: Optional[int]
    transfer_date: datetime
    source_location: str
    destination_location: str
    created_by: str
    notes: str
    total_cost: float = 0.0
    details: List['TransferDetail'] = None

@dataclass
class TransferDetail:
    detail_id: Optional[int]
    item_num: str
    item_name: str
    quantity: float
    cost: float
    source_stock_before: float
    source_stock_after: float
    dest_stock_before: float
    dest_stock_after: float
