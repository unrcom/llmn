import re
import os
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import Optional, List
from app.core.auth import get_current_user
from app.core import llm

router = APIRouter(prefix="/validate", tags=["validate"])


class LoadRequest(BaseModel):
    model_name: str
    adapter_path: Optional[str] = None


class GenerateRequest(BaseModel):
    messages: list
    system_prompt: Optional[str] = None
    max_tokens: int = 512
    dataset_id: Optional[int] = None


class StatusResponse(BaseModel):
    loaded: bool
    model_name: Optional[str]
    adapter_path: Optional[str]


def _search_chroma(query: str, dataset_id: int, db) -> str:
    import chromadb
    from app.models.base import Dataset
    dataset = db.query(Dataset).filter(Dataset.id == dataset_id).first()
    if not dataset:
        return "検索結果なし"
    chroma_path = os.path.expanduser("~/dev/llmn/chroma_db")
    client = chromadb.PersistentClient(path=chroma_path)
    try:
        collection = client.get_collection(dataset.name)
        results = collection.query(query_texts=[query], n_results=3)
        docs = results.get("documents", [[]])[0]
        if not docs:
            return "検索結果なし"
        return "検索結果: [ " + ", ".join(docs) + " ]"
    except Exception as e:
        return f"検索エラー: {str(e)}"


@router.get("/status", response_model=StatusResponse)
def get_status(_=Depends(get_current_user)):
    return StatusResponse(
        loaded=llm.is_model_loaded(),
        model_name=llm.get_current_model_name(),
        adapter_path=llm.get_current_adapter_path(),
    )


@router.post("/load")
def load_model(req: LoadRequest, _=Depends(get_current_user)):
    try:
        llm.load_model(req.model_name, req.adapter_path)
        return {"ok": True, "model_name": req.model_name, "adapter_path": req.adapter_path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate")
def generate(req: GenerateRequest, _=Depends(get_current_user)):
    from app.db.database import get_db

    if not llm.is_model_loaded():
        raise HTTPException(status_code=400, detail="モデルがロードされていません")

    try:
        # メッセージ履歴を構築
        messages = []
        if req.system_prompt:
            messages.append({"role": "system", "content": req.system_prompt})
        messages.extend(req.messages)

        # 1回目の推論
        result = llm.generate_with_messages(messages, req.max_tokens)

        # [SEARCH]...[/SEARCH] を検出
        search_match = re.search(r'\[SEARCH\](.*?)\[/SEARCH\]', result)
        if search_match and req.dataset_id:
            query = search_match.group(1)

            # assistantメッセージ（検索トークン）を追加
            messages.append({"role": "assistant", "content": result})

            # ChromaDB検索
            db_gen = get_db()
            db = next(db_gen)
            search_result = _search_chroma(query, req.dataset_id, db)

            # toolメッセージを追加
            messages.append({"role": "tool", "content": f'"content": "{search_result}"'})

            # 2回目の推論（最終回答）
            result = llm.generate_with_messages(messages, req.max_tokens)

        return {"result": result, "messages": messages}

    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/system-prompt/{model_id}")
def get_model_system_prompt(model_id: int, _=Depends(get_current_user)):
    from app.db.database import get_db
    from app.models.base import Model, TrainingJob, SystemPrompt
    db = next(get_db())
    model = db.query(Model).filter(Model.id == model_id).first()
    if not model or model.model_type != "fine-tuned":
        return {"system_prompt": None}
    job = db.query(TrainingJob).filter(TrainingJob.models_id == model.parent_models_id).first()
    if not job:
        return {"system_prompt": None}
    sp = db.query(SystemPrompt).filter(SystemPrompt.project_id == job.project_id).first()
    if not sp:
        return {"system_prompt": None}
    return {"system_prompt": sp.content}
