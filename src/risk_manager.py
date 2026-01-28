"""
Risk Manager - Handles zone recovery, hedging, and risk management.

This module provides comprehensive risk management including:
- Zone recovery logic with AI-enhanced parameters
- Dynamic hedging based on market conditions
- Risk validation and safety checks
- Cooldown management to prevent rapid-fire trading

Author: AETHER Development Team
License: MIT
Version: 1.0.1 [SUPERBOT EVOLUTION]
"""

import time
import os
import logging
import threading
import math
import MetaTrader5 as mt5
from typing import Dict, List, Optional, Any, Tuple, Callable
from dataclasses import dataclass, is_dataclass
from enum import Enum
from src.utils.data_normalization import normalize_positions
from src.constants import AdaptiveRisk, VolatilityAdjustment

# Import enhanced trade explainer for detailed logging
try:
    from .utils.trade_explainer import TradeExplainer
    EXPLAINER_AVAILABLE = True
except ImportError:
    EXPLAINER_AVAILABLE = False

logger = logging.getLogger("RiskManager")

# Setup UI Logger for console output (Shared with Main Bot)
ui_logger = logging.getLogger("AETHER_UI")
if not ui_logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter('%(message)s'))
    ui_logger.addHandler(console_handler)
    ui_logger.propagate = False


