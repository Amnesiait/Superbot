import time
import logging
from collections import deque

# [SUPERBOT INTEGRATION] Importar Nucleo Rust de Baja Latencia
try:
    import aether_fast_core
    RUST_AVAILABLE = True
    # [FIX] Eliminado emoji y acento para compatibilidad total con Windows Logs
    print(">>> [INIT] NUCLEO RUST CARGADO: Microestructura HFT Activada")
except ImportError:
    RUST_AVAILABLE = False
    print(">>> [INIT] ADVERTENCIA: Nucleo Rust no encontrado. Usando modo lento (Python).")

logger = logging.getLogger("TickPressure")

class TickPressureAnalyzer:
    """
    "Holographic" Market View: Simulates Order Flow (Level 2) using Tick Velocity.
    Detects Institutional Aggression vs Retail Noise.
    
    [SUPERBOT EVOLUTION] Enhanced with Rust Core for VPIN calculation.
    """
    def __init__(self, window_seconds=5):
        self.window_seconds = window_seconds
        self.ticks = deque() # Stores (price, time)
        
        # ENHANCEMENT 2: Order Flow Imbalance Tracking
        self.buy_volume_buffer = deque(maxlen=100)
        self.sell_volume_buffer = deque(maxlen=100)
        self.max_buffer_size = 100
        
        # [SUPERBOT] Inicializar motor Rust si está disponible
        self.rust_engine = None
        
        # Corrección de Scope: Solo leemos la variable global, no intentamos modificarla
        if RUST_AVAILABLE:
            try:
                # Inicializar con bucket_size=1.0 (no usado) y buffer=100
                self.rust_engine = aether_fast_core.MicrostructureAnalyzer(1.0, 100)
            except Exception as e:
                logger.error(f"Error inicializando motor Rust: {e}")
                self.rust_engine = None # Fallback explícito a Python

    def add_tick(self, tick):
        """
        Add a new tick to the analyzer.
        Args:
            tick: Dictionary containing 'bid', 'ask', 'time'
        """
        if not tick:
            return
            
        # Use Bid price for pressure analysis.
        price = tick.get('bid', 0.0)
        current_time = time.time()
        
        if price > 0:
            self.ticks.append((price, current_time))
            self._cleanup(current_time)
            
            # [SUPERBOT] Si tenemos Rust, alimentamos el motor también aquí
            # para mantener el estado sincronizado

    def _cleanup(self, current_time):
        while self.ticks and (current_time - self.ticks[0][1] > self.window_seconds):
            self.ticks.popleft()
            
    def get_pressure_metrics(self, point_value=0.01):
        """
        Calculates Tick Pressure (Aggression).
        Returns: Dictionary with pressure metrics
        """
        if len(self.ticks) < 5:
            return {
                'pressure_score': 0.0,
                'intensity': 'LOW',
                'dominance': 'NEUTRAL',
                'state': 'INSUFFICIENT_DATA',
                'velocity': 0.0
            }
            
        start_price = self.ticks[0][0]
        end_price = self.ticks[-1][0]
        price_change = end_price - start_price
        
        tick_count = len(self.ticks)
        duration = self.ticks[-1][1] - self.ticks[0][1]
        if duration <= 0: duration = 0.001
        
        # Velocity = Ticks per Second (Speed of orders)
        velocity = tick_count / duration
        
        # Normalized Price Change (in Points)
        price_delta_points = price_change / point_value
        
        # Pressure = Price Delta * Velocity
        pressure = price_delta_points * velocity
        
        state = "NEUTRAL"
        intensity = "NORMAL"
        dominance = "NEUTRAL"
        
        # Thresholds (Tuned for Gold)
        if pressure > 50.0: 
            state = "INSTITUTIONAL_BUY"
            intensity = "HIGH"
            dominance = "BUY"
        elif pressure > 15.0: 
            state = "STRONG_BUY"
            intensity = "MEDIUM"
            dominance = "BUY"
        elif pressure < -50.0: 
            state = "INSTITUTIONAL_SELL"
            intensity = "HIGH"
            dominance = "SELL"
        elif pressure < -15.0: 
            state = "STRONG_SELL"
            intensity = "MEDIUM"
            dominance = "SELL"
        elif velocity > 10.0 and abs(price_delta_points) < 2.0: 
            state = "ABSORPTION_FIGHT" # High volume, no movement (Trap)
            intensity = "HIGH"
            dominance = "NEUTRAL"
        elif velocity < 1.0:
            state = "LOW_LIQUIDITY"
            intensity = "LOW"
            
        return {
            'pressure_score': pressure,
            'intensity': intensity,
            'dominance': dominance,
            'state': state,
            'velocity': velocity
        }
    
    def analyze_order_flow(self, tick):
        """
        Analyze buy vs sell volume imbalance from tick data.
        """
        if not tick:
            return {
                'order_flow_imbalance': 0.0,
                'buy_pressure': 0.5,
                'sell_pressure': 0.5
            }
        
        try:
            last_price = tick.get('last', tick.get('bid', 0))
            bid = tick.get('bid', 0)
            ask = tick.get('ask', 0)
            volume = float(tick.get('volume', 1)) # Ensure float
            
            mid_price = (bid + ask) / 2
            
            if not hasattr(self, '_prev_mid'):
                self._prev_mid = mid_price
                
            # [FIX] Nueva línea (Si hay precio 'last', es un trade real)
            is_quote_update = abs(last_price) < 1e-9
            
            # Determine Aggressor Side (0=Buy, 1=Sell, 2=Neutral) for Rust
            side_rust = 2 
            
            if not is_quote_update:
                if last_price >= ask:
                    self.buy_volume_buffer.append(volume)
                    side_rust = 0 # BUY
                elif last_price <= bid:
                    self.sell_volume_buffer.append(volume)
                    side_rust = 1 # SELL
                else:
                    self.buy_volume_buffer.append(volume / 2)
                    self.sell_volume_buffer.append(volume / 2)
            else:
                # Quote Update Logic
                if mid_price > self._prev_mid:
                    self.buy_volume_buffer.append(volume)
                    side_rust = 0 # BUY
                elif mid_price < self._prev_mid:
                    self.sell_volume_buffer.append(volume)
                    side_rust = 1 # SELL
                else:
                    self.buy_volume_buffer.append(volume / 2)
                    self.sell_volume_buffer.append(volume / 2)
            
            self._prev_mid = mid_price

            # [SUPERBOT] ALIMENTAR MOTOR RUST (Si existe)
            if self.rust_engine:
                self.rust_engine.calculate_vpin(0.0, volume, side_rust)
            
            # Python Legacy Logic (Keep for fallback/display)
            buy_vol = sum(self.buy_volume_buffer) if self.buy_volume_buffer else 0
            sell_vol = sum(self.sell_volume_buffer) if self.sell_volume_buffer else 0
            total_vol = buy_vol + sell_vol
            
            if total_vol > 0:
                imbalance = (buy_vol - sell_vol) / total_vol
                buy_pressure = buy_vol / total_vol
                sell_pressure = sell_vol / total_vol
            else:
                imbalance = 0.0
                buy_pressure = 0.5
                sell_pressure = 0.5
            
            return {
                'order_flow_imbalance': float(imbalance),
                'buy_pressure': float(buy_pressure),
                'sell_pressure': float(sell_pressure),
                'buy_volume': float(buy_vol),
                'sell_volume': float(sell_vol)
            }
            
        except Exception as e:
            return {
                'order_flow_imbalance': 0.0,
                'buy_pressure': 0.5,
                'sell_pressure': 0.5
            }

    def calculate_vpin(self) -> float:
        """
        [THE CHEMIST] Calculate Volume-Synchronized Probability of Informed Trading.
        Fallback: |V_buy - V_sell| / Total_Volume (Python)
        """
        if self.rust_engine:
            pass

        buy_vol = sum(self.buy_volume_buffer) if self.buy_volume_buffer else 0
        sell_vol = sum(self.sell_volume_buffer) if self.sell_volume_buffer else 0
        total_vol = buy_vol + sell_vol
        
        if total_vol <= 0:
            return 0.0
            
        buy_samples = len(self.buy_volume_buffer)
        sell_samples = len(self.sell_volume_buffer)
        
        if (buy_samples + sell_samples) < 15:
            return 0.0
            
        return abs(buy_vol - sell_vol) / total_vol

    def calculate_reynolds_number(self, spread_points: float, point_value: float = 0.01) -> float:
        """
        [THE PHYSICIST] Calculate Reynolds Number (Re) for Phase Transition detection.
        Re = (Volume * Volatility) / Viscosity(Spread)
        """
        if spread_points <= 0 or not self.ticks:
            return 0.0
            
        duration = self.ticks[-1][1] - self.ticks[0][1]
        if duration <= 0: duration = 0.001
        velocity = len(self.ticks) / duration
        
        prices = [p[0] for p in self.ticks]
        if len(prices) > 2:
            import numpy as np
            volatility = np.std(prices) / point_value
        else:
            volatility = 0.0
            
        viscosity = spread_points
        re = (velocity * volatility * 100) / viscosity
        
        return float(re)

    def calculate_navier_stokes_pressure(self, order_flow_imbalance: float, velocity: float) -> float:
        """
        [THE PHYSICIST] Calculate Net Force (Pressure Gradient).
        Approximation: Force = Imbalance * Velocity
        """
        return order_flow_imbalance * velocity

    def calculate_reaction_rate(self) -> float:
        """
        [THE CHEMIST] Calculate Liquidity Consumption Rate.
        """
        if len(self.ticks) < 2: 
            return 0.0
            
        duration = self.ticks[-1][1] - self.ticks[0][1]
        if duration <= 0: return 0.0
        
        return len(self.ticks) / duration

    def get_combined_analysis(self, tick, point_value=0.01):
        """
        Get all Physics & Chemistry metrics in one call.
        """
        pressure = self.get_pressure_metrics(point_value)
        order_flow = self.analyze_order_flow(tick)
        
        ask = tick.get('ask', 0)
        bid = tick.get('bid', 0)
        spread = (ask - bid) if (ask > 0 and bid > 0) else 0.0001
        spread_points = spread / point_value
        
        re = self.calculate_reynolds_number(spread_points, point_value)
        ns_pressure = self.calculate_navier_stokes_pressure(
            order_flow['order_flow_imbalance'], 
            pressure['velocity']
        )
        
        vpin = self.calculate_vpin()
        reaction = self.calculate_reaction_rate()
        
        combined = {
            **pressure,
            **order_flow,
            'physics': {
                'reynolds_number': re,
                'navier_stokes_force': ns_pressure,
                'regime': 'TURBULENT' if re > 500 else 'LAMINAR'
            },
            'chemistry': {
                'vpin': vpin,
                'reaction_rate': reaction,
                'is_toxic': vpin > 0.4
            }
        }
        
        return combined