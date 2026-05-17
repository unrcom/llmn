from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response as FastAPIResponse
from datetime import datetime, timezone
import re as _re
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
    title: Optional[str] = None
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

    if len(req.content) > 700:
        raise HTTPException(status_code=400, detail="本文は700文字以内にしてください")

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    chroma_path = CHROMA_DB_DIR
    client = chromadb.PersistentClient(path=chroma_path)
    collection = client.get_or_create_collection(dataset.name)

    doc_id = req.doc_id or str(uuid.uuid4())
    meta = {"title": req.title} if req.title else None
    collection.add(
        documents=[req.content],
        metadatas=[meta] if meta else None,
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
        meta = result["metadatas"][i] if result["metadatas"] else {}
        docs.append({
            "id": doc_id,
            "title": meta.get("title", ""),
            "content": result["documents"][i]
        })
    return list(reversed(docs))


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


# ── エクスポート（全体）──────────────────────────────────────────
@router.get("/export/all")
def export_all_datasets(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.base import Dataset
    datasets = db.query(Dataset).order_by(Dataset.id).all()

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_str = now[:10]
    lines = []
    lines.append("---")
    lines.append("type: full")
    lines.append(f"exported_at: {now}")
    lines.append("---")
    lines.append("")

    for dataset in datasets:
        docs = _get_docs_from_collection(dataset)
        lines.append(f"# project: {dataset.display_name}")
        lines.append(f"# dataset_name: {dataset.name}")
        lines.append("")
        for doc in docs:
            lines.append(f"## {doc['id']}")
            lines.append("")
            if doc.get("title"):
                lines.append(f"**title:** {doc['title']}")
                lines.append("")
            lines.append(doc["content"])
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append("")

    md_text = "\n".join(lines)
    filename = f"llamune_backup_{now_str}.md"

    return FastAPIResponse(
        content=md_text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── エクスポート（プロジェクト単位）──────────────────────────────

def _build_md(dataset, documents: list, export_type: str = "project") -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = []
    lines.append("---")
    lines.append(f"type: {export_type}")
    lines.append(f"exported_at: {now}")
    lines.append("---")
    lines.append("")
    lines.append(f"# project: {dataset.display_name}")
    lines.append(f"# dataset_name: {dataset.name}")
    lines.append("")
    for doc in documents:
        lines.append(f"## {doc['id']}")
        lines.append("")
        if doc.get("title"):
            lines.append(f"**title:** {doc['title']}")
            lines.append("")
        lines.append(doc["content"])
        lines.append("")
        lines.append("---")
        lines.append("")
    return "\n".join(lines)


def _get_docs_from_collection(dataset) -> list:
    import chromadb
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)
    result = collection.get()
    docs = []
    for i, doc_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result["metadatas"] else {}
        docs.append({
            "id": doc_id,
            "title": meta.get("title", ""),
            "content": result["documents"][i],
        })
    return docs


@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    from app.models.base import Dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    docs = _get_docs_from_collection(dataset)
    md_text = _build_md(dataset, docs, export_type="project")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    filename = f"{dataset.name}_{now_str}.md"

    return FastAPIResponse(
        content=md_text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )



# ── スナップショット ──────────────────────────────────────────
import os

BACKUP_DIR = os.path.expanduser("~/dev/llamune/backups")

def _save_snapshot(md_text: str, filename: str):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_text)

def _snapshot_dataset(dataset, db):
    """プロジェクト単位のスナップショットを保存"""
    docs = _get_docs_from_collection(dataset)
    md_text = _build_md(dataset, docs, export_type="project")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    filename = f"snapshot_{dataset.name}_{now_str}.md"
    _save_snapshot(md_text, filename)

def _snapshot_all(db):
    """全体スナップショットを保存"""
    from app.models.base import Dataset
    datasets = db.query(Dataset).order_by(Dataset.id).all()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    lines = []
    lines.append("---")
    lines.append("type: full")
    lines.append(f"exported_at: {now}")
    lines.append("---")
    lines.append("")
    for dataset in datasets:
        docs = _get_docs_from_collection(dataset)
        lines.append(f"# project: {dataset.display_name}")
        lines.append(f"# dataset_name: {dataset.name}")
        lines.append("")
        for doc in docs:
            lines.append(f"## {doc['id']}")
            lines.append("")
            if doc.get("title"):
                lines.append(f"**title:** {doc['title']}")
                lines.append("")
            lines.append(doc["content"])
            lines.append("")
            lines.append("---")
            lines.append("")
        lines.append("")
    md_text = "\n".join(lines)
    filename = f"snapshot_full_{now_str}.md"
    _save_snapshot(md_text, filename)


# ── インポート共通パーサー ────────────────────────────────────────
def _parse_md(text: str) -> tuple[str, list[dict]]:
    """
    MDファイルをパースしてドキュメントリストを返す。
    戻り値: (type, [{ dataset_name, id, title, content }, ...])
    """
    lines = text.split("\n")

    # front matter をパース
    start = 0
    md_type = ""
    if lines and lines[0].strip() == "---":
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
            m = _re.match(r'^type:\s+(.+)$', lines[i].strip())
            if m:
                md_type = m.group(1).strip()

    body = "\n".join(lines[start:])

    # dataset_name の取得（# dataset_name: xxx）
    current_dataset_name = None
    results = []

    # "---" でブロック分割
    blocks = body.split("\n---")

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        # dataset_name コメント行を拾う
        for line in block.splitlines():
            m = _re.match(r'^#\s+dataset_name:\s+(.+)$', line.strip())
            if m:
                current_dataset_name = m.group(1).strip()

        # ドキュメントブロック（## id で始まる）
        id_match = _re.search(r'^##\s+(.+)$', block, _re.MULTILINE)
        if not id_match:
            continue

        doc_id = id_match.group(1).strip()
        rest = block[id_match.end():].strip()

        title = ""
        title_match = _re.match(r'^\*\*title:\*\*\s*(.+)$', rest, _re.MULTILINE)
        if title_match:
            title = title_match.group(1).strip()
            rest = rest[title_match.end():].strip()

        content = rest.strip()
        if not content:
            continue

        results.append({
            "dataset_name": current_dataset_name,
            "id": doc_id,
            "title": title,
            "content": content,
        })

    return md_type, results


def _upsert_docs(collection, docs: list) -> tuple[int, int]:
    imported = skipped = 0
    for doc in docs:
        content = doc["content"]
        if not content or len(content) > 700:
            skipped += 1
            continue
        title = doc.get("title", "")
        doc_id = doc["id"]
        meta = [{"title": title}] if title else None
        try:
            existing = collection.get(ids=[doc_id])
            if existing["ids"]:
                collection.update(ids=[doc_id], documents=[content], metadatas=meta)
            else:
                collection.add(ids=[doc_id], documents=[content], metadatas=meta)
            imported += 1
        except Exception:
            skipped += 1
    return imported, skipped


# ── インポート（全体）────────────────────────────────────────────
@router.post("/import/all", status_code=200)
async def import_all_datasets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    from app.models.base import Dataset

    raw = await file.read()
    text = raw.decode("utf-8")
    md_type, docs = _parse_md(text)
    if md_type != "full":
        raise HTTPException(status_code=400, detail="全体バックアップファイルを選択してください。プロジェクト単位のファイルはリストアに使用できません")

    # インポート前に全体スナップショット保存
    _snapshot_all(db)

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    total_imported = total_skipped = 0
    not_found = set()

    # dataset_name でグループ化
    from itertools import groupby
    docs_by_ds: dict[str, list] = {}
    for doc in docs:
        ds_name = doc.get("dataset_name")
        if not ds_name:
            total_skipped += 1
            continue
        docs_by_ds.setdefault(ds_name, []).append(doc)

    for ds_name, ds_docs in docs_by_ds.items():
        dataset = db.query(Dataset).filter(Dataset.name == ds_name).first()
        if not dataset:
            not_found.add(ds_name)
            total_skipped += len(ds_docs)
            continue
        collection = client.get_or_create_collection(dataset.name)
        imp, skp = _upsert_docs(collection, ds_docs)
        total_imported += imp
        total_skipped += skp

    result = {"imported": total_imported, "skipped": total_skipped}
    if not_found:
        result["not_found_datasets"] = list(not_found)
    return result
# ── インポート（プロジェクト単位）────────────────────────────────

@router.post("/{dataset_id}/import", status_code=200)
async def import_dataset(
    dataset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    from app.models.base import Dataset

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    raw = await file.read()
    text = raw.decode("utf-8")
    md_type, docs = _parse_md(text)
    if md_type != "project":
        raise HTTPException(status_code=400, detail="プロジェクト単位のバックアップファイルを選択してください（全体バックアップは使用できません）")

    # dataset_name の一致チェック
    ds_names = {doc.get("dataset_name") for doc in docs if doc.get("dataset_name")}
    if ds_names and dataset.name not in ds_names:
        raise HTTPException(status_code=400, detail=f"このファイルは別のデータセット（{', '.join(ds_names)}）のバックアップです")

    # インポート前にスナップショット保存
    _snapshot_dataset(dataset, db)

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)
    imported, skipped = _upsert_docs(collection, docs)

    return {"imported": imported, "skipped": skipped}


