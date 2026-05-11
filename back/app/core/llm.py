import json
import threading
from pathlib import Path
from typing import Optional

from huggingface_hub import hf_hub_download

# mlx_vlm.generate をメインスレッドでインポートして generation_stream を初期化
try:
    from mlx_vlm import generate as _vlm_generate_init  # noqa: F401
except Exception:
    pass

_lock = threading.Lock()
_current_model_name: Optional[str] = None
_current_adapter_path: Optional[str] = None
_model = None
_tokenizer = None
_backend: Optional[str] = None  # "mlx_lm" or "mlx_vlm"

# mlx-vlm が必要な model_type のリスト
_VLM_MODEL_TYPES = {"gemma4"}


def _detect_backend(model_name: str) -> str:
    """config.json の model_type を見て使用するバックエンドを判定する"""
    try:
        config_path = hf_hub_download(model_name, "config.json")
        with open(config_path) as f:
            config = json.load(f)
        model_type = config.get("model_type", "")
        if model_type in _VLM_MODEL_TYPES:
            return "mlx_vlm"
    except Exception:
        pass
    return "mlx_lm"


def load_model(model_name: str, adapter_path: Optional[str] = None):
    global _current_model_name, _current_adapter_path, _model, _tokenizer, _backend
    with _lock:
        if _current_model_name == model_name and _current_adapter_path == adapter_path:
            return
        _backend = _detect_backend(model_name)
        print(f"🔄 Loading model: {model_name} (backend: {_backend})" + (f" adapter: {adapter_path}" if adapter_path else ""))
        if _backend == "mlx_vlm":
            from mlx_vlm import load
            _model, _tokenizer = load(model_name)
        else:
            from mlx_lm import load
            if adapter_path:
                _model, _tokenizer = load(model_name, adapter_path=adapter_path)
            else:
                _model, _tokenizer = load(model_name)
        _current_model_name = model_name
        _current_adapter_path = adapter_path
        print(f"✅ Model loaded: {model_name}" + (f" + adapter" if adapter_path else ""))


def _generate_impl(messages: list, max_tokens: int = 512) -> str:
    """バックエンドに応じた推論を実行する共通関数"""
    if _model is None or _tokenizer is None:
        raise RuntimeError("モデルがロードされていません")

    if _backend == "mlx_vlm":
        from mlx_vlm import generate as vlm_generate
        prompt = _tokenizer.tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        result_obj = vlm_generate(
            _model, _tokenizer, prompt, max_tokens=max_tokens
        )
        result = result_obj.text if hasattr(result_obj, 'text') else str(result_obj)
    else:
        from mlx_lm import generate as mlx_generate
        formatted = _tokenizer.apply_chat_template(
            messages, tokenize=False, add_generation_prompt=True
        )
        result = mlx_generate(
            _model, _tokenizer, prompt=formatted,
            max_tokens=max_tokens, verbose=False,
        )

    # gpt-ossのfinal出力を抽出
    if '<|channel|>final<|message|>' in result:
        result = result.split('<|channel|>final<|message|>')[-1]
        result = result.replace('<|end|>', '').strip()
    return result


def generate(prompt: str, system_prompt: Optional[str] = None, max_tokens: int = 512) -> str:
    with _lock:
        if system_prompt:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]
        else:
            messages = [{"role": "user", "content": prompt}]
        return _generate_impl(messages, max_tokens)


def get_current_model_name() -> Optional[str]:
    return _current_model_name


def get_current_adapter_path() -> Optional[str]:
    return _current_adapter_path


def is_model_loaded() -> bool:
    return _model is not None


def generate_with_messages(messages: list, max_tokens: int = 512) -> str:
    with _lock:
        return _generate_impl(messages, max_tokens)

