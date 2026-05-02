import json
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List
from app.db.database import get_db
from app.core.auth import get_current_user
from app.models.base import Project, FtConversation

router = APIRouter(prefix="/ft-conversations", tags=["ft_conversations"])


class MessageTurn(BaseModel):
    role: str
    content: str


class FtConversationCreate(BaseModel):
    project_id: int
    is_base: bool = False
    base_id: Optional[int] = None
    split: str = "train"
    messages: List[MessageTurn]


class FtConversationUpdate(BaseModel):
    is_base: Optional[bool] = None
    split: Optional[str] = None
    messages: List[MessageTurn]


class FtConversationResponse(BaseModel):
    id: int
    project_id: int
    is_base: bool
    base_id: Optional[int]
    split: str
    messages: list
    created_at: str

    class Config:
        from_attributes = True


@router.get("", response_model=List[FtConversationResponse])
def get_ft_conversations(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    convs = db.query(FtConversation).filter(
        FtConversation.project_id == project_id
    ).order_by(FtConversation.created_at.desc()).all()

    return [
        FtConversationResponse(
            id=c.id,
            project_id=c.project_id,
            is_base=c.is_base,
            base_id=c.base_id,
            split=c.split,
            messages=c.messages,
            created_at=c.created_at.isoformat(),
        )
        for c in convs
    ]


@router.post("", response_model=FtConversationResponse, status_code=201)
def create_ft_conversation(
    req: FtConversationCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    if req.base_id:
        base = db.query(FtConversation).filter(
            FtConversation.id == req.base_id,
            FtConversation.is_base == True,
        ).first()
        if not base:
            raise HTTPException(status_code=404, detail="ベースが見つかりません")

    messages = [{"role": t.role, "content": t.content} for t in req.messages]
    conv = FtConversation(
        project_id=req.project_id,
        is_base=req.is_base,
        base_id=req.base_id,
        split=req.split,
        messages=messages,
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)

    return FtConversationResponse(
        id=conv.id,
        project_id=conv.project_id,
        is_base=conv.is_base,
        base_id=conv.base_id,
        split=conv.split,
        messages=conv.messages,
        created_at=conv.created_at.isoformat(),
    )


@router.put("/{conv_id}", response_model=FtConversationResponse)
def update_ft_conversation(
    conv_id: int,
    req: FtConversationUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    conv = db.query(FtConversation).filter(FtConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会話が見つかりません")

    if req.is_base is not None:
        conv.is_base = req.is_base
    if req.split is not None:
        conv.split = req.split
    conv.messages = [{"role": t.role, "content": t.content} for t in req.messages]
    db.commit()
    db.refresh(conv)

    return FtConversationResponse(
        id=conv.id,
        project_id=conv.project_id,
        is_base=conv.is_base,
        base_id=conv.base_id,
        split=conv.split,
        messages=conv.messages,
        created_at=conv.created_at.isoformat(),
    )


@router.patch("/{conv_id}/split", response_model=FtConversationResponse)
def update_split(
    conv_id: int,
    split: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    conv = db.query(FtConversation).filter(FtConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会話が見つかりません")
    if split not in ("train", "valid"):
        raise HTTPException(status_code=400, detail="split は train または valid を指定してください")
    conv.split = split
    db.commit()
    db.refresh(conv)

    return FtConversationResponse(
        id=conv.id,
        project_id=conv.project_id,
        is_base=conv.is_base,
        base_id=conv.base_id,
        split=conv.split,
        messages=conv.messages,
        created_at=conv.created_at.isoformat(),
    )


@router.delete("/{conv_id}", status_code=204)
def delete_ft_conversation(
    conv_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    conv = db.query(FtConversation).filter(FtConversation.id == conv_id).first()
    if not conv:
        raise HTTPException(status_code=404, detail="会話が見つかりません")
    db.delete(conv)
    db.commit()


@router.get("/export", response_class=PlainTextResponse)
def export_ft_conversations(
    project_id: int,
    split: str = "train",
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    """ベース + パターンを結合してJSONL形式で出力"""
    if split not in ("train", "valid"):
        raise HTTPException(status_code=400, detail="split は train または valid を指定してください")

    convs = db.query(FtConversation).filter(
        FtConversation.project_id == project_id,
        FtConversation.is_base == False,
        FtConversation.split == split,
    ).order_by(FtConversation.created_at.asc()).all()

    lines = []
    for conv in convs:
        if conv.base_id:
            base = db.query(FtConversation).filter(
                FtConversation.id == conv.base_id
            ).first()
            base_messages = base.messages if base else []
        else:
            base_messages = []

        messages = base_messages + conv.messages
        lines.append(json.dumps({"messages": messages}, ensure_ascii=False))

    return "\n".join(lines)
