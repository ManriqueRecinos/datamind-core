"""Endpoints REST del Laboratorio Neuronal sobre datos reales de pgvector."""

from typing import List, Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/neural-lab", tags=["Neural Lab"])


class TrainRequest(BaseModel):
    learning_rate: float = Field(default=0.001, gt=0.0, le=1.0)
    epochs: int = Field(default=50, ge=5, le=2000)
    hidden_layers: Optional[List[int]] = Field(default=[128, 64])


class PredictRequest(BaseModel):
    text: str = Field(..., min_length=2)


@router.post("/train")
async def train_model_endpoint(payload: TrainRequest):
    from app.infrastructure.ml.trainer import train_knowledge_model
    try:
        return await train_knowledge_model(
            learning_rate=payload.learning_rate,
            epochs=payload.epochs,
            hidden_layers=payload.hidden_layers,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/predict")
async def predict_endpoint(payload: PredictRequest):
    from app.infrastructure.ml.trainer import predict_knowledge_category
    try:
        return await predict_knowledge_category(text=payload.text)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
