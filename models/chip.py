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
    def __init__(self, chips: Dict[int, int] = None, denominations: list = None):
        """
        Initialize a ChipHolder.
        
        Args:
            chips: Optional dictionary of {value: quantity} to start with
            denominations: List of available chip denominations for bank exchanges.
                          Defaults to [1] if not provided.
        """
        self.chips = chips.copy() if chips else {}
        self.denominations = sorted(denominations) if denominations else [1]
    
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
        If exact change cannot be made, exchange with the bank for smaller denominations.
        
        Args:
            other: ChipHolder to transfer to
            amount: Amount to transfer
            
        Raises:
            ValueError: If insufficient chips
        """
        if not isinstance(other, ChipHolder):
            raise TypeError("Can only transfer chips to another ChipHolder")
        
        if amount < 0:
            raise ValueError("Amount must be non-negative")
        
        if amount == 0:
            return
        
        if amount > self.total():
            raise ValueError(f"Not enough chips (have {self.total()}, need {amount})")
        
        # Keep trying to transfer, exchanging with bank if needed
        max_attempts = 100  # Prevent infinite loops
        attempts = 0
        
        while attempts < max_attempts:
            try:
                chips_to_transfer = self._calculate_chip_transfer(amount)
                # Successfully calculated the transfer
                for value, quantity in chips_to_transfer.items():
                    self.remove_chips(value, quantity)
                    other.add_chips(value, quantity)
                return
            except ValueError:
                # Can't make exact change, exchange with bank
                self._exchange_with_bank(amount)
                attempts += 1
        
        raise ValueError(f"Could not transfer {amount} after {max_attempts} bank exchanges")
    
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
    
    def _exchange_with_bank(self, amount: int) -> None:
        """
        Exchange chips with the bank to get smaller denominations.
        This converts larger chips to smaller denominations to enable transactions.
        
        Args:
            amount: The amount that needs to be transferred
        """
        # Find the smallest chip denomination that we can break down
        # We want to exchange a large chip for smaller ones to make exact change
        for chip_value in sorted(self.chips.keys(), reverse=True):
            if self.chips[chip_value] > 0 and chip_value > amount:
                # This chip is larger than what we need, we can break it down
                self.remove_chips(chip_value, 1)
                break_down = self._calculate_breakdown(chip_value)
                for denom_value, denom_qty in break_down.items():
                    self.add_chips(denom_value, denom_qty)
                return
        
        # If no chip is larger than amount, exchange the largest chip we have
        largest_chip = max(self.chips.keys())
        if self.chips[largest_chip] > 0:
            self.remove_chips(largest_chip, 1)
            break_down = self._calculate_breakdown(largest_chip)
            for denom_value, denom_qty in break_down.items():
                self.add_chips(denom_value, denom_qty)
    
    def _calculate_breakdown(self, chip_value: int) -> Dict[int, int]:
        """
        Calculate how to break down a chip into smaller denominations using the bank.
        Uses a greedy algorithm with available denominations.
        
        Args:
            chip_value: The value of the chip to break down
            
        Returns:
            Dictionary of {denomination: quantity} representing the breakdown
        """
        breakdown = {}
        remaining = chip_value
        
        # Use largest available denominations first (excluding the chip_value itself)
        for denom in sorted([d for d in self.denominations if d < chip_value], reverse=True):
            if remaining >= denom:
                count = remaining // denom
                breakdown[denom] = count
                remaining -= count * denom
        
        # If there's a remainder, use the smallest denomination
        if remaining > 0:
            smallest = self.denominations[0]
            breakdown[smallest] = breakdown.get(smallest, 0) + remaining
        
        return breakdown
    
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
        return ChipHolder(self.chips, self.denominations)
    
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