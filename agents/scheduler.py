"""
Scheduler — runs the check every day at 7:00 AM
Run: python agents/scheduler.py
"""
import schedule, time, sys, os
from datetime import datetime
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from agents.orchestrator import run_daily_check
from dotenv import load_dotenv
load_dotenv()

if __name__ == "__main__":
    print("🚀 ComplianceAI Scheduler starting...")
    print(f"   Time now: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("   Scheduled: every day at 07:00 AM")
    print("   Running initial check now...\n")
    run_daily_check()
    schedule.every().day.at("07:00").do(run_daily_check)
    print("\n⏰ Waiting for next run at 07:00. Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(60)
