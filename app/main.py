import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text, inspect
from app.config import settings
from app.database import engine, Base, SessionLocal
import app.models # Register all models with Base
from app.services.seed_data import seed_database_if_empty
from app.services.neon_sync import run_neon_sync_all
from app.routers import (
    auth_router,
    dashboard_router,
    stations_router,
    timeseries_router,
    thresholds_router,
    alerts_router,
    reports_router,
    admin_router,
)

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("dmp.main")

def ensure_timeseries_columns():
    """Ensure newly introduced audit & correction columns exist in SQLite/PostgreSQL."""
    try:
        with engine.begin() as conn:
            inspector = inspect(conn)
            existing_tables = inspector.get_table_names()
            if "timeseries_data" in existing_tables:
                cols = [c["name"] for c in inspector.get_columns("timeseries_data")]
                if "raw_value" not in cols:
                    conn.execute(text("ALTER TABLE timeseries_data ADD COLUMN raw_value FLOAT;"))
                    log.info("Migrated timeseries_data: added raw_value column")
                if "remarks" not in cols:
                    conn.execute(text("ALTER TABLE timeseries_data ADD COLUMN remarks VARCHAR(255);"))
                    log.info("Migrated timeseries_data: added remarks column")
                if "edited_by" not in cols:
                    conn.execute(text("ALTER TABLE timeseries_data ADD COLUMN edited_by VARCHAR(100);"))
                    log.info("Migrated timeseries_data: added edited_by column")
                if "edited_at" not in cols:
                    conn.execute(text("ALTER TABLE timeseries_data ADD COLUMN edited_at DATETIME;"))
                    log.info("Migrated timeseries_data: added edited_at column")
    except Exception as ex:
        log.warning(f"Column migration check note: {ex}")

async def periodic_neon_sync(interval_seconds: int = 300):
    """Background task that syncs latest NAHRIM telemetry from Neon on startup and every 5 minutes."""
    await asyncio.sleep(2)
    first_run = True
    while True:
        try:
            lookback = 7 if first_run else 1
            log.info(f"Running background Neon sync (lookback={lookback}d)...")
            count = await asyncio.to_thread(run_neon_sync_all, days_lookback=lookback, max_workers=4)
            log.info(f"Background Neon sync finished: {count} new observations.")
            first_run = False
        except asyncio.CancelledError:
            log.info("Background Neon sync task cancelled.")
            break
        except Exception as e:
            log.error(f"Background Neon sync error: {e}")

        try:
            await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            break

@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("Initializing Data Monitoring Platform Database...")
    Base.metadata.create_all(bind=engine)
    ensure_timeseries_columns()
    
    # Auto-seed initial dataset if database is empty
    db = SessionLocal()
    try:
        seed_database_if_empty(db)
    except Exception as e:
        log.error(f"Error during auto-seed: {e}")
    finally:
        db.close()

    sync_task = asyncio.create_task(periodic_neon_sync(interval_seconds=300))
    
    log.info("Data Monitoring Platform Backend is operational.")
    yield
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass
    log.info("Shutting down backend services...")

app = FastAPI(
    title="Data Monitoring Platform Enterprise API",
    description="High-performance environmental, industrial telemetry, and sensor station monitoring API.",
    version="2.4.0",
    lifespan=lifespan
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.parsed_cors_origins + ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth_router.router)
app.include_router(dashboard_router.router)
app.include_router(stations_router.router)
app.include_router(timeseries_router.router)
app.include_router(thresholds_router.router)
app.include_router(alerts_router.router)
app.include_router(reports_router.router)
app.include_router(admin_router.router)

@app.get("/")
def root():
    return {
        "platform": "Data Monitoring Platform Enterprise",
        "status": "online",
        "version": "2.4.0",
        "docs_url": "/docs"
    }

@app.get("/health")
def health_check():
    return {"status": "healthy"}
