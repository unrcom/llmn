from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.auth import get_current_user
from app.models.base import SystemPrompt

router = APIRouter(prefix="/system-prompts", tags=["system_prompts"])


class SystemPromptCreate(BaseModel):
    project_id: int
    name: str
    content: str


class SystemPromptUpdate(BaseModel):
    name: str
    content: str


class SystemPromptResponse(BaseModel):
    id: int
    project_id: int
    name: str
    content: str
    created_at: str

    class Config:
        from_attributes = True


def _to_response(sp: SystemPrompt) -> SystemPromptResponse:
    return SystemPromptResponse(
        id=sp.id,
        project_id=sp.project_id,
        name=sp.name,
        content=sp.content,
        created_at=sp.created_at.isoformat(),
    )


@router.get("", response_model=List[SystemPromptResponse])
def get_system_prompts(project_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    return [_to_response(sp) for sp in db.query(SystemPrompt).filter(SystemPrompt.project_id == project_id).all()]


@router.post("", response_model=SystemPromptResponse, status_code=201)
def create_system_prompt(req: SystemPromptCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    # プロジェクトで1件のみ
    existing = db.query(SystemPrompt).filter(SystemPrompt.project_id == req.project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="このプロジェクトにはすでにシステムプロンプトが登録されています")
    sp = SystemPrompt(project_id=req.project_id, name=req.name, content=req.content)
    db.add(sp)
    db.commit()
    db.refresh(sp)
    return _to_response(sp)


@router.put("/{sp_id}", response_model=SystemPromptResponse)
def update_system_prompt(sp_id: int, req: SystemPromptUpdate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    sp = db.query(SystemPrompt).filter(SystemPrompt.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="見つかりません")
    sp.name = req.name
    sp.content = req.content
    db.commit()
    db.refresh(sp)
    return _to_response(sp)


@router.delete("/{sp_id}", status_code=204)
def delete_system_prompt(sp_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    sp = db.query(SystemPrompt).filter(SystemPrompt.id == sp_id).first()
    if not sp:
        raise HTTPException(status_code=404, detail="見つかりません")
    db.delete(sp)
    db.commit()
