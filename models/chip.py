from __future__ import annotations
from dataclasses import dataclass
from typing import Dict

@dataclass(frozen=True)
class Chip:
    value: int

    def __repr__(self):
        return str(self.value)

class ChipHolder:
    """
    A class that maps chip values to quantities.
    Used by players for their stacks and for the pot.
    """
    def __init__(self, chips: Dict[int, int] = None):
        """
        Initialize a ChipHolder.
        
        Args:
            chips: Optional dictionary of {value: quantity} to start with
        """
        self.chips = chips.copy() if chips else {}
    
    def add_chips(self, value: int, quantity: int) -> None:
        """Add chips of a specific value."""
        if value <= 0:
            raise ValueError("Chip value must be positive")
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if quantity == 0:
            return
        
        self.chips[value] = self.chips.get(value, 0) + quantity
    
    def remove_chips(self, value: int, quantity: int) -> None:
        """Remove chips of a specific value."""
        if quantity < 0:
            raise ValueError("Quantity cannot be negative")
        if quantity == 0:
            return
        
        current = self.chips.get(value, 0)
        if current < quantity:
            raise ValueError(f"Not enough {value}-value chips (have {current}, need {quantity})")
        
        self.chips[value] -= quantity
        if self.chips[value] == 0:
            del self.chips[value]
    
    def transfer_to(self, other: ChipHolder, amount: int) -> None:
        """
        Transfer a specific amount to another ChipHolder using largest chips first.
        
        Args:
            other: ChipHolder to transfer to
            amount: Amount to transfer
            
        Raises:
            ValueError: If cannot make exact change or insufficient chips
        """
        if not isinstance(other, ChipHolder):
            raise TypeError("Can only transfer chips to another ChipHolder")
        
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        
        if amount == 0:
            return
        
        if amount > self.total():
            raise ValueError(f"Not enough chips (have {self.total()}, need {amount})")
        
        # Calculate which chips to transfer
        chips_to_transfer = self._calculate_chip_transfer(amount)
        
        # Perform the transfer
        for value, quantity in chips_to_transfer.items():
            self.remove_chips(value, quantity)
            other.add_chips(value, quantity)
    
    def _calculate_chip_transfer(self, amount: int) -> Dict[int, int]:
        """Calculate which chips to use for a transfer (greedy algorithm)."""
        remaining = amount
        chips_to_transfer = {}
        
        # Use largest chips first
        for value in sorted(self.chips.keys(), reverse=True):
            available = self.chips[value]
            needed = remaining // value
            
            if needed > 0:
                transfer_count = min(needed, available)
                chips_to_transfer[value] = transfer_count
                remaining -= transfer_count * value
        
        if remaining > 0:
            raise ValueError(f"Cannot make exact change for {amount} with available chips")
        
        return chips_to_transfer
    
    def transfer_all_to(self, other: ChipHolder) -> None:
        """Transfer all chips to another ChipHolder."""
        if not isinstance(other, ChipHolder):
            raise TypeError("Can only transfer chips to another ChipHolder")
        
        for value, quantity in list(self.chips.items()):
            other.add_chips(value, quantity)
            self.remove_chips(value, quantity)
    
    def total(self) -> int:
        """Calculate total value of all chips."""
        return sum(value * qty for value, qty in self.chips.items())
    
    def copy(self) -> 'ChipHolder':
        """Create a deep copy of this ChipHolder."""
        return ChipHolder(self.chips)
    
    def is_empty(self) -> bool:
        """Check if this ChipHolder has no chips."""
        return len(self.chips) == 0
    
    def __repr__(self) -> str:
        return f"ChipHolder(total={self.total()}, chips={self.chips})"
    
    def __str__(self) -> str:
        if self.is_empty():
            return "ChipHolder(empty)"
        chip_str = ", ".join(f"{qty}×${value}" for value, qty in sorted(self.chips.items()))
        return f"ChipHolder({chip_str}, total=${self.total()})"
    
    def __eq__(self, other) -> bool:
        """Two ChipHolders are equal if they have the same chips."""
        if not isinstance(other, ChipHolder):
            return False
        return self.chips == other.chips