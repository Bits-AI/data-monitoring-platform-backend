from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from app.database import get_db
from app.auth import get_password_hash, require_admin
from app.models.user import User, Role, SiteRole
from app.models.station import Site, Station

router = APIRouter(prefix="/admin", tags=["Administration"])

class UserCreate(BaseModel):
    email: str
    full_name: str
    password: str
    role_id: int
    is_active: bool = True

class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    password: Optional[str] = None
    role_id: Optional[int] = None
    is_active: Optional[bool] = None

@router.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return [
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "Viewer",
            "role_id": u.role_id,
            "is_active": u.is_active,
            "is_superuser": u.is_superuser,
            "created_at": u.created_at,
            "last_login": u.last_login
        }
        for u in users
    ]

@router.post("/users")
def create_user(req: UserCreate, db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.email == req.email).first()
    if existing:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    
    u = User(
        email=req.email,
        full_name=req.full_name,
        hashed_password=get_password_hash(req.password),
        role_id=req.role_id,
        is_active=req.is_active
    )
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"message": "User created successfully", "user_id": u.id}

@router.put("/users/{user_id}")
def update_user(user_id: int, req: UserUpdate, db: Session = Depends(get_db)):
    u = db.query(User).filter(User.id == user_id).first()
    if not u:
        raise HTTPException(status_code=404, detail="User not found")
    
    if req.full_name is not None:
        u.full_name = req.full_name
    if req.email is not None and req.email != u.email:
        existing = db.query(User).filter(User.email == req.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Email already in use by another user")
        u.email = req.email
    if req.password:
        u.hashed_password = get_password_hash(req.password)
    if req.role_id is not None:
        u.role_id = req.role_id
    if req.is_active is not None:
        u.is_active = req.is_active
    
    db.commit()
    return {"message": "User updated successfully"}

@router.get("/roles")
def list_roles(db: Session = Depends(get_db)):
    roles = db.query(Role).all()
    return [
        {"id": r.id, "name": r.name, "description": r.description}
        for r in roles
    ]

@router.get("/overview")
def get_admin_overview(db: Session = Depends(get_db)):
    total_users = db.query(User).count()
    total_sites = db.query(Site).count()
    total_stations = db.query(Station).count()

    return {
        "total_users": total_users,
        "total_sites": total_sites,
        "total_stations": total_stations,
        "system_version": "v2.4.0-minimalist-enterprise",
        "api_status": "healthy"
    }
