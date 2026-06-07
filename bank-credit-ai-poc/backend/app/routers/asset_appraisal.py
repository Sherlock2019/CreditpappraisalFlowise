from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.audit import log_event
from app.database import get_db

router = APIRouter(prefix="/asset-appraisals", tags=["asset appraisal"])


def _collateral_value(appraised_value: float, haircut_pct: float) -> float:
    haircut = max(0.0, min(float(haircut_pct), 100.0))
    return round(float(appraised_value) * (1 - haircut / 100), 2)


@router.post("", response_model=schemas.AssetAppraisalOut)
def create_asset_appraisal(payload: schemas.AssetAppraisalCreate, db: Session = Depends(get_db)) -> schemas.AssetAppraisalOut:
    customer = crud.get_customer(db, payload.customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail="Customer not found")

    appraisal = models.AssetAppraisal(
        customer_id=payload.customer_id,
        asset_name=payload.asset_name,
        asset_class=payload.asset_class,
        description=payload.description,
        appraised_value=payload.appraised_value,
        currency=payload.currency,
        valuation_method=payload.valuation_method,
        haircut_pct=payload.haircut_pct,
        collateral_value=_collateral_value(payload.appraised_value, payload.haircut_pct),
        confidence_score=payload.confidence_score,
        status=payload.status,
        notes=payload.notes,
    )
    db.add(appraisal)
    db.commit()
    db.refresh(appraisal)
    log_event(
        db,
        "asset_appraisal_created",
        payload.customer_id,
        {
            "asset_appraisal_id": appraisal.id,
            "asset_class": appraisal.asset_class,
            "appraised_value": appraisal.appraised_value,
            "collateral_value": appraisal.collateral_value,
        },
    )
    return appraisal


@router.get("", response_model=list[schemas.AssetAppraisalOut])
def list_asset_appraisals(customer_id: int | None = None, db: Session = Depends(get_db)) -> list[schemas.AssetAppraisalOut]:
    query = db.query(models.AssetAppraisal)
    if customer_id is not None:
        query = query.filter(models.AssetAppraisal.customer_id == customer_id)
    return query.order_by(models.AssetAppraisal.created_at.desc(), models.AssetAppraisal.id.desc()).all()


@router.get("/summary/{customer_id}", response_model=schemas.AssetAppraisalSummary)
def asset_appraisal_summary(customer_id: int, db: Session = Depends(get_db)) -> schemas.AssetAppraisalSummary:
    if not crud.get_customer(db, customer_id):
        raise HTTPException(status_code=404, detail="Customer not found")

    rows = (
        db.query(
            models.AssetAppraisal.asset_class,
            func.coalesce(func.sum(models.AssetAppraisal.appraised_value), 0.0),
            func.coalesce(func.sum(models.AssetAppraisal.collateral_value), 0.0),
            func.count(models.AssetAppraisal.id),
        )
        .filter(models.AssetAppraisal.customer_id == customer_id)
        .group_by(models.AssetAppraisal.asset_class)
        .all()
    )
    by_class = {row[0]: float(row[1] or 0.0) for row in rows}
    return schemas.AssetAppraisalSummary(
        customer_id=customer_id,
        total_appraised_value=round(sum(float(row[1] or 0.0) for row in rows), 2),
        total_collateral_value=round(sum(float(row[2] or 0.0) for row in rows), 2),
        appraisal_count=sum(int(row[3] or 0) for row in rows),
        by_class=by_class,
    )
