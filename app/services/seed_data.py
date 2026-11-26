import logging
from datetime import datetime
from sqlalchemy.orm import Session
from app.auth import get_password_hash
from app.models.user import User, Role, SiteRole, UserPermission
from app.models.station import Station
from app.services.neon_sync import run_neon_sync_all

logger = logging.getLogger("dmp.seed")

def seed_database_if_empty(db: Session):
    # Check if initial admin user already exists
    if db.query(User).first() is not None:
        return

    logger.info("Initializing system users and roles...")

    # 1. System Roles
    admin_role = Role(name="Administrator", description="Full system access and user management")
    analyst_role = Role(name="Analyst", description="Data analytics, thresholds, and exports")
    operator_role = Role(name="Operator", description="Station maintenance and live monitoring")
    viewer_role = Role(name="Viewer", description="Read-only telemetry monitoring")
    db.add_all([admin_role, analyst_role, operator_role, viewer_role])
    db.flush()

    # 2. Default Authorized Users
    admin_user = User(
        email="admin@datamonitor.io",
        full_name="System Administrator",
        hashed_password=get_password_hash("Admin@1234"),
        role_id=admin_role.id,
        is_active=True,
        is_superuser=True
    )
    analyst_user = User(
        email="analyst@datamonitor.io",
        full_name="Elena Vance (Senior Analyst)",
        hashed_password=get_password_hash("Analyst@1234"),
        role_id=analyst_role.id,
        is_active=True,
        is_superuser=False
    )
    operator_user = User(
        email="operator@datamonitor.io",
        full_name="Tariq Mansor (Site Operations)",
        hashed_password=get_password_hash("Operator@1234"),
        role_id=operator_role.id,
        is_active=True,
        is_superuser=False
    )
    db.add_all([admin_user, analyst_user, operator_user])
    db.commit()

    logger.info("Default user credentials created successfully.")

    # 3. If no stations exist, sync real Neon hydrological stations
    if db.query(Station).first() is None:
        logger.info("No stations found in database. Triggering automatic initial sync with Neon REST API...")
        try:
            run_neon_sync_all(days_lookback=7, max_workers=4)
        except Exception as e:
            logger.error(f"Initial Neon sync failed: {e}")
