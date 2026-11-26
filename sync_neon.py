"""
Neon Website & Hydrological REST Telemetry Synchronizer for Data Monitoring Platform.
Fetches authentic real-time and historical sensor telemetry from Surechem / Unidata Neon REST service
for stations configured in stations.json (categorized under NAHRIM).
"""
import sys
import logging
import argparse
from sqlalchemy import text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s"
)
logger = logging.getLogger("sync_neon")

from app.database import engine, Base, SessionLocal
import app.models
from app.services.neon_sync import run_neon_sync_all, sync_single_station, load_stations_config

def main():
    parser = argparse.ArgumentParser(description="Sync Neon Telemetry to Data Monitoring Platform")
    parser.add_argument("--days", type=int, default=30, help="Lookback window in days (default: 30)")
    parser.add_argument("--workers", type=int, default=4, help="Parallel worker threads (default: 4)")
    parser.add_argument("--node", type=str, default=None, help="Sync single node ID (e.g. 6 for NAHRIM Office)")
    parser.add_argument("--clean", action="store_true", help="Purge existing stations and telemetry before sync")
    args = parser.parse_args()

    # Ensure tables exist
    Base.metadata.create_all(bind=engine)

    if args.clean:
        logger.info("Cleaning existing telemetry and stations data...")
        with SessionLocal() as db:
            db.execute(text("DELETE FROM timeseries_data;"))
            db.execute(text("DELETE FROM sensors;"))
            db.execute(text("DELETE FROM loggers;"))
            db.execute(text("DELETE FROM stations;"))
            db.execute(text("DELETE FROM sites;"))
            db.commit()
        logger.info("Previous stations and timeseries purged.")

    if args.node:
        cfgs = load_stations_config()
        target = next((c for c in cfgs if str(c.get("node_id")) == str(args.node)), None)
        if not target:
            logger.error(f"Node ID {args.node} not found in stations.json!")
            sys.exit(1)
        logger.info(f"Syncing single station: {target.get('custom_name')} (Node {args.node})")
        pts = sync_single_station(target, days_lookback=args.days)
        logger.info(f"Done. Synced {pts} readings.")
    else:
        logger.info(f"Starting complete Neon sync ({args.days} days lookback, {args.workers} workers)...")
        total = run_neon_sync_all(days_lookback=args.days, max_workers=args.workers)
        logger.info(f"Completed! Total {total} telemetry readings synchronized.")

if __name__ == "__main__":
    main()
