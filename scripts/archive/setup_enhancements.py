"""
Final Setup & Verification Script for Critical AI Enhancements

This script:
1. Verifies all enhancements are properly installed
2. Integrates adaptive learning into trading_engine.py
3. Tests all components
4. Provides next steps

Run this ONCE after reviewing the implementation guide.
"""

import os
import sys
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Setup")

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def check_file_exists(path, description):
    """Check if a file exists"""
    if os.path.exists(path):
        logger.info(f"✅ {description}: {path}")
        return True
    else:
        logger.error(f"❌ {description} NOT FOUND: {path}")
        return False


def verify_enhancements():
    """Verify all enhancements are installed"""
    logger.info("="*60)
    logger.info("Verifying Critical AI Enhancements")
    logger.info("="*60)
    
    all_ok = True
    
    # Check data collection script
    all_ok &= check_file_exists(
        "scripts/collect_training_data.py",
        "Data Collection Script"
    )
    
    # Check adaptive learner
    all_ok &= check_file_exists(
        "src/ai_core/adaptive_learner.py",
        "Adaptive Learning System"
    )
    
    # Check GOD MODE enhancement
    with open("src/position_manager.py", "r") as f:
        content = f.read()
        if "GOD MODE ML-BASED TREND EXIT" in content:
            logger.info("✅ GOD MODE Trend Exit: IMPLEMENTED")
        else:
            logger.error("❌ GOD MODE Trend Exit: NOT FOUND")
            all_ok = False
    
    return all_ok


def integrate_adaptive_learning():
    """Add adaptive learning integration to trading_engine.py"""
    logger.info("\n" + "="*60)
    logger.info("Integrating Adaptive Learning")
    logger.info("="*60)
    
    file_path = "src/trading_engine.py"
    
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        
        # Check if already integrated
        if "adaptive_learner" in content:
            logger.info("✅ Adaptive Learning: ALREADY INTEGRATED")
            return True
        
        # Find the insertion point (after MultiHorizonPredictor)
        target = "self.multi_horizon = MultiHorizonPredictor()"
        
        if target not in content:
            logger.error("❌ Could not find insertion point in trading_engine.py")
            logger.error("Please manually add adaptive learning integration")
            return False
        
        # Integration code
        integration_code = """
        # [ADAPTIVE LEARNING] Initialize adaptive learning system
        adaptive_enabled = str(os.getenv("AETHER_ADAPTIVE_LEARNING_ENABLED", "1")).strip().lower() in ("1", "true", "yes", "on")
        if adaptive_enabled:
            try:
                from src.ai_core.adaptive_learner import get_adaptive_learner
                self.adaptive_learner = get_adaptive_learner()
                self.adaptive_learner.start_scheduler()
                logger.info("[ADAPTIVE] Learning system enabled - weekly auto-retraining scheduled")
            except Exception as e:
                logger.warning(f"[ADAPTIVE] Failed to initialize: {e}")
                self.adaptive_learner = None
        else:
            self.adaptive_learner = None
"""
        
        # Insert after MultiHorizonPredictor
        content = content.replace(
            target,
            target + integration_code
        )
        
        # Write back
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
        
        logger.info("✅ Adaptive Learning: INTEGRATED into trading_engine.py")
        return True
        
    except Exception as e:
        logger.error(f"❌ Integration failed: {e}")
        return False


def create_env_config():
    """Create .env configuration if not exists"""
    logger.info("\n" + "="*60)
    logger.info("Checking Environment Configuration")
    logger.info("="*60)
    
    env_path = ".env"
    
    required_configs = {
        "AETHER_GOD_MODE_ML_ENABLED": "1",
        "AETHER_ADAPTIVE_LEARNING_ENABLED": "1",
        "AETHER_ORACLE_USE_REAL_DATA": "1",
    }
    
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            existing = f.read()
        
        for key, value in required_configs.items():
            if key not in existing:
                logger.warning(f"⚠️  Missing config: {key}={value}")
                logger.info(f"Add to .env: {key}={value}")
    else:
        logger.warning("⚠️  .env file not found")
        logger.info("Create .env with required configurations:")
        for key, value in required_configs.items():
            logger.info(f"  {key}={value}")


def test_imports():
    """Test that all modules can be imported"""
    logger.info("\n" + "="*60)
    logger.info("Testing Module Imports")
    logger.info("="*60)
    
    all_ok = True
    
    # Test adaptive learner
    try:
        from src.ai_core.adaptive_learner import get_adaptive_learner
        learner = get_adaptive_learner()
        logger.info("✅ AdaptiveLearner: Import successful")
    except Exception as e:
        logger.error(f"❌ AdaptiveLearner: Import failed - {e}")
        all_ok = False
    
    # Test Oracle
    try:
        from src.ai_core.oracle import Oracle
        logger.info("✅ Oracle: Import successful")
    except Exception as e:
        logger.error(f"❌ Oracle: Import failed - {e}")
        all_ok = False
    
    return all_ok


def main():
    """Run complete setup and verification"""
    logger.info("\n")
    logger.info("╔" + "="*58 + "╗")
    logger.info("║" + " "*10 + "AETHER AI Enhancement Setup" + " "*20 + "║")
    logger.info("╚" + "="*58 + "╝")
    logger.info("\n")
    
    # Step 1: Verify files
    if not verify_enhancements():
        logger.error("\n❌ SETUP FAILED: Missing required files")
        logger.error("Please ensure all enhancements are properly created")
        return False
    
    # Step 2: Integrate adaptive learning
    if not integrate_adaptive_learning():
        logger.warning("\n⚠️  Adaptive learning not integrated")
        logger.warning("Manual integration required - see implementation_guide.md")
    
    # Step 3: Check environment
    create_env_config()
    
    # Step 4: Test imports
    if not test_imports():
        logger.error("\n❌ IMPORT TEST FAILED")
        logger.error("Check for syntax errors or missing dependencies")
        return False
    
    # Success summary
    logger.info("\n" + "="*60)
    logger.info("✅ SETUP COMPLETE!")
    logger.info("="*60)
    
    logger.info("\nNext Steps:")
    logger.info("1. Collect market data:")
    logger.info("   python scripts/collect_training_data.py --days 90")
    logger.info("")
    logger.info("2. Restart the bot:")
    logger.info("   python run_bot.py")
    logger.info("")
    logger.info("3. Monitor logs for:")
    logger.info("   - [GOD MODE] TREND EXIT (death spiral prevention)")
    logger.info("   - [ADAPTIVE] Learning system enabled")
    logger.info("   - [ATOMIC CLOSE] Batch closing")
    logger.info("")
    logger.info("="*60)
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"Setup failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