def retry_with_backoff(
    operation: Callable,
    max_attempts: int = 3,
    initial_delay: float = 0.5,
    backoff_multiplier: float = 2.0,
    max_total_time: float = 10.0,
    operation_name: str = "operation"
) -> Tuple[bool, Any]:
    """
    Retry an operation with exponential backoff and timeout.
    """
    delay = initial_delay
    start_time = time.time()
    
    for attempt in range(1, max_attempts + 1):
        if time.time() - start_time > max_total_time:
            logger.error(f"[RETRY] {operation_name} timeout exceeded ({max_total_time}s)")
            return False, None
        
        try:
            success, result = operation()
            
            if success:
                if attempt > 1:
                    logger.info(f"[RETRY] {operation_name} succeeded on attempt {attempt}/{max_attempts}")
                return True, result
            
            if result and isinstance(result, dict):
                retcode = result.get('retcode', 0)
                if retcode == 10036:  # Position doesn't exist
                    logger.info(f"[RETRY] {operation_name} - position no longer exists, aborting retries")
                    return False, result
            
            if attempt < max_attempts:
                logger.warning(f"[RETRY] {operation_name} failed (attempt {attempt}/{max_attempts}), retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_multiplier
            else:
                logger.error(f"[RETRY] {operation_name} failed after {max_attempts} attempts")
                return False, result
                
        except Exception as e:
            if attempt < max_attempts:
                logger.warning(f"[RETRY] {operation_name} exception (attempt {attempt}/{max_attempts}): {e}, retrying in {delay:.1f}s...")
                time.sleep(delay)
                delay *= backoff_multiplier
            else:
                logger.error(f"[RETRY] {operation_name} exception after {max_attempts} attempts: {e}")
                return False, None
    
    return False, None


class RiskState(Enum):
    NORMAL = "normal"
    HEDGING = "hedging"
    RECOVERY = "recovery"
    EMERGENCY = "emergency"


@dataclass
class ZoneConfig:
    zone_pips: float
    tp_pips: float
    max_hedges: int = 10
    min_age_seconds: float = 3.0
    hedge_cooldown_seconds: float = 15.0
    bucket_close_cooldown_seconds: float = 15.0
    emergency_hedge_threshold: int = 10


@dataclass
class HedgeState:
    last_hedge_time: float = 0.0
    active_hedges: int = 0
    total_positions: int = 0
    zone_width_points: float = 0.0
    tp_width_points: float = 0.0
    high_vol_mode: bool = False
    volatility_scale: float = 1.0
    last_volatility_scale_update: float = 0.0
    lock: threading.Lock = None

    def __post_init__(self):
        if self.lock is None:
            self.lock = threading.Lock()


class RiskManager:
    """
    Manages risk through zone recovery and intelligent hedging.
    [SUPERBOT] Enhanced with Spread Health Monitoring.
    """

    def __init__(self, zone_config: ZoneConfig):
        self.config = zone_config
        self._hedge_states: Dict[str, HedgeState] = {}
        self._pending_hedges: Dict[str, float] = {}
        self._global_position_cap = 10
        self._lock = threading.Lock()
        self._last_log_time = 0.0
        
        # [SUPERBOT MINIPASO 1.1] Definición de variables de salud
        self.spread_history = [] 
        self.max_spread_multiplier = 2.5
        
        self._time_offset: Optional[float] = None
        self._last_offset_calc: float = 0.0

        logger.info(f"RiskManager initialized with zone: {zone_config.zone_pips}pips, TP: {zone_config.tp_pips}pips")

    # [SUPERBOT MINIPASO 1.2] Algoritmo de validación de Spread
    def is_spread_healthy(self, current_spread: float) -> bool:
        if not hasattr(self, '_last_spread_update'): self._last_spread_update = 0
        now = time.time()
        
        if not self.spread_history:
            self.spread_history.append(current_spread)
            return True
        
        avg_spread = sum(self.spread_history) / len(self.spread_history)
        
        # SOLO grabar en el historial una vez por segundo para tener un promedio real
        if now - self._last_spread_update > 1.0:
            self.spread_history.append(current_spread)
            if len(self.spread_history) > 50:
                self.spread_history.pop(0)
            self._last_spread_update = now
            
        if current_spread > (avg_spread * self.max_spread_multiplier):
            logger.warning(f"[SPREAD VETO] Anomalía: {current_spread} > {avg_spread * self.max_spread_multiplier:.2f}")
            return False
        return True

    def _get_hedge_state(self, symbol: str) -> HedgeState:
        if symbol not in self._hedge_states:
            self._hedge_states[symbol] = HedgeState()
        return self._hedge_states[symbol]

    def _calculate_adaptive_factors(self, atr_val: float) -> Tuple[float, float]:
        if atr_val <= 0:
            return AdaptiveRisk.COOLDOWN_BASE, 1.0
        baseline = 2.0 
        vol_ratio = atr_val / baseline
        if vol_ratio < AdaptiveRisk.VOL_LOW:
            cooldown = AdaptiveRisk.COOLDOWN_MIN
        elif vol_ratio > AdaptiveRisk.VOL_EXTREME:
            cooldown = AdaptiveRisk.COOLDOWN_MAX
        elif vol_ratio > AdaptiveRisk.VOL_HIGH:
            cooldown = 15.0
        else:
            cooldown = AdaptiveRisk.COOLDOWN_BASE
        zone_mult = max(1.0, vol_ratio) if vol_ratio > 1.0 else 1.0
        return cooldown, zone_mult

    def validate_hedge_conditions(self, broker, symbol: str, positions: List[Dict],
                                tick: Dict, point: float, atr_val: float = 0.0, max_hedges_override: int = None) -> Tuple[bool, str]:
        if not positions:
            return False, "No positions to hedge"

        state = self._get_hedge_state(symbol)

        with state.lock:
            # [SUPERBOT INTEGRATION] Validar salud del spread antes de cualquier otra condición
            current_spread = tick.get('spread', 0)
            if current_spread > 0 and not self.is_spread_healthy(float(current_spread)):
                return False, f"Spread unhealthy ({current_spread})"

            limit = max_hedges_override if max_hedges_override is not None else self.config.max_hedges
            if len(positions) >= limit:
                logger.info(f"[HEDGE_CHECK] Max hedges reached ({len(positions)}/{limit})")
                return False, f"Max hedges reached ({len(positions)}/{limit})"

            all_positions = broker.get_positions()
            if all_positions is None:
                return False, "Failed to fetch global positions"

            total_positions = len(all_positions)
            if total_positions >= self._global_position_cap:
                return False, f"Global position cap reached ({total_positions}/{self._global_position_cap})"

            current_server_time = broker.get_tick(symbol).get('time', time.time())
            sorted_pos = sorted(positions, key=lambda p: p['time'])
            last_pos = sorted_pos[-1]
            age_since_last = current_server_time - last_pos['time']
            if age_since_last < self.config.min_age_seconds:
                return False, f"Position too young ({age_since_last:.1f}s < {self.config.min_age_seconds}s)"

            if isinstance(last_pos, dict):
                last_price = float(last_pos.get('price_open', last_pos.get('price', 0.0)))
                last_type = last_pos.get('type', 0)
            else:
                last_price = float(getattr(last_pos, 'price_open', getattr(last_pos, 'price', 0.0)))
                last_type = getattr(last_pos, 'type', 0)

            current_price = tick['bid'] if last_type == 0 else tick['ask']
            dist = abs(current_price - last_price)
            pip_multiplier = 100 if "XAU" in symbol or "GOLD" in symbol else 10000
            atr_price = atr_val if (atr_val and atr_val > 0) else 2.0
            dynamic_min_dist = atr_price * 0.25
            min_floor = 2.0 if "XAU" in symbol or "GOLD" in symbol else 0.0020
            final_min_dist = max(min_floor, dynamic_min_dist)
            
            if dist < final_min_dist:
                 return False, f"Distance too small ({dist:.2f} < {final_min_dist:.2f})"

            dynamic_cooldown, _ = self._calculate_adaptive_factors(float(atr_val) if atr_val else 0.0)
            time_since_hedge = time.time() - state.last_hedge_time
            if time_since_hedge < dynamic_cooldown:
                return False, f"Hedge cooldown active ({time_since_hedge:.1f}s < {dynamic_cooldown:.1f}s)"

            return True, "Conditions met for hedging"

    def calculate_zone_parameters(self, positions: List[Dict], tick: Dict, point: float,
                                ppo_guardian, atr_val: float = 0.0010) -> Tuple[float, float]:
        symbol = positions[0]['symbol'] if positions else ""
        pip_multiplier = 100 if "XAU" in symbol or "GOLD" in symbol or "JPY" in symbol else 10000
        num_positions = len(positions)
        zone_pips = 20.0 
        
        if num_positions == 2:
            zone_pips = 30.0
        elif num_positions >= 3:
            zone_pips = 50.0
            
        _, zone_mult = self._calculate_adaptive_factors(float(atr_val) if atr_val else 0.0)
        effective_zone = min(zone_pips * zone_mult, AdaptiveRisk.ZONE_MAX)
        if zone_mult > 1.1:
            zone_pips = effective_zone
        
        atr_pips = atr_val * pip_multiplier
        if atr_pips > 50.0:
             zone_pips = max(zone_pips, atr_pips * 0.8)

        slippage_pad_pips = 0.0
        if atr_pips > 20.0:
             slippage_pad_pips = atr_pips * 0.10

        tp_pips = zone_pips + slippage_pad_pips
        zone_width_points = zone_pips * point
        tp_width_points = tp_pips * point
        return zone_width_points, tp_width_points

    def execute_zone_recovery(self, broker, symbol: str, positions: List[Dict],
                            tick: Dict, point: float, shield, ppo_guardian,
                            position_manager, strict_entry: bool, oracle=None, atr_val: float = None,
                            volatility_ratio: float = 1.0, rsi_value: float = None, trap_hunter=None, pressure_metrics=None,
                            max_hedges_override: int = None, hybrid_intelligence=None) -> bool:
        
        positions = normalize_positions(positions)
        last_pending = self._pending_hedges.get(symbol, 0)
        if time.time() - last_pending < 10.0:
             return False

        self._pending_hedges[symbol] = time.time()

        if strict_entry and (rsi_value is None or atr_val is None or float(atr_val) <= 0):
            self._pending_hedges.pop(symbol, None)
            return False

        enable_freshness = str(os.getenv("AETHER_ENABLE_FRESHNESS_GATE", "1")).strip().lower() in ("1", "true", "yes", "on")
        if enable_freshness:
            now = time.time()
            tick_ts = float(tick.get('time', 0.0) or 0.0)
            should_recalc = (self._time_offset is None or (now - self._last_offset_calc) > 3600)
            
            if should_recalc and tick_ts > 0:
                raw_diff = now - tick_ts
                self._time_offset = raw_diff if abs(raw_diff) > 600 else 0.0
                self._last_offset_calc = now
            
            offset = self._time_offset if self._time_offset is not None else 0.0
            tick_age = abs(now - (tick_ts + offset)) if tick_ts > 0 else float(tick.get('tick_age_s', float('inf')))
            max_tick_age = float(os.getenv("AETHER_FRESH_TICK_MAX_AGE_S", "10.0"))

            if max_tick_age > 0 and tick_age > max_tick_age:
                self._pending_hedges.pop(symbol, None)
                return False

        try:
            if not broker.is_trade_allowed():
                self._pending_hedges.pop(symbol, None)
                return False
        except Exception:
            self._pending_hedges.pop(symbol, None)
            return False
        
        from src.utils.hedge_coordinator import get_hedge_coordinator
        coordinator = get_hedge_coordinator()
        first_pos = sorted(positions, key=lambda p: p['time'])[0]
        bucket_id = f"{symbol}_{first_pos['ticket']}"
        can_hedge_bucket, _ = coordinator.can_hedge_bucket(bucket_id)
        if not can_hedge_bucket:
            self._pending_hedges.pop(symbol, None)
            return False
        
        can_hedge, reason = self.validate_hedge_conditions(broker, symbol, positions, tick, point, atr_val=atr_val, max_hedges_override=max_hedges_override)
        if not can_hedge:
            self._pending_hedges.pop(symbol, None)
            return False

        state = self._get_hedge_state(symbol)
        try:
            sorted_pos = sorted(positions, key=lambda p: p['time'])
            last_pos = sorted_pos[-1]
            first_ticket = first_pos['ticket']
            trade_metadata = position_manager.active_learning_trades.get(first_ticket, {})
            hedge_plan = trade_metadata.get('hedge_plan', {})
            entry_atr = trade_metadata.get('entry_atr', None)
            
            if atr_val is not None and float(atr_val) > 0:
                current_atr = float(atr_val)
            elif entry_atr is not None and float(entry_atr) > 0:
                current_atr = float(entry_atr)
            else:
                self._pending_hedges.pop(symbol, None)
                return False

            saved_hedge_level = trade_metadata.get('current_hedge_level', 0)
            hedge_level = saved_hedge_level if saved_hedge_level != 0 else max(0, len(positions) - 1)
            
            use_stored_plan = False
            stored_trigger_price = 0.0
            if hedge_plan:
                plan_key_price = f"hedge{hedge_level}_trigger_price"
                if plan_key_price in hedge_plan:
                    stored_trigger_price = hedge_plan[plan_key_price]
                    use_stored_plan = True

            zone_width_points, tp_width_points = self.calculate_zone_parameters(positions, tick, point, ppo_guardian, atr_val=atr_val)

            if pressure_metrics:
                vpin = pressure_metrics.get('chemistry', {}).get('vpin', 0.0)
                if vpin > 0.6:
                    self._pending_hedges.pop(symbol, None)
                    return False
                reynolds = pressure_metrics.get('physics', {}).get('reynolds_number', 0.0)
                if reynolds > 2000:
                    zone_width_points *= 1.25

            scale_factor = 1.0
            with state.lock:
                if volatility_ratio >= 2.5:
                    state.high_vol_mode = True
                    log_scale = 1.0 + (math.log(max(volatility_ratio, 2.0) / 2.0) * 0.5)
                    state.volatility_scale = max(1.0, min(log_scale, 1.25))
                elif volatility_ratio <= 2.0:
                    state.high_vol_mode = False
                    state.volatility_scale = 1.0
                scale_factor = state.volatility_scale

            if scale_factor > 1.0:
                zone_width_points *= scale_factor

            if first_pos['type'] == 0:
                upper_level = first_pos['price_open']
                lower_level = first_pos['price_open'] - zone_width_points
            else:
                lower_level = first_pos['price_open']
                upper_level = first_pos['price_open'] + zone_width_points
            
            if use_stored_plan and stored_trigger_price > 0:
                if first_pos['type'] == 0:
                    if hedge_level % 2 != 0: lower_level = stored_trigger_price
                    else: upper_level = stored_trigger_price
                else:
                    if hedge_level % 2 != 0: upper_level = stored_trigger_price
                    else: lower_level = stored_trigger_price

            precision = int(-math.log10(point)) if point > 0 else 2
            epsilon = point * 0.1
            next_action = None
            target_price = 0.0
            
            if tick['bid'] <= lower_level + epsilon:
                if first_pos['type'] == 0 or (first_pos['type'] == 1 and len(positions) % 2 == 0):
                    next_action = "SELL"
                    target_price = tick['bid']
            elif tick['ask'] >= upper_level - epsilon:
                if first_pos['type'] == 1 or (first_pos['type'] == 0 and len(positions) % 2 == 0):
                    next_action = "BUY"
                    target_price = tick['ask']

            if not next_action:
                self._pending_hedges.pop(symbol, None)
                return False

            # Elastic Defense check
            new_hedge_type = 0 if next_action == "BUY" else 1
            elastic_wait = False
            if new_hedge_type == 0 and rsi_value is not None and rsi_value < 30: elastic_wait = True
            elif new_hedge_type == 1 and rsi_value is not None and rsi_value > 70: elastic_wait = True
            
            if elastic_wait:
                self._pending_hedges.pop(symbol, None)
                return False

            if (next_action == "BUY" and last_pos['type'] == 0) or (next_action == "SELL" and last_pos['type'] == 1):
                self._pending_hedges.pop(symbol, None)
                return False

            # Hybrid Intelligence sizing
            from src.ai_core.hybrid_hedge_intelligence import HybridHedgeIntelligence
            hybrid_intel = hybrid_intelligence if hybrid_intelligence else HybridHedgeIntelligence()
            hedge_market_data = {'atr': atr_val, 'rsi': rsi_value, 'trend_strength': 0.0, 'symbol': symbol, 'current_price': target_price, 'volatility_ratio': volatility_ratio, 'pressure_metrics': pressure_metrics}
            drawdown_pct = 0.0
            try:
                acc_info = broker.get_account_info()
                if acc_info: drawdown_pct = max(0.0, (acc_info.get('balance', 1.0) - acc_info.get('equity', 1.0)) / acc_info.get('balance', 1.0))
            except Exception: pass

            hedge_decision = hybrid_intel.analyze_hedge_decision(positions=positions, current_price=target_price, market_data=hedge_market_data, oracle=oracle, zone_breach_pips=0.0, drawdown_pct=drawdown_pct)
            if not hedge_decision.should_hedge:
                self._pending_hedges.pop(symbol, None)
                return False
            
            total_required_hedge = hedge_decision.hedge_size
            current_friendly_volume = sum(p.get('volume', 0.0) for p in positions if p.get('type') == (0 if next_action == "BUY" else 1))
            hedge_lot = total_required_hedge - current_friendly_volume
            
            if hedge_lot < 0.01:
                self._pending_hedges.pop(symbol, None)
                return True

            # Execution
            result = broker.execute_order(
                action="OPEN", symbol=symbol, order_type=next_action, price=target_price,
                volume=hedge_lot, sl=0.0, tp=0.0, strict_entry=bool(strict_entry),
                trace_reason="OPEN_ZONE_RECOVERY", comment=f"HDG_Z{int(zone_width_points/point)}"[:31]
            )
            
            if result and result.get('ticket'):
                coordinator.record_hedge(bucket_id, next_action, hedge_lot, target_price)
                new_hedge_level = hedge_level + 1
                trade_metadata['current_hedge_level'] = new_hedge_level
                position_manager.active_learning_trades[first_ticket] = trade_metadata
                state.last_hedge_time = time.time()
                state.active_hedges += 1
                position_manager.add_position_to_bucket(bucket_id, result['ticket'])
                return True
            
            self._pending_hedges.pop(symbol, None)
            return False

        except Exception as e:
            logger.error(f"Zone recovery error: {e}")
            self._pending_hedges.pop(symbol, None)
            return False

    def get_risk_status(self, symbol: str) -> Dict[str, Any]:
        state = self._get_hedge_state(symbol)
        with state.lock:
            return {
                "symbol": symbol,
                "active_hedges": state.active_hedges,
                "last_hedge_time": state.last_hedge_time,
                "time_since_last_hedge": time.time() - state.last_hedge_time,
                "zone_width_pips": state.zone_width_points,
                "tp_width_pips": state.tp_width_points
            }

    def reset_symbol_state(self, symbol: str) -> None:
        with self._lock:
            if symbol in self._hedge_states:
                del self._hedge_states[symbol]
                logger.info(f"Reset risk state for {symbol}")

    def get_emergency_status(self, total_positions: int) -> Tuple[bool, str]:
        if total_positions >= self._global_position_cap:
            return True, f"Emergency: {total_positions} positions >= cap of {self._global_position_cap}"
        return False, "Normal operations"