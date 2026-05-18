from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from fastapi.responses import Response as FastAPIResponse
from datetime import datetime, timezone
import re as _re
import os
from pydantic import BaseModel
from typing import Optional, List
from sqlalchemy.orm import Session
from app.db.database import get_db
from app.core.config import CHROMA_DB_DIR
from app.core.auth import get_current_user
from app.models.base import Dataset

router = APIRouter(prefix="/datasets", tags=["datasets"])

BACKUP_DIR = os.path.expanduser("~/dev/llamune/backups")


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
    datasets = db.query(Dataset).filter(Dataset.project_id == project_id).order_by(Dataset.created_at.desc()).all()
    return [_to_response(d) for d in datasets]


@router.post("", response_model=DatasetResponse, status_code=201)
def create_dataset(req: DatasetCreate, db: Session = Depends(get_db), _=Depends(get_current_user)):
    import chromadb
    import uuid

    existing = db.query(Dataset).filter(Dataset.project_id == req.project_id).first()
    if existing:
        raise HTTPException(status_code=400, detail="このプロジェクトにはすでにデータセットが存在します")

    auto_name = f"ds-{uuid.uuid4().hex[:12]}"
    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
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

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    try:
        client.delete_collection(dataset.name)
    except Exception:
        pass

    db.delete(dataset)
    db.commit()


class DocumentAdd(BaseModel):
    title: Optional[str] = None
    content: str
    doc_id: Optional[str] = None
    source_id: Optional[str] = None
    source_data: Optional[str] = None
    created_at: Optional[str] = None


@router.post("/{dataset_id}/documents", status_code=201)
def add_document(
    dataset_id: int,
    req: DocumentAdd,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb
    import uuid

    if len(req.content) > 700:
        raise HTTPException(status_code=400, detail="本文は700文字以内にしてください")

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)

    doc_id = req.doc_id or str(uuid.uuid4())
    meta = {
        "title": req.title or "",
        "source_id": req.source_id or str(uuid.uuid4()),
        "source_data": req.source_data or "",
        "created_at": req.created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    collection.add(
        documents=[req.content],
        metadatas=[meta],
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

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

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
            "source_id": meta.get("source_id", ""),
            "source_data": meta.get("source_data", ""),
            "created_at": meta.get("created_at", ""),
        })
    docs.sort(key=lambda d: d["created_at"], reverse=True)
    return docs


@router.delete("/{dataset_id}/documents/{doc_id}", status_code=204)
def delete_document(
    dataset_id: int,
    doc_id: str,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)
    collection.delete(ids=[doc_id])


class DocumentUpdate(BaseModel):
    content: str
    source_data: Optional[str] = None
    created_at: Optional[str] = None


@router.put("/{dataset_id}/documents/{doc_id}", status_code=200)
def update_document(
    dataset_id: int,
    doc_id: str,
    req: DocumentUpdate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)

    existing = collection.get(ids=[doc_id])
    meta = existing["metadatas"][0] if existing["metadatas"] else {}
    if req.source_data is not None:
        meta["source_data"] = req.source_data
    if req.created_at is not None:
        meta["created_at"] = req.created_at
    collection.update(
        ids=[doc_id],
        documents=[req.content],
        metadatas=[meta],
    )
    return {"ok": True, "id": doc_id}


@router.get("/{dataset_id}/sources")
def get_sources(
    dataset_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)
    result = collection.get()

    sources = {}
    for i, doc_id in enumerate(result["ids"]):
        meta = result["metadatas"][i] if result["metadatas"] else {}
        source_id = meta.get("source_id", "")
        if not source_id or source_id in sources:
            continue
        sources[source_id] = {
            "source_id": source_id,
            "source_data": meta.get("source_data", ""),
            "created_at": meta.get("created_at", ""),
        }
    return sorted(sources.values(), key=lambda s: s["created_at"], reverse=True)


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
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")
    dataset.display_name = req.display_name
    dataset.description = req.description
    db.commit()
    db.refresh(dataset)
    return _to_response(dataset)


# ── 共通ヘルパー ──────────────────────────────────────────────────
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
            "source_id": meta.get("source_id", ""),
            "source_data": meta.get("source_data", ""),
            "created_at": meta.get("created_at", ""),
        })
    return docs


def _build_md_block(doc: dict) -> list:
    lines = []
    lines.append(f"## {doc['id']}")
    lines.append("")
    if doc.get("title"):
        lines.append(f"**title:** {doc['title']}")
    if doc.get("source_id"):
        lines.append(f"**source_id:** {doc['source_id']}")
    if doc.get("source_data"):
        lines.append(f"**source_data:** {doc['source_data']}")
    if doc.get("created_at"):
        lines.append(f"**created_at:** {doc['created_at']}")
    lines.append("")
    lines.append(doc["content"])
    lines.append("")
    lines.append("---")
    lines.append("")
    return lines


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
        lines.extend(_build_md_block(doc))
    return "\n".join(lines)


def _parse_md(text: str) -> tuple:
    lines = text.split("\n")
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
    current_dataset_name = None
    results = []
    blocks = body.split("\n---")

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        for line in block.splitlines():
            m = _re.match(r'^#\s+dataset_name:\s+(.+)$', line.strip())
            if m:
                current_dataset_name = m.group(1).strip()

        id_match = _re.search(r'^##\s+(.+)$', block, _re.MULTILINE)
        if not id_match:
            continue

        doc_id = id_match.group(1).strip()
        rest = block[id_match.end():].strip()

        title = source_id = source_data = created_at = ""

        for key in ["title", "source_id", "source_data", "created_at"]:
            m = _re.match(rf'^\*\*{key}:\*\*\s*(.+)$', rest, _re.MULTILINE)
            if m:
                val = m.group(1).strip()
                if key == "title":
                    title = val
                elif key == "source_id":
                    source_id = val
                elif key == "source_data":
                    source_data = val
                elif key == "created_at":
                    created_at = val
                rest = rest[m.end():].strip()

        content = rest.strip()
        if not content:
            continue

        results.append({
            "dataset_name": current_dataset_name,
            "id": doc_id,
            "title": title,
            "source_id": source_id,
            "source_data": source_data,
            "created_at": created_at,
            "content": content,
        })

    return md_type, results


def _upsert_docs(collection, docs: list) -> tuple:
    import uuid
    imported = skipped = 0
    for doc in docs:
        content = doc["content"]
        if not content or len(content) > 700:
            skipped += 1
            continue
        doc_id = doc["id"]
        meta = [{
            "title": doc.get("title", ""),
            "source_id": doc.get("source_id", "") or str(uuid.uuid4()),
            "source_data": doc.get("source_data", ""),
            "created_at": doc.get("created_at", ""),
        }]
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


# ── スナップショット ──────────────────────────────────────────────
def _save_snapshot(md_text: str, filename: str):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_text)


def _snapshot_dataset(dataset, db):
    docs = _get_docs_from_collection(dataset)
    md_text = _build_md(dataset, docs, export_type="project")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    _save_snapshot(md_text, f"snapshot_{dataset.name}_{now_str}.md")


def _snapshot_all(db):
    datasets = db.query(Dataset).order_by(Dataset.id).all()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d_%H%M%S")
    lines = ["---", "type: full", f"exported_at: {now}", "---", ""]
    for dataset in datasets:
        docs = _get_docs_from_collection(dataset)
        lines.append(f"# project: {dataset.display_name}")
        lines.append(f"# dataset_name: {dataset.name}")
        lines.append("")
        for doc in docs:
            lines.extend(_build_md_block(doc))
        lines.append("")
    _save_snapshot("\n".join(lines), f"snapshot_full_{now_str}.md")


# ── エクスポート（全体）──────────────────────────────────────────
@router.get("/export/all")
def export_all_datasets(
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    datasets = db.query(Dataset).order_by(Dataset.id).all()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    now_str = now[:10]
    lines = ["---", "type: full", f"exported_at: {now}", "---", ""]
    for dataset in datasets:
        docs = _get_docs_from_collection(dataset)
        lines.append(f"# project: {dataset.display_name}")
        lines.append(f"# dataset_name: {dataset.name}")
        lines.append("")
        for doc in docs:
            lines.extend(_build_md_block(doc))
        lines.append("")
    md_text = "\n".join(lines)
    filename = f"llamune_backup_{now_str}.md"
    return FastAPIResponse(
        content=md_text.encode("utf-8"),
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── インポート（全体）────────────────────────────────────────────
@router.post("/import/all", status_code=200)
async def import_all_datasets(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb

    raw = await file.read()
    text = raw.decode("utf-8")
    md_type, docs = _parse_md(text)
    if md_type != "full":
        raise HTTPException(status_code=400, detail="全体バックアップファイルを選択してください。プロジェクト単位のファイルはリストアに使用できません")

    _snapshot_all(db)

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    total_imported = total_skipped = 0
    not_found = set()

    docs_by_ds: dict = {}
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


# ── エクスポート（プロジェクト単位）──────────────────────────────
@router.get("/{dataset_id}/export")
def export_dataset(
    dataset_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
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


# ── インポート（プロジェクト単位）────────────────────────────────
@router.post("/{dataset_id}/import", status_code=200)
async def import_dataset(
    dataset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    import chromadb

    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        raise HTTPException(status_code=404, detail="データセットが見つかりません")

    raw = await file.read()
    text = raw.decode("utf-8")
    md_type, docs = _parse_md(text)
    if md_type != "project":
        raise HTTPException(status_code=400, detail="プロジェクト単位のバックアップファイルを選択してください（全体バックアップは使用できません）")

    ds_names = {doc.get("dataset_name") for doc in docs if doc.get("dataset_name")}
    if ds_names and dataset.name not in ds_names:
        raise HTTPException(status_code=400, detail=f"このファイルは別のデータセット（{', '.join(ds_names)}）のバックアップです")

    _snapshot_dataset(dataset, db)

    client = chromadb.PersistentClient(path=CHROMA_DB_DIR)
    collection = client.get_or_create_collection(dataset.name)
    imported, skipped = _upsert_docs(collection, docs)
    return {"imported": imported, "skipped": skipped}
