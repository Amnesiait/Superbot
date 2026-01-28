"""
World-Class Oracle Retraining Script
Uses enhanced NexusTrainerV2 with state-of-the-art optimizations.
"""

import sys
import os
import argparse
import logging

# Add project to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.ai_core.nexus_trainer_v2 import NexusTrainerV2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("WorldClassTraining")

def main():
    parser = argparse.ArgumentParser(description='World-Class Oracle Retraining')
    parser.add_argument('--epochs', type=int, default=15, help='Number of training epochs')
    parser.add_argument('--validation-split', type=float, default=0.2, help='Validation split ratio')
    args = parser.parse_args()
    
    logger.info("=" * 70)
    logger.info("🌟 WORLD-CLASS ORACLE TRAINING - Advanced AI System")
    logger.info("=" * 70)
    logger.info(f"Epochs: {args.epochs}")
    logger.info(f"Validation Split: {args.validation_split * 100:.0f}%")
    logger.info("")
    logger.info("Enhancements Active:")
    logger.info("  ✅ Focal Loss (class imbalance handling)")
    logger.info("  ✅ Z-Score Normalization (regime-robust)")
    logger.info("  ✅ Technical Indicators (RSI, MACD, ATR, etc.)")
    logger.info("  ✅ OneCycleLR Scheduling (super-convergence)")
    logger.info("  ✅ Early Stopping (overfitting prevention)")
    logger.info("  ✅ Gradient Clipping (training stability)")
    logger.info("=" * 70)
    logger.info("")
    
    try:
        trainer = NexusTrainerV2()
        final_loss = trainer.train(epochs=args.epochs, validation_split=args.validation_split)
        
        if final_loss is not None:
            logger.info("")
            logger.info("=" * 70)
            logger.info(" TRAINING COMPLETED SUCCESSFULLY")
            logger.info(f"Best Validation Loss: {final_loss:.4f}")
            logger.info("=" * 70)
            logger.info("")
            logger.info("Next Steps:")
            logger.info("  1. Run backtest: python scripts/backtest_oracle.py --days 30")
            logger.info("  2. Verify Win Rate > 55% and Profit Factor > 1.3")
            logger.info("  3. Restart bot: python run_bot.py")
            logger.info("")
            return 0
        else:
            logger.error("❌ Training failed. Check logs above for details.")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Training failed with exception: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(main())
