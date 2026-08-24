from typing import List, Dict, Any, Optional
from fastapi import APIRouter, HTTPException, Depends, Request
from pydantic import BaseModel
from validation_db import create_plan as db_create_plan, list_plans, get_plan, delete_plan, save_baseline
def dummy_require_feature(feature_id: str):
    def _dependency():
        return None
    return _dependency

try:
    from main import require_feature
except ImportError:
    require_feature = dummy_require_feature

router = APIRouter(
    prefix="/api/validation",
    tags=["validation"],
    dependencies=[Depends(require_feature("post-change-validation"))]
)

class PlanCreate(BaseModel):
    name: str
    change_ticket: Optional[str] = None
    category: Optional[str] = None
    description: Optional[str] = None
    target_devices: List[str] = []
    scenario_modules: List[str] = []
    config_parameters: Dict[str, Any] = {}

class BaselineCreate(BaseModel):
    plan_id: int
    ticket_number: str
    raw_outputs: Dict[str, Any] = {}
    parsed_metrics: Dict[str, Any] = {}

@router.post("/plans", status_code=201)
def create_plan_route(req: PlanCreate, user: Optional[Dict] = Depends(require_feature("post-change-validation"))):
    username = user["username"] if user else "anonymous"
    plan_id = db_create_plan(
        name=req.name,
        change_ticket=req.change_ticket,
        category=req.category,
        description=req.description,
        target_devices=req.target_devices,
        scenario_modules=req.scenario_modules,
        config_parameters=req.config_parameters
    )
    return {"id": plan_id}

@router.get("/plans")
def list_plans_route():
    return list_plans()

@router.get("/plans/{plan_id}")
def get_plan_route(plan_id: int):
    plan = get_plan(plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan not found")
    return plan

@router.delete("/plans/{plan_id}")
def delete_plan_route(plan_id: int):
    if not delete_plan(plan_id):
        raise HTTPException(status_code=404, detail="Plan not found")
    return {"status": "deleted"}

@router.post("/baselines", status_code=201)
def create_baseline_route(req: BaselineCreate, user: Optional[Dict] = Depends(require_feature("post-change-validation"))):
    username = user["username"] if user else "anonymous"
    baseline_id = save_baseline(
        plan_id=req.plan_id,
        ticket_number=req.ticket_number,
        captured_by=username,
        raw_outputs=req.raw_outputs,
        parsed_metrics=req.parsed_metrics
    )
    return {"id": baseline_id}
