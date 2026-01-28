import logging
import numpy as np
from typing import List, Dict, Tuple, Optional

logger = logging.getLogger("LiquidityMapper")

class LiquidityMapper:
    """
    Detects Institutional Liquidity Pools and 'Stop Hunt' Zones.
    
    Logic:
    1. Identifies Swing Highs/Lows (Pivot Points).
    2. Clusters nearby pivots into "Liquidity Walls".
    3. Blocks entries that trade directly INTO a wall (Buying resistance / Selling support).
    """

    def __init__(self, pivot_lookback=5, wall_thickness_pips=5.0, decay_factor=0.98):
        self.pivot_lookback = pivot_lookback
        self.wall_thickness_pips = wall_thickness_pips
        self.decay_factor = decay_factor # Old levels get weaker over time
        self.cached_walls = {}
        self.last_update_ts = 0

    def _find_pivots(self, candles: List[Dict]) -> Tuple[List[float], List[float]]:
        """
        Identify local Highs and Lows (Fractals).
        """
        highs = []
        lows = []
        
        if len(candles) < (self.pivot_lookback * 2 + 1):
            return highs, lows

        # Extract numpy arrays for speed
        h_arr = np.array([c.get('high', 0) for c in candles])
        l_arr = np.array([c.get('low', 0) for c in candles])
        
        # Simple window checking
        for i in range(self.pivot_lookback, len(candles) - self.pivot_lookback):
            window_h = h_arr[i - self.pivot_lookback : i + self.pivot_lookback + 1]
            window_l = l_arr[i - self.pivot_lookback : i + self.pivot_lookback + 1]
            
            # Check if current is max of window
            if h_arr[i] == np.max(window_h):
                highs.append(h_arr[i])
                
            # Check if current is min of window
            if l_arr[i] == np.min(window_l):
                lows.append(l_arr[i])
                
        return highs, lows

    def map_liquidity(self, candles: List[Dict], current_price: float) -> Dict[str, List[Dict]]:
        """
        Generates a map of Support (Buy Liquidity) and Resistance (Sell Liquidity) zones.
        """
        if not candles:
            return {'supports': [], 'resistances': []}

        highs, lows = self._find_pivots(candles)
        
        # Cluster pivots into walls
        # Use simple grouping: if levels are within X pips, merge them.
        # XAUUSD uses 0.01 point size usually, Forex 0.0001
        # We assume price is raw.
        
        # Simple clustering algorithm
        resistances = self._cluster_levels(highs, is_resistance=True)
        supports = self._cluster_levels(lows, is_resistance=False)
        
        # Filter active walls (close to price) to save processing
        # Keep only walls within reasonable distance (e.g. 500 pips)
        # This is optional but good for optimization.
        
        return {
            'supports': supports,
            'resistances': resistances
        }

    def _cluster_levels(self, levels: List[float], is_resistance: bool) -> List[Dict]:
        if not levels:
            return []
            
        levels.sort()
        clusters = []
        
        if not levels: return []
        
        current_cluster = [levels[0]]
        
        # Determine threshold in raw price units based on magnitude
        # Heuristic: 0.05% of price
        avg_price = levels[0]
        threshold = avg_price * 0.0005 

        for i in range(1, len(levels)):
            if levels[i] - levels[i-1] <= threshold:
                current_cluster.append(levels[i])
            else:
                # Close cluster
                clusters.append(self._process_cluster(current_cluster, is_resistance))
                current_cluster = [levels[i]]
        
        # Append last cluster
        if current_cluster:
            clusters.append(self._process_cluster(current_cluster, is_resistance))
            
        return clusters

    def _process_cluster(self, levels: List[float], is_resistance: bool) -> Dict:
        """Calculate stats for a cluster of pivots."""
        avg_level = sum(levels) / len(levels)
        strength = len(levels) # More touches = stronger wall
        return {
            'price': avg_level,
            'strength': strength,
            'type': 'RESISTANCE' if is_resistance else 'SUPPORT'
        }

    def should_avoid_entry(self, current_price: float, action: str, liquidity_map: Dict) -> Tuple[bool, str]:
        """
        Determines if an entry should be blocked due to a Liquidity Wall.
        
        Args:
            current_price: Current Bid/Ask
            action: "BUY" or "SELL"
            liquidity_map: Output from map_liquidity
            
        Returns:
            (should_block, reason)
        """
        # Define "Too Close" threshold (e.g. 0.03% of price)
        proximity_threshold = current_price * 0.0003 
        
        if action == "BUY":
            # Check if we are buying directly into a RESISTANCE wall
            # If price is just BELOW a resistance, avoid buying (Breakout trap risk)
            for wall in liquidity_map['resistances']:
                dist = wall['price'] - current_price
                
                # If Resistance is ABOVE us (dist > 0) AND VERY CLOSE (dist < threshold)
                # AND it's a strong wall (strength >= 2)
                if 0 < dist < proximity_threshold and wall['strength'] >= 2:
                    return True, f"Blocked: Buying into Resistance Wall @ {wall['price']:.2f} (Str: {wall['strength']})"
                    
        elif action == "SELL":
            # Check if we are selling directly into a SUPPORT wall
            # If price is just ABOVE a support, avoid selling (Bear trap risk)
            for wall in liquidity_map['supports']:
                dist = current_price - wall['price']
                
                # If Support is BELOW us (dist > 0) AND VERY CLOSE
                if 0 < dist < proximity_threshold and wall['strength'] >= 2:
                    return True, f"Blocked: Selling into Support Wall @ {wall['price']:.2f} (Str: {wall['strength']})"
                    
        return False, "Clear"