"""
Historical Data Collection Script for Oracle Training

This script collects real market data from MT5 to replace the synthetic
sine wave training data. It fetches M1, M5, M15, and H1 timeframes.

Usage:
    python scripts/collect_training_data.py --days 90 --symbol XAUUSD
"""

import MetaTrader5 as mt5
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import logging
import argparse
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("DataCollector")


def initialize_mt5():
    """Initialize MT5 connection"""
    if not mt5.initialize():
        logger.error(f"MT5 initialization failed: {mt5.last_error()}")
        return False
    
    logger.info(f"MT5 initialized. Terminal: {mt5.terminal_info().name}")
    logger.info(f"Account: {mt5.account_info().login}")
    return True


def collect_timeframe_data(symbol, timeframe, start_date, end_date):
    """Collect data for a specific timeframe"""
    logger.info(f"Collecting {timeframe} data for {symbol}...")
    
    # Map string timeframe to MT5 constant
    tf_map = {
        "M1": mt5.TIMEFRAME_M1,
        "M5": mt5.TIMEFRAME_M5,
        "M15": mt5.TIMEFRAME_M15,
        "H1": mt5.TIMEFRAME_H1,
        "H4": mt5.TIMEFRAME_H4,
        "D1": mt5.TIMEFRAME_D1,
    }
    
    mt5_timeframe = tf_map.get(timeframe)
    if not mt5_timeframe:
        logger.error(f"Invalid timeframe: {timeframe}")
        return None
    
    # Fetch data
    rates = mt5.copy_rates_range(symbol, mt5_timeframe, start_date, end_date)
    
    if rates is None or len(rates) == 0:
        logger.error(f"No data received for {timeframe}: {mt5.last_error()}")
        return None
    
    # Convert to DataFrame
    df = pd.DataFrame(rates)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df['timeframe'] = timeframe
    df['symbol'] = symbol
    
    logger.info(f"Collected {len(df)} {timeframe} candles")
    return df


def calculate_technical_indicators(df):
    """Add technical indicators to candles"""
    logger.info("Calculating technical indicators...")
    
    # RSI (14)
    def calc_rsi(prices, period=14):
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))
    
    df['rsi_14'] = calc_rsi(df['close'])
    
    # EMAs
    df['ema_20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['ema_50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ema_200'] = df['close'].ewm(span=200, adjust=False).mean()
    
    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # ATR
    high_low = df['high'] - df['low']
    high_close = (df['high'] - df['close'].shift()).abs()
    low_close = (df['low'] - df['close'].shift()).abs()
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    df['atr'] = true_range.rolling(window=14).mean()
    
    # Volume MA
    df['volume_ma'] = df['tick_volume'].rolling(window=20).mean()
    
    logger.info("Technical indicators calculated")
    return df


def store_in_database(df, db_path, table_name):
    """Store DataFrame in SQLite database"""
    logger.info(f"Storing data in {db_path} table: {table_name}")
    
    # Create database directory if it doesn't exist
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    
    # Connect to database
    conn = sqlite3.connect(db_path)
    
    # Store data
    df.to_sql(table_name, conn, if_exists='replace', index=False)
    
    # Create indexes for faster queries
    cursor = conn.cursor()
    try:
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_time ON {table_name}(time)")
        cursor.execute(f"CREATE INDEX IF NOT EXISTS idx_{table_name}_symbol ON {table_name}(symbol)")
        conn.commit()
    except Exception as e:
        logger.warning(f"Index creation warning: {e}")
    
    conn.close()
    logger.info(f"Stored {len(df)} rows in {table_name}")


def main():
    parser = argparse.ArgumentParser(description='Collect historical market data for Oracle training')
    parser.add_argument('--days', type=int, default=90, help='Number of days to collect (default: 90)')
    parser.add_argument('--symbol', type=str, default='XAUUSD', help='Trading symbol (default: XAUUSD)')
    parser.add_argument('--db-path', type=str, default='data/market_memory.db', help='Database path')
    
    args = parser.parse_args()
    
    logger.info("="*60)
    logger.info("Historical Data Collection for Oracle Training")
    logger.info("="*60)
    logger.info(f"Symbol: {args.symbol}")
    logger.info(f"Period: {args.days} days")
    logger.info(f"Database: {args.db_path}")
    logger.info("="*60)
    
    # Initialize MT5
    if not initialize_mt5():
        return
    
    try:
        # Calculate date range
        end_date = datetime.now()
        start_date = end_date - timedelta(days=args.days)
        
        logger.info(f"Date range: {start_date.date()} to {end_date.date()}")
        
        # Collect data for each timeframe
        timeframes = ["M1", "M5", "M15", "H1"]
        all_data = {}
        
        for tf in timeframes:
            df = collect_timeframe_data(args.symbol, tf, start_date, end_date)
            
            if df is not None:
                # Add technical indicators to M1 data
                if tf == "M1":
                    df = calculate_technical_indicators(df)
                
                all_data[tf] = df
                
                # Store in database
                table_name = f"candles_{tf.lower()}"
                store_in_database(df, args.db_path, table_name)
        
        # Summary
        logger.info("\n" + "="*60)
        logger.info("Collection Summary:")
        logger.info("="*60)
        for tf, df in all_data.items():
            logger.info(f"{tf:4s}: {len(df):6d} candles | {df['time'].min()} to {df['time'].max()}")
        
        logger.info("="*60)
        logger.info("✅ Data collection complete!")
        logger.info(f"Database: {args.db_path}")
        logger.info("\nNext steps:")
        logger.info("1. Run Oracle retraining: python scripts/retrain_oracle.py")
        logger.info("2. Test new model accuracy")
        logger.info("="*60)
        
    finally:
        mt5.shutdown()
        logger.info("MT5 connection closed")


if __name__ == "__main__":
    main()
