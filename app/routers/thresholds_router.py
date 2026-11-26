from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.alert import ThresholdRule, Alert
from app.models.station import Station

router = APIRouter(prefix="/thresholds", tags=["Thresholds & Rules"])

class ThresholdRuleCreate(BaseModel):
    rule_name: str
    station_id: Optional[int] = None
    metric_key: str
    comparison_operator: str = ">"
    warning_value: float
    critical_value: float
    is_active: bool = True

@router.get("/rules")
def get_threshold_rules(station_id: Optional[int] = None, db: Session = Depends(get_db)):
    query = db.query(ThresholdRule)
    if station_id:
        query = query.filter((ThresholdRule.station_id == station_id) | (ThresholdRule.station_id == None))
    rules = query.all()
    
    result = []
    for r in rules:
        st_name = "Global (All Stations)"
        if r.station_id:
            st = db.query(Station).filter(Station.id == r.station_id).first()
            if st:
                st_name = f"{st.name} ({st.code})"
        
        result.append({
            "id": r.id,
            "rule_name": r.rule_name,
            "station_id": r.station_id,
            "station_name": st_name,
            "metric_key": r.metric_key,
            "comparison_operator": r.comparison_operator,
            "warning_value": r.warning_value,
            "critical_value": r.critical_value,
            "is_active": r.is_active,
            "created_at": r.created_at
        })
    return result

@router.post("/rules")
def create_threshold_rule(rule_in: ThresholdRuleCreate, db: Session = Depends(get_db)):
    rule = ThresholdRule(
        rule_name=rule_in.rule_name,
        station_id=rule_in.station_id,
        metric_key=rule_in.metric_key,
        comparison_operator=rule_in.comparison_operator,
        warning_value=rule_in.warning_value,
        critical_value=rule_in.critical_value,
        is_active=rule_in.is_active
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"message": "Rule created successfully", "rule": rule.id}

@router.put("/rules/{rule_id}")
def update_threshold_rule(rule_id: int, rule_in: ThresholdRuleCreate, db: Session = Depends(get_db)):
    rule = db.query(ThresholdRule).filter(ThresholdRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")
    
    rule.rule_name = rule_in.rule_name
    rule.station_id = rule_in.station_id
    rule.metric_key = rule_in.metric_key
    rule.comparison_operator = rule_in.comparison_operator
    rule.warning_value = rule_in.warning_value
    rule.critical_value = rule_in.critical_value
    rule.is_active = rule_in.is_active
    
    db.commit()
    return {"message": "Rule updated successfully"}

@router.delete("/rules/{rule_id}")
def delete_threshold_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(ThresholdRule).filter(ThresholdRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Threshold rule not found")
    db.delete(rule)
    db.commit()
    return {"message": "Rule deleted successfully"}
