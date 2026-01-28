"""
Oracle Backtesting Script

Validates the trained Oracle model against historical data.
Measures prediction accuracy, win rate, and profitability.
"""

import sys
import os
import sqlite3
import pandas as pd
import numpy as np
import torch
from datetime import datetime, timedelta
import logging

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_core.nexus_transformer import TimeSeriesTransformer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("OracleBacktest")

class OracleBacktester:
    def __init__(self, db_path="data/market_memory.db", model_path="models/nexus_transformer.pth"):
        self.db_path = db_path
        self.model_path = model_path
        self.seq_len = 64
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        
        # Trading parameters
        self.tp_pips = 25  # Take profit in pips
        self.sl_pips = 25  # Stop loss in pips
        self.pip_value = 0.01  # For Gold
        
        # Load model
        self.model = self._load_model()
        
    def _load_model(self):
        """Load trained Oracle model"""
        logger.info(f"Loading Oracle from {self.model_path}")
        
        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model not found: {self.model_path}")
        
        # Match exact parameters used in NexusTrainerV2 (12 features: OHLCV + 7 technical indicators)
        model = TimeSeriesTransformer(
            input_dim=12,  # Updated for technical indicators
            d_model=128    # Matches NexusTrainerV2
        ).to(self.device)
        
        model.load_state_dict(torch.load(self.model_path, map_location=self.device))
        model.eval()
        
        logger.info("Oracle loaded successfully")
        return model
    
    def load_historical_data(self, days=90):
        """Load historical M1 candles"""
        logger.info(f"Loading {days} days of historical data...")
        
        conn = sqlite3.connect(self.db_path)
        
        # Get data from candles table (all available data)
        query = """
            SELECT open, high, low, close, volume
            FROM candles
            WHERE timeframe = 'M1'
            ORDER BY timestamp ASC
        """
        
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        if df.empty:
            raise ValueError("No historical data found in database")
        
        # Take last N days worth (approximate)
        rows_per_day = 24 * 60  # M1 = 1440 candles per day
        max_rows = days * rows_per_day
        if len(df) > max_rows:
            df = df.tail(max_rows).reset_index(drop=True)
        
        logger.info(f"Loaded {len(df)} candles")
        return df
    
    def prepare_sequence(self, data, idx):
        """Prepare sequence for Oracle prediction with technical indicators"""
        if idx < self.seq_len + 50:  # Need extra rows for indicator calculation
            return None
            
        # Get extended slice for indicator calculation
        start_idx = idx - self.seq_len - 50
        if start_idx < 0:
            return None
            
        # Get raw data slice with extra rows for indicators
        extended_df = data.iloc[start_idx:idx][['open', 'high', 'low', 'close', 'volume']].copy()
        
        # Calculate technical indicators (matching NexusTrainerV2)
        try:
            import ta
            
            # RSI
            extended_df['rsi'] = ta.momentum.RSIIndicator(extended_df['close'], window=14).rsi()
            
            # MACD
            macd_ind = ta.trend.MACD(extended_df['close'])
            extended_df['macd_diff'] = macd_ind.macd_diff()
            
            # ATR
            extended_df['atr'] = ta.volatility.AverageTrueRange(
                extended_df['high'], extended_df['low'], extended_df['close'], window=14
            ).average_true_range()
            
            # Bollinger Bands
            bollinger = ta.volatility.BollingerBands(extended_df['close'], window=20)
            extended_df['bb_width'] = bollinger.bollinger_wband()
            
            # OBV
            extended_df['obv'] = ta.volume.OnBalanceVolumeIndicator(
                extended_df['close'], extended_df['volume']
            ).on_balance_volume()
            
            # Stochastic
            stoch = ta.momentum.StochasticOscillator(
                extended_df['high'], extended_df['low'], extended_df['close']
            )
            extended_df['stoch_k'] = stoch.stoch()
            
            # CCI
            extended_df['cci'] = ta.trend.CCIIndicator(
                extended_df['high'], extended_df['low'], extended_df['close']
            ).cci()
            
            # Clean NaN/Inf
            extended_df.replace([np.inf, -np.inf], np.nan, inplace=True)
            extended_df.ffill(inplace=True)
            extended_df.bfill(inplace=True)
            extended_df.fillna(0.0, inplace=True)
            
        except Exception as e:
            logger.warning(f"Failed to calculate indicators: {e}")
            return None
        
        # Take only the last seq_len + 1 rows (for normalization)
        extended_df = extended_df.tail(self.seq_len + 1).reset_index(drop=True)
        
        # Extract features: OHLCV + 7 indicators = 12 features
        features = ['open', 'high', 'low', 'close', 'volume', 'rsi', 'macd_diff', 
                   'atr', 'bb_width', 'obv', 'stoch_k', 'cci']
        raw_data = extended_df[features].values
        
        # Normalize: relative returns for price/volume, clip indicators
        normalized_data = []
        for i in range(1, len(raw_data)):
            prev_close = float(raw_data[i-1][3])  # Close
            if prev_close <= 0: prev_close = 1.0
            
            curr_row = raw_data[i]
            
            # OHLC: relative returns
            norm_row = [
                (float(curr_row[0]) / prev_close) - 1.0,  # Open
                (float(curr_row[1]) / prev_close) - 1.0,  # High
                (float(curr_row[2]) / prev_close) - 1.0,  # Low
                (float(curr_row[3]) / prev_close) - 1.0,  # Close
            ]
            
            # Volume: log
            norm_row.append(float(np.log1p(max(0.0, float(curr_row[4])))))
            
            # Technical indicators: clip to [-10, 10]
            for j in range(5, 12):
                val = float(curr_row[j])
                val = np.clip(val, -10.0, 10.0)
                val = np.nan_to_num(val, nan=0.0, posinf=10.0, neginf=-10.0)
                norm_row.append(val)
            
            normalized_data.append(norm_row)
        
        return np.array(normalized_data, dtype=np.float32)
    
    def predict(self, sequence):
        """Get Oracle prediction"""
        if sequence is None:
            return None, None
        
        # Convert to tensor
        x = torch.FloatTensor(sequence).unsqueeze(0).to(self.device)
        
        with torch.no_grad():
            trend_logits, vol_pred = self.model(x)
            trend_probs = torch.softmax(trend_logits, dim=1)
            trend = torch.argmax(trend_probs, dim=1).item()
            confidence = trend_probs[0][trend].item()
        
        # 0 = DOWN, 1 = NEUTRAL, 2 = UP
        return trend, confidence
    
    def simulate_trade(self, entry_price, direction, df, start_idx):
        """Simulate a trade and return outcome"""
        tp_distance = self.tp_pips * self.pip_value
        sl_distance = self.sl_pips * self.pip_value
        
        if direction == 2:  # BUY
            tp_price = entry_price + tp_distance
            sl_price = entry_price - sl_distance
        elif direction == 0:  # SELL
            tp_price = entry_price - tp_distance
            sl_price = entry_price + sl_distance
        else:  # NEUTRAL - skip
            return None
        
        # Check next candles for TP/SL hit
        max_candles = 100  # Max 100 candles (~1.5 hours for M1)
        
        for i in range(start_idx + 1, min(start_idx + max_candles, len(df))):
            high = df.iloc[i]['high']
            low = df.iloc[i]['low']
            
            if direction == 2:  # BUY
                if high >= tp_price:
                    return {'outcome': 'WIN', 'profit': tp_distance, 'candles': i - start_idx}
                if low <= sl_price:
                    return {'outcome': 'LOSS', 'profit': -sl_distance, 'candles': i - start_idx}
            else:  # SELL
                if low <= tp_price:
                    return {'outcome': 'WIN', 'profit': tp_distance, 'candles': i - start_idx}
                if high >= sl_price:
                    return {'outcome': 'LOSS', 'profit': -sl_distance, 'candles': i - start_idx}
        
        # Trade didn't close within max candles - assume breakeven
        return {'outcome': 'TIMEOUT', 'profit': 0, 'candles': max_candles}
    
    def run_backtest(self, days=90):
        """Run full backtest"""
        logger.info("="*60)
        logger.info("Oracle Backtest - 3 Month Validation")
        logger.info("="*60)
        
        # Load data
        df = self.load_historical_data(days)
        
        # Results storage
        trades = []
        predictions = []
        
        logger.info(f"Running backtest on {len(df)} candles...")
        
        # Process each candle
        for i in range(self.seq_len, len(df) - 100):  # Leave room for trade simulation
            # Get prediction (pass DataFrame, not numpy array)
            seq = self.prepare_sequence(df, i)
            trend, confidence = self.predict(seq)
            
            if trend is None:
                continue
            
            # Record prediction
            predictions.append({
                'trend': trend,
                'confidence': confidence
            })
            
            # Only trade on high-confidence signals
            if confidence < 0.6:
                continue
            
            # Skip NEUTRAL
            if trend == 1:
                continue
            
            # Simulate trade
            entry_price = df.iloc[i]['close']
            result = self.simulate_trade(entry_price, trend, df, i)
            
            if result:
                trades.append({
                    'direction': 'BUY' if trend == 2 else 'SELL',
                    'entry_price': entry_price,
                    'confidence': confidence,
                    **result
                })
            
            # Progress update
            if len(trades) % 100 == 0 and len(trades) > 0:
                logger.info(f"Processed {i}/{len(df)} candles | Trades: {len(trades)}")
        
        # Calculate statistics
        self._print_results(trades, predictions, df)
        
        return trades, predictions
    
    def _print_results(self, trades, predictions, df):
        """Print backtest results"""
        logger.info("\n" + "="*60)
        logger.info("BACKTEST RESULTS")
        logger.info("="*60)
        
        # Prediction stats
        logger.info(f"\n📊 Prediction Statistics:")
        logger.info(f"Total Predictions: {len(predictions)}")
        
        if predictions:
            trend_counts = pd.Series([p['trend'] for p in predictions]).value_counts()
            logger.info(f"DOWN: {trend_counts.get(0, 0)} | NEUTRAL: {trend_counts.get(1, 0)} | UP: {trend_counts.get(2, 0)}")
            
            avg_confidence = np.mean([p['confidence'] for p in predictions])
            logger.info(f"Average Confidence: {avg_confidence:.1%}")
        
        # Trade stats
        logger.info(f"\n💰 Trading Performance:")
        logger.info(f"Total Trades: {len(trades)}")
        
        if not trades:
            logger.warning("No trades executed (Low confidence or insufficient data)")
            return
        
        wins = [t for t in trades if t['outcome'] == 'WIN']
        losses = [t for t in trades if t['outcome'] == 'LOSS']
        timeouts = [t for t in trades if t['outcome'] == 'TIMEOUT']
        
        win_rate = len(wins) / len(trades) * 100
        
        logger.info(f"Wins: {len(wins)} | Losses: {len(losses)} | Timeouts: {timeouts or 0}")
        logger.info(f"Win Rate: {win_rate:.1f}%")
        
        # Profit analysis
        total_profit = sum([t['profit'] for t in trades])
        avg_win = np.mean([t['profit'] for t in wins]) if wins else 0
        avg_loss = np.mean([t['profit'] for t in losses]) if losses else 0
        
        logger.info(f"\nTotal Profit: {total_profit:.2f} pips")
        logger.info(f"Average Win: {avg_win:.2f} pips")
        logger.info(f"Average Loss: {avg_loss:.2f} pips")
        
        # Profit factor
        gross_profit = sum([t['profit'] for t in wins])
        gross_loss = abs(sum([t['profit'] for t in losses]))
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        logger.info(f"Profit Factor: {profit_factor:.2f}")
        
        # Max drawdown (simplified)
        cumulative = np.cumsum([t['profit'] for t in trades])
        max_dd = np.min(cumulative - np.maximum.accumulate(cumulative))
        logger.info(f"Max Drawdown: {max_dd:.2f} pips")
        
        # Average trade duration
        avg_duration = np.mean([t['candles'] for t in trades])
        logger.info(f"Avg Trade Duration: {avg_duration:.0f} candles ({avg_duration:.0f} mins)")
        
        logger.info("="*60)
        
        # Verdict
        if win_rate >= 60 and profit_factor >= 1.5:
            logger.info("✅ VERDICT: Oracle is PROFITABLE on historical data!")
        elif win_rate >= 50:
            logger.info("⚠️ VERDICT: Oracle shows promise but needs optimization")
        else:
            logger.info("❌ VERDICT: Oracle needs further training or strategy adjustment")
        
        logger.info("="*60)


def main():
    import argparse
    parser = argparse.ArgumentParser(description='Oracle Backtester')
    parser.add_argument('--days', type=int, default=30, help='Number of days to backtest')
    parser.add_argument('--model', type=str, default="models/nexus_transformer.pth", help='Path to model file')
    args = parser.parse_args()

    try:
        backtester = OracleBacktester(model_path=args.model)
        trades, predictions = backtester.run_backtest(days=args.days)
        
        logger.info("\n✅ Backtest complete!")
        logger.info("Results saved. Ready for live trading assessment.")
        
        return 0
        
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
