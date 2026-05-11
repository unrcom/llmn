import json
import os
import subprocess
import tempfile
import threading
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy import create_engine, text
from pydantic import BaseModel
from typing import Optional, List
from app.db.database import get_db
from app.core.config import DATABASE_URL
from app.core.auth import get_current_user
from app.core.llm import _detect_backend
from app.models.base import Project, Model, TrainingJob, FtConversation

router = APIRouter(prefix="/training-jobs", tags=["training_jobs"])


class TrainingJobCreate(BaseModel):
    project_id: int
    models_id: int
    training_mode: int = 2
    max_seq_length: int = 8192
    iters: int = 100
    batch_size: int = 1
    learning_rate: Optional[float] = None


class TrainingJobResponse(BaseModel):
    id: int
    project_id: int
    models_id: int
    status: str
    training_mode: int
    max_seq_length: int
    iters: int
    batch_size: int
    learning_rate: Optional[float]
    adapter_path: Optional[str]
    error_message: Optional[str]
    log: Optional[str]
    started_at: Optional[str]
    finished_at: Optional[str]
    created_at: str


def _to_response(job: TrainingJob) -> TrainingJobResponse:
    return TrainingJobResponse(
        id=job.id,
        project_id=job.project_id,
        models_id=job.models_id,
        status=job.status,
        training_mode=job.training_mode,
        max_seq_length=job.max_seq_length,
        iters=job.iters,
        batch_size=job.batch_size,
        learning_rate=job.learning_rate,
        adapter_path=job.adapter_path,
        error_message=job.error_message,
        log=job.log,
        started_at=job.started_at.isoformat() if job.started_at else None,
        finished_at=job.finished_at.isoformat() if job.finished_at else None,
        created_at=job.created_at.isoformat(),
    )


def _build_jsonl(db: Session, project_id: int, split: str) -> str:
    convs = db.query(FtConversation).filter(
        FtConversation.project_id == project_id,
        FtConversation.is_base == False,
        FtConversation.split == split,
    ).order_by(FtConversation.created_at.asc()).all()

    lines = []
    for conv in convs:
        base_messages = []
        if conv.base_id:
            base = db.query(FtConversation).filter(FtConversation.id == conv.base_id).first()
            if base:
                base_messages = base.messages
        messages = base_messages + conv.messages
        lines.append(json.dumps({"messages": messages}, ensure_ascii=False))
    return "\n".join(lines)


def _run_training(job_id: int, model_name: str, train_data: str, valid_data: str,
                  max_seq_length: int, iters: int, batch_size: int,
                  learning_rate: Optional[float]):
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        db.execute(text("SET search_path TO llmn"))
        job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
        if not job:
            return

        job.status = "running"
        job.started_at = datetime.utcnow()
        job.log = ""
        db.commit()

        import shutil
        adapter_path = os.path.expanduser(f"~/llmn_adapters/{job_id}")
        if os.path.exists(adapter_path):
            shutil.rmtree(adapter_path)
        os.makedirs(adapter_path, exist_ok=True)

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "train.jsonl"), "w") as f:
                f.write(train_data)
            with open(os.path.join(tmpdir, "valid.jsonl"), "w") as f:
                f.write(valid_data if valid_data else train_data)

            is_vlm = (_detect_backend(model_name) == "mlx_vlm")

            if is_vlm:
                output_file = os.path.join(adapter_path, "adapters.safetensors")
                cmd = [
                    "python", "-m", "mlx_vlm.lora",
                    "--model-path", model_name,
                    "--dataset", tmpdir,
                    "--split", "all",
                    "--iters", str(iters),
                    "--batch-size", str(batch_size),
                    "--max-seq-length", str(max_seq_length),
                    "--output-path", output_file,
                ]
                if learning_rate:
                    cmd += ["--learning-rate", str(learning_rate)]
            else:
                cmd = [
                    "mlx_lm.lora",
                    "--model", model_name,
                    "--train",
                    "--data", tmpdir,
                    "--max-seq-length", str(max_seq_length),
                    "--iters", str(iters),
                    "--batch-size", str(batch_size),
                    "--adapter-path", adapter_path,
                ]
                if learning_rate:
                    cmd += ["--learning-rate", str(learning_rate)]

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            log_lines = []
            for line in process.stdout:
                line = line.rstrip()
                if line:
                    log_lines.append(line)
                    if len(log_lines) % 5 == 0:
                        job.log = "\n".join(log_lines)
                        db.commit()

            process.wait()
            job.log = "\n".join(log_lines)
            job.finished_at = datetime.utcnow()

            if process.returncode == 0:
                job.status = "completed"
                job.adapter_path = adapter_path
                db.commit()

                # FT済みモデルを自動登録
                base_model = db.query(Model).filter(Model.id == job.models_id).first()
                if base_model:
                    ft_model = Model(
                        name=base_model.name,
                        display_name=f"{base_model.display_name} FT #{job.id}",
                        model_type="fine-tuned",
                        adapter_path=adapter_path,
                        parent_models_id=base_model.id,
                        trained_at=datetime.utcnow(),
                    )
                    db.add(ft_model)
                    db.commit()
            else:
                job.status = "failed"
                job.error_message = "mlx_lm.lora が異常終了しました"
                db.commit()

    except Exception as e:
        try:
            job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
            if job:
                job.status = "failed"
                job.error_message = str(e)
                job.finished_at = datetime.utcnow()
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
        engine.dispose()


@router.get("", response_model=List[TrainingJobResponse])
def get_training_jobs(
    project_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    jobs = db.query(TrainingJob).filter(
        TrainingJob.project_id == project_id
    ).order_by(TrainingJob.created_at.desc()).all()
    return [_to_response(j) for j in jobs]


@router.get("/{job_id}", response_model=TrainingJobResponse)
def get_training_job(
    job_id: int,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    job = db.query(TrainingJob).filter(TrainingJob.id == job_id).first()
    if not job:
        raise HTTPException(status_code=404, detail="ジョブが見つかりません")
    return _to_response(job)


@router.post("", response_model=TrainingJobResponse, status_code=201)
def create_and_start_training_job(
    req: TrainingJobCreate,
    db: Session = Depends(get_db),
    _=Depends(get_current_user),
):
    project = db.query(Project).filter(Project.id == req.project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="プロジェクトが見つかりません")

    model = db.query(Model).filter(Model.id == req.models_id).first()
    if not model:
        raise HTTPException(status_code=404, detail="モデルが見つかりません")

    train_data = _build_jsonl(db, req.project_id, "train")
    valid_data = _build_jsonl(db, req.project_id, "valid")

    if not train_data:
        raise HTTPException(status_code=400, detail="trainデータがありません")

    job = TrainingJob(
        project_id=req.project_id,
        models_id=req.models_id,
        status="pending",
        training_mode=req.training_mode,
        max_seq_length=req.max_seq_length,
        iters=req.iters,
        batch_size=req.batch_size,
        learning_rate=req.learning_rate,
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    thread = threading.Thread(
        target=_run_training,
        args=(
            job.id, model.name, train_data, valid_data,
            req.max_seq_length, req.iters, req.batch_size, req.learning_rate,
        ),
        daemon=True,
    )
    thread.start()

    return _to_response(job)
