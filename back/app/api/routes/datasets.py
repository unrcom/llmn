from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.config import CHROMA_DB_DIR
from app.core.auth import get_current_user
from app.models.base import Dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])


class DatasetCreate(BaseModel):
    project_id: int
    display_name: str
    description: Optional[str] = None


class DatasetResponse(BaseModel):
    id: int
    project_id: int
    name: str
    display_name: str
    description: Optional[str]
    created_at: str


def _to_response(d: Dataset) -> DatasetResponse:
    return DatasetResponse(
        id=d.id,
        project_id=d.project_id,
        name=d.name,
        display_name=d.display_name,
        description=d.description,
        created_at=d.created_at.isoformat(),
    )


@router.get("", response_model=List[DatasetResponse])
def get_datasets(project_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    from app.models.base import Dataset
    datasets = db.query(Dataset).filter(Dataset.project_id == project_id).order_by(Dataset.created_at.desc()).all()
    return [_to_response(d) for d in datasets]


@router.post("", response_model=DatasetResponse, status_code=201)
def create_dataset(req: DatasetCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    import chromadb
    from app.models.base import Dataset
    import os

    # 1プロジェクト1データセット制限
    existing = db.query(Dataset).filter(Dataset.project_id == req.project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="このプロジェクトにはすでにデータセットが存在します")

    import uuid
    auto_name = f"ds-{uuid.uuid4().hex[:12]}"

    # ChromaDBにコレクション作成
    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    client.get_or_create_collection(auto_name)

    dataset = Dataset(
        project_id=req.project_id,
        name=auto_name,
        display_name=req.display_name,
        description=req.description,
    )
    db.add(dataset)
    db.commit()
    db.refresh(dataset)
    return _to_response(dataset)


@router.delete("/{dataset_id}", status_code=204)
def delete_dataset(dataset_id: int, db: Session = Depends(get_db), _=Depends(get_current_user)):
    import chromadb
    import os
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    # ChromaDBのコレクション削除
    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    try:
        client.delete_collection(dataset.name)
    except Exception:
        pass

    db.delete(dataset)
    db.commit()


class DocumentAdd(BaseModel):
    content: str  # JSON文字列 or テキスト
    doc_id: Optional[str] = None


@router.post("/{dataset_id}/documents", status_code=201)
def add_document(
    dataset_id: int,
    req: DocumentAdd,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    import os
    import uuid
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(dataset.name)

    doc_id = req.doc_id or str(uuid.uuid4())
    collection.add(
        documents=[req.content],
        ids=[doc_id],
    )
    return {"ok": True, "id": doc_id}


@router.get("/{dataset_id}/documents")
def get_documents(
    dataset_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    import os
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(dataset.name)

    result = collection.get()
    docs = []
    for i, doc_id in enumerate(result["ids"]):
        docs.append({"id": doc_id, "content": result["documents"][i]})
    return docs


@router.delete("/{dataset_id}/documents/{doc_id}", status_code=204)
def delete_document(
    dataset_id: int,
    doc_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    import os
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(dataset.name)
    collection.delete(ids=[doc_id])


class DocumentUpdate(BaseModel):
    content: str


@router.put("/{dataset_id}/documents/{doc_id}", status_code=200)
def update_document(
    dataset_id: int,
    doc_id: str,
    req: DocumentUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    import os
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(dataset.name)
    collection.update(
        ids=[doc_id],
        documents=[req.content],
    )
    return {"ok": True, "id": doc_id}


class DatasetUpdate(BaseModel):
    display_name: str
    description: Optional[str] = None


@router.put("/{dataset_id}", response_model=DatasetResponse)
def update_dataset(
    dataset_id: int,
    req: DatasetUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.base import Dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")
    dataset.display_name = req.display_name
    dataset.description = req.description
    db.commit()
    db.refresh(dataset)
    return _to_response(dataset)
