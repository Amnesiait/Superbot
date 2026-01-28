#!/usr/bin/env python3
"""
AETHER Trading Bot - Enhanced Launcher Script
Ensures latest code is always loaded by clearing cache before starting.
"""

import sys
import os
import shutil
import subprocess
import logging
import time
from pathlib import Path

# Increase recursion limit to handle deep bucket evaluation chains
sys.setrecursionlimit(5000)

# Import psutil for process management
try:
    import psutil
except ImportError:
    psutil = None

# [FIX] Enable UTF-8 output on Windows
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'

def clear_python_cache():
    """Remove all __pycache__ directories and .pyc files to ensure fresh code."""
    try:
        project_root = Path(__file__).parent
        cache_cleared = 0
        
        # Remove __pycache__ directories
        for pycache_dir in project_root.rglob("__pycache__"):
            try:
                shutil.rmtree(pycache_dir)
                cache_cleared += 1
            except Exception:
                pass  # Silently skip if can't remove
        
        # Remove .pyc files
        for pyc_file in project_root.rglob("*.pyc"):
            try:
                pyc_file.unlink()
                cache_cleared += 1
            except Exception:
                pass
        
        # Remove .pyo files
        for pyo_file in project_root.rglob("*.pyo"):
            try:
                pyo_file.unlink()
                cache_cleared += 1
            except Exception:
                pass
        
        if cache_cleared > 0:
            print(f"[CACHE] Cleared {cache_cleared} cache items (ensuring fresh code)", flush=True)
    except Exception as e:
        # Don't fail startup if cache clear fails
        print(f"[WARNING] Cache clear warning: {e}", flush=True)

def kill_duplicate_bots():
    """Kill all other bot instances to ensure single-instance operation."""
    if not psutil:
        # psutil not available, skip duplicate killing
        return 0
    
    try:
        current_pid = os.getpid()
        killed_count = 0
        
        print("[PROCESS] Checking for duplicate bot instances...", flush=True)
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                # Check if it's a Python process running run_bot.py
                if proc.info['name'] and 'python' in proc.info['name'].lower():
                    cmdline = proc.info['cmdline']
                    if cmdline and any('run_bot.py' in str(arg) for arg in cmdline):
                        # Don't kill the current process
                        if proc.info['pid'] != current_pid:
                            print(f"[PROCESS] Found duplicate bot: PID {proc.info['pid']}", flush=True)
                            try:
                                proc.kill()
                                killed_count += 1
                                print(f"[PROCESS] [OK] Killed duplicate bot PID {proc.info['pid']}", flush=True)
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass  # Process already dead or no permission
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass  # Ignore processes we can't access
        
        if killed_count > 0:
            print(f"[PROCESS] Cleaned up {killed_count} duplicate bot process(es)", flush=True)
            print("[PROCESS] Waiting 2 seconds for processes to terminate...", flush=True)
            time.sleep(2)
        else:
            print("[PROCESS] [OK] No duplicate bots found", flush=True)
        
        return killed_count
    except Exception as e:
        # Don't fail startup if duplicate killing fails
        print(f"[WARNING] Could not check for duplicate bots: {e}", flush=True)
        return 0

# ======================================================================================
# COMMERCIAL SECURITY ENFORCEMENT
# ======================================================================================
try:
    from src.security.license_manager import enforce_license, _license_mgr
    from src.ai_core.bayesian_tuner import BayesianOptimizer as BayesianTuner
    
    # Check if license exists, if not create a trial (for First Run Experience)
    # IN PRODUCTION: Remove the 'create_trial_license' call!
    if not enforce_license():
        # Auto-generate trial for smoother dev experience, then re-check
        print(">> First run detected. Generating DEV TRIAL license...")
        _license_mgr.create_trial_license(owner_name="Developer Mode")  # noqa: F401 (private usage is intentional)
        if not enforce_license():
             print("FATAL: License generation failed.")
             sys.exit(1)
        print(">> TRIAL LICENSE ACTIVE")
except ImportError:
    print("Security module missing. Critical integrity failure.")
    sys.exit(1)

# ======================================================================================
    
def verify_version():
    """Display bot version on startup."""
    try:
        constants_file = Path(__file__).parent / "src" / "constants.py"
        with open(constants_file, 'r', encoding='utf-8') as f:
            for line in f:
                if 'SYSTEM_VERSION' in line and '=' in line:
                    version = line.split('=')[1].strip().strip('"').strip("'")
                    # Extract just the version number
                    if 'SYSTEM_VERSION' in line:
                        version_parts = version.split('#')[0].strip()
                        print(f"🤖 AETHER Bot Version: {version_parts}")
                    break
    except Exception:
        pass  # Silently skip if can't read version

def check_git_status():
    """Check for uncommitted changes (optional)."""
    try:
        result = subprocess.run(
            ['git', 'status', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent,
            timeout=2
        )
        
        if result.returncode == 0 and result.stdout.strip():
            print("⚠ Warning: Running with uncommitted changes")
    except Exception:
        pass  # Silently skip if Git not available

# Add the current directory to sys.path to ensure src is importable
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

if __name__ == "__main__":
    # Pre-startup checks (fast and non-blocking)
    print("=" * 70, flush=True)
    print(">> AETHER Trading Bot Startup Sequence (v7.0.0)", flush=True)
    print("=" * 70, flush=True)
    print()
    
    # 1. Kill any duplicate bot instances (CRITICAL for single-instance operation)
    #print("[1/5] Eliminating duplicate bot instances...", flush=True)
    #kill_duplicate_bots()
    #print()
    
    # 2. Clear Python cache to ensure fresh code
    print("[2/5] Clearing Python cache...", flush=True)
    clear_python_cache()
    print()
    
    # 3. Verify bot version
    print("[3/5] Verifying bot version...", flush=True)
    verify_version()
    print()
    
    # 4. Check git status
    print("[4/5] Checking system status...", flush=True)
    check_git_status()
    print()

    # 5. Initialize Bayesian Tuner (parameter optimization)
    print("[5/5] Initializing AI optimization system...", flush=True)
    tuner = None
    try:
        print(">> [INIT] Initializing Bayesian Tuner...", flush=True)
        tuner = BayesianTuner()
        logger = logging.getLogger("Launcher")
        logger.info("Bayesian Tuner Active.")
        print(">> [OK] Bayesian Tuner Ready", flush=True)
    except Exception as e:
        print(f">> [WARNING] Bayesian Tuner skipped: {e}", flush=True)
    
    print()
    print("=" * 70, flush=True)
    print("[OK] All startup checks passed. Starting main bot...", flush=True)
    print("=" * 70, flush=True)
    print()
    
    # Start the bot
    from src.cli import main as cli_main
    cli_main(tuner=tuner)  # type: ignore[return-value]
    