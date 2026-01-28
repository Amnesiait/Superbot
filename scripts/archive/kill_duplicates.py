"""
Kill Duplicate Bot Processes

This script ensures only ONE bot instance is running at a time.
Run this before starting the bot to clean up any zombie processes.
"""

import os
import sys
import psutil
import time

def kill_duplicate_bots():
    """Kill all Python processes running run_bot.py except this one"""
    current_pid = os.getpid()
    killed_count = 0
    
    print("🔍 Scanning for duplicate bot processes...")
    
    for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
        try:
            # Check if it's a Python process
            if proc.info['name'] and 'python' in proc.info['name'].lower():
                cmdline = proc.info['cmdline']
                if cmdline and any('run_bot.py' in str(arg) for arg in cmdline):
                    # Don't kill this script
                    if proc.info['pid'] != current_pid:
                        print(f"⚠️  Found duplicate bot: PID {proc.info['pid']}")
                        print(f"   Command: {' '.join(cmdline)}")
                        proc.kill()
                        killed_count += 1
                        print(f"   ✅ Killed PID {proc.info['pid']}")
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    
    if killed_count > 0:
        print(f"\n🧹 Cleaned up {killed_count} duplicate bot process(es)")
        print("⏳ Waiting 2 seconds for processes to terminate...")
        time.sleep(2)
    else:
        print("✅ No duplicate bots found")
    
    return killed_count

if __name__ == "__main__":
    print("=" * 60)
    print("   DUPLICATE BOT KILLER")
    print("=" * 60)
    print()
    
    killed = kill_duplicate_bots()
    
    print()
    print("=" * 60)
    print("✅ Ready to start bot (only ONE instance will run)")
    print("=" * 60)
    
    sys.exit(0)
