import logging
from typing import Dict, List, Optional
import time

logger = logging.getLogger("BadBank")

class BadBank:
    """
    The Bad Bank (Asset Management Company).
    
    Purpose:
    1. Holds "Toxic Assets" (Frozen Buckets) that were locked by the Valkyrie Protocol.
    2. Collects "Tithes" (Taxes) from healthy, profitable trades.
    3. Uses Tithes to slowly pay off (close) the toxic debt, chunk by chunk.
    """
    
    def __init__(self):
        self.toxic_assets: Dict[str, Dict] = {} # bucket_id -> {positions, frozen_time, initial_debt}
        self.tithe_balance: float = 0.0
        self.total_tithe_collected: float = 0.0
        self.total_debt_repaid: float = 0.0
        
    def register_toxic_asset(self, bucket_id: str, positions: list):
        """
        Take ownership of a Frozen Bucket.
        """
        if bucket_id in self.toxic_assets:
            logger.warning(f"[BAD BANK] Asset {bucket_id} is already registered.")
            return

        # Calculate total debt (Net Negative PnL)
        # Note: We track volume and floating PnL
        total_volume = sum(p.volume for p in positions)
        
        self.toxic_assets[bucket_id] = {
            'bucket_id': bucket_id,
            'positions': positions, # Storing object references or dicts? Ideally snapshot.
            'frozen_time': time.time(),
            'initial_volume': total_volume,
            'status': 'FROZEN'
        }
        
        logger.critical(f"🏦 [BAD BANK] ACQUIRED TOXIC ASSET: {bucket_id} | Vol: {total_volume:.2f} lots")
        
    def deposit_tithe(self, amount: float, source_symbol: str) -> float:
        """
        Deposit a portion of profits into the Bad Bank.
        Returns the accepted amount.
        """
        if amount <= 0:
            return 0.0
            
        self.tithe_balance += amount
        self.total_tithe_collected += amount
        
        logger.info(f"💰 [BAD BANK] DEPOSIT RECEIVED: ${amount:.2f} from {source_symbol} | Balance: ${self.tithe_balance:.2f}")
        
        # Note: attempt_debt_reduction needs broker and is async, so it's called
        # from the main position_manager cleanup cycle, not here
        # The tithe is stored and will be used in the next cleanup cycle
        
        return amount

    def is_toxic(self, ticket: int) -> bool:
        """Check if a ticket belongs to a toxic asset."""
        for asset in self.toxic_assets.values():
             for p in asset['positions']:
                 # Check ticket. Handle object or dict
                 t = p.ticket if hasattr(p, 'ticket') else p.get('ticket')
                 if t == ticket:
                     return True
        return False

    async def attempt_debt_reduction(self, broker) -> bool:
        """
        Check if we have enough cash to close a micro-chunk of debt.
        
        Logic (Chronos Phase 1):
        1. Find the smallest position in toxic assets.
        2. Calculate cost to close 0.01 lots of it.
        3. If Balance > Profit Loss needed:
           - Close 0.01 lots.
           - Deduct from Tithe Balance.
        """
        if not self.toxic_assets:
            return False
            
        action_taken = False
        
        # Iterate through toxic buckets
        for bucket_id, asset_data in list(self.toxic_assets.items()):
            positions = asset_data['positions']
            
            if not positions:
                continue
                
            # Find the worst losing position (priority to clean up messiest parts)
            # Or best losing position (cheapest to fix)?
            # Strategy: Nibble the largest volume loser to reduce exposure risk.
            loser = None
            for p in positions:
                # We need live profit for accurate calc, but here we might have stale data.
                # Ideally, we fetch live data or use last known.
                # For safety, we just target any position with volume >= 0.01
                if p.volume >= 0.01:
                    loser = p
                    break
            
            if not loser:
                continue
                
            # Target nibble size
            NIBBLE_SIZE = 0.01
            
            # Estimate cost
            # Cost = Validating that paying X amount covers the loss of 0.01 lots.
            # We don't "pay" the broker, we realize the loss.
            # We must verify we have enough 'Tithe' to offset this realized loss within our internal ledger.
            # Example: 0.01 lot loss = -$5.00. We need $5.00 in Tithe Balance.
            
            # We need current price to know actual loss.
            # This requires broker access.
            current_tick = broker.get_last_tick(loser.symbol)
            if not current_tick:
                continue
                
            price = current_tick['bid'] if loser.type == 0 else current_tick['ask'] # Close price
            
            # Calc PnL for 0.01 lot
            # profit = (close_price - open_price) * vol * contract_size
            contract_size = 100 if "XAU" in loser.symbol else 100000
            diff = (price - loser.price_open) if loser.type == 0 else (loser.price_open - price)
            estimated_loss = diff * NIBBLE_SIZE * contract_size
            
            if estimated_loss >= 0:
                # It's actually profitable? Close it immediately! Free money!
                logger.info(f"🏦 [BAD BANK] Found PROFITABLE toxic chunk! Closing free of charge.")
                required_tithe = 0.0
            else:
                required_tithe = abs(estimated_loss)
                
            # Check Affordability
            if self.tithe_balance >= required_tithe:
                logger.info(f"🏦 [BAD BANK] Nibbling 0.01 lot from Ticket #{loser.ticket}. Cost: ${required_tithe:.2f}")
                
                # Execute Partial Close
                res = await broker.close_position(loser.ticket, volume=NIBBLE_SIZE, comment="CHRONOS_NIBBLE")
                
                if res:
                    # Deduct from tithe
                    self.tithe_balance -= required_tithe
                    self.total_debt_repaid += required_tithe
                    
                    # Update internal state
                    loser.volume = round(loser.volume - NIBBLE_SIZE, 2)
                    if loser.volume < 0.01:
                        positions.remove(loser)
                    
                    action_taken = True
                    logger.info(f"🏦 [BAD BANK] Nibble successful. Remaining Tithe: ${self.tithe_balance:.2f}")
                    
                    # If bucket empty, remove asset
                    if not positions:
                        logger.critical(f"🎉 [BAD BANK] TOXIC ASSET {bucket_id} FULLY LIQUIDATED!")
                        del self.toxic_assets[bucket_id]
                        
                    return True
                else:
                     logger.warning(f"🏦 [BAD BANK] Nibble execution failed for #{loser.ticket}")
            else:
                 # Not enough cash, wait.
                 pass
                 
        return action_taken

    def get_stats(self) -> Dict:
        return {
            'assets_count': len(self.toxic_assets),
            'tithe_pool': self.tithe_balance,
            'total_collected': self.total_tithe_collected,
            'total_debt_repaid': self.total_debt_repaid
        }

    def get_status(self) -> str:
        return (f"Bad Bank Status:\n"
                f"  Assets: {len(self.toxic_assets)}\n"
                f"  Cash Ratio: ${self.tithe_balance:.2f} available\n"
                f"  Lifetime Collection: ${self.total_tithe_collected:.2f}")
