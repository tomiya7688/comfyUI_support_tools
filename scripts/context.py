
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Tabbed Tools GUI

各種ツールを Tkinter のタブでまとめて扱う単一ファイル版です。
flat_file_copy、random_image_creater、tag_deleter、start_webui、text_marger
などの主要処理をこのファイルに内包しています。

Stable Diffusion 本体、ffmpeg、7-Zip、Pillow、requests は別途必要です。
"""
from __future__ import annotations

import atexit
import base64
import contextlib
import io
import json
import os
import queue
import random
import re
import secrets
import signal
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import tkinter as tk
from tkinter import filedialog, ttk
from tkinter.scrolledtext import ScrolledText

try:
    import psutil
    _HAS_PSUTIL = True
except Exception:
    _HAS_PSUTIL = False

try:
    import requests
except Exception:
    requests = None


# =========================
# 共通部品
# =========================

APP_DIR = Path(__file__).resolve().parent.parent
USER_DATA_DIR = APP_DIR / "user_data"
USER_INPUT_DIR = USER_DATA_DIR / "input"
COMMON_CONFIG_DIR = USER_INPUT_DIR / "config" / "common"
USER_DATA_FILE = COMMON_CONFIG_DIR / "paths.json"
LEGACY_USER_DATA_FILE = USER_DATA_DIR / "paths.json"


def _load_user_paths():
    defaults = {
        "sd_root": str(APP_DIR),
        "models_root": str(APP_DIR / "models"),
        "checkpoints": str(APP_DIR / "models" / "checkpoints"),
        "comfy_flows": str(APP_DIR / "models" / "flows"),
        "wildcards": str(APP_DIR / "wildcards"),
        "a1111_dir": str(APP_DIR / "stable-diffusion-webui"),
        "comfyui_dir": str(APP_DIR / "ComfyUI"),
        "pixai_tagger_dir": str(APP_DIR / "pixai_tagger" / "pixai-tagger-v0.9-demo"),
        "taggui_dir": str(APP_DIR / "taggui"),
        "taggui_exe": str(APP_DIR / "taggui-v1.34.0-windows" / "taggui.exe"),
        "webui_api_url": "http://127.0.0.1:7860",
        "comfyui_api_url": "http://127.0.0.1:8188",
        "pixai_api_url": "http://127.0.0.1:7861/pixai/v1/interrogate",
        "flat_copy_input_dir": "",
        "flat_copy_output_dir": "",
        "text_merger_folder": "",
        "screenshot_input_dir": "",
        "screenshot_output_dir": "",
        "zipper_input_dir": "",
        "zipper_output_dir": "",
        "seven_zip_exe": "",
        "images_to_webp_input_dir": "",
        "ffmpeg_input_file": "",
        "ffmpeg_output_file": "",
        "random_img2img_input_dir": "",
        "youtube_downloader_dir": r"I:\scripts\youtubez_downloader",
        "nuno_touka_dir": r"K:\sd\nuno\_touka",
    }
    try:
        source_path = USER_DATA_FILE if USER_DATA_FILE.is_file() else LEGACY_USER_DATA_FILE
        with source_path.open("r", encoding="utf-8") as source:
            values = json.load(source)
        if not isinstance(values, dict):
            values = {}
    except (FileNotFoundError, OSError, ValueError):
        values = {}
    return {**defaults, **values}


USER_PATHS = _load_user_paths()


def _configured_path(key, environment_key, fallback):
    return Path(os.environ.get(environment_key, USER_PATHS.get(key, fallback))).expanduser().resolve()


SD_ROOT = _configured_path("sd_root", "KADOKA_TOOLS_SD_ROOT", str(APP_DIR))


def _backend_from_command_line():
    for index, value in enumerate(sys.argv):
        if value == "--backend" and index + 1 < len(sys.argv):
            return sys.argv[index + 1].strip().lower()
        if value.startswith("--backend="):
            return value.split("=", 1)[1].strip().lower()
    return ""


_backend_environment = os.environ.get("KADOKA_TOOLS_BACKEND", "").strip().lower()
_backend_argument = _backend_from_command_line()
BACKEND_SELECTION_REQUIRED = not (_backend_environment or _backend_argument)
RUNTIME_BACKEND = _backend_argument or _backend_environment or "a1111"
if RUNTIME_BACKEND not in {"a1111", "comfyui"}:
    RUNTIME_BACKEND = "a1111"
A1111_DIR = _configured_path("a1111_dir", "KADOKA_TOOLS_A1111_DIR", str(SD_ROOT / "stable-diffusion-webui"))
COMFYUI_DIR = _configured_path("comfyui_dir", "KADOKA_TOOLS_COMFYUI_DIR", str(SD_ROOT / "ComfyUI"))
RUNTIME_DIR = Path(os.environ.get(
    "KADOKA_TOOLS_RUNTIME_DIR",
    str(COMFYUI_DIR if RUNTIME_BACKEND == "comfyui" else A1111_DIR),
)).resolve()
BACKEND_DISPLAY_NAME = "ComfyUI" if RUNTIME_BACKEND == "comfyui" else "WebUI1111"
USER_INPUT_DIR = _configured_path("input_root", "KADOKA_TOOLS_INPUT_ROOT", str(USER_INPUT_DIR))
INPUT_MODELS_DIR = _configured_path("input_models", "KADOKA_TOOLS_INPUT_MODELS", str(USER_INPUT_DIR / "models"))
MODELS_DIR = _configured_path("models_root", "KADOKA_TOOLS_MODELS_ROOT", str(INPUT_MODELS_DIR))
CHECKPOINTS_DIR = _configured_path("checkpoints", "KADOKA_TOOLS_CHECKPOINTS_DIR", str(MODELS_DIR / "checkpoints"))
COMFY_FLOWS_DIR = _configured_path("comfy_flows", "KADOKA_TOOLS_COMFY_FLOWS_DIR", str(MODELS_DIR / "flows"))
WILDCARDS_DIR = _configured_path("wildcards", "KADOKA_TOOLS_WILDCARDS_DIR", str(SD_ROOT / "wildcards"))
PIXAI_TAGGER_DIR = _configured_path("pixai_tagger_dir", "KADOKA_TOOLS_PIXAI_TAGGER_DIR", str(SD_ROOT / "pixai_tagger" / "pixai-tagger-v0.9-demo"))
TAGGUI_DIR = _configured_path("taggui_dir", "KADOKA_TOOLS_TAGGUI_DIR", str(SD_ROOT / "taggui"))
TAGGUI_PACKAGED_EXE = _configured_path("taggui_exe", "KADOKA_TOOLS_TAGGUI_EXE", str(SD_ROOT / "taggui-v1.34.0-windows" / "taggui.exe"))
YOUTUBE_DOWNLOADER_DIR = _configured_path("youtube_downloader_dir", "KADOKA_TOOLS_YOUTUBE_DOWNLOADER_DIR", r"I:\scripts\youtubez_downloader")
NUNO_TOUKA_DIR = _configured_path("nuno_touka_dir", "KADOKA_TOOLS_NUNO_TOUKA_DIR", r"K:\sd\nuno\_touka")
PIXAI_TAGGER_API_URL = str(USER_PATHS.get("pixai_api_url", "http://127.0.0.1:7861/pixai/v1/interrogate"))
PIXAI_TAGGER_MODEL = "deepghs/pixai-tagger-v0.9-onnx"


def _load_pillow_image():
    """WebUIの依存関係更新とDLLロックが競合しないよう、Pillowは使用時だけ読む。"""
    try:
        from PIL import Image as pillow_image
    except Exception as exc:
        raise RuntimeError("Pillow がインポートできません") from exc
    return pillow_image

MODEL_FILE_SUFFIXES = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".onnx"}
A1111_SAMPLER_CHOICES = [
    "Euler a", "Euler", "DPM++ 2M", "DPM++ 2M Karras",
    "DPM++ SDE", "DPM++ SDE Karras", "DDIM", "UniPC",
]
COMFYUI_SAMPLER_CHOICES = [
    "euler", "euler_ancestral", "heun", "dpm_2", "dpm_2_ancestral",
    "dpmpp_2m", "dpmpp_2m_sde", "dpmpp_sde", "dpmpp_3m_sde",
    "ddim", "uni_pc",
]
A1111_UPSCALER_CHOICES = [
    "None", "Lanczos", "Nearest", "Latent", "Latent (antialiased)",
    "R-ESRGAN 4x+", "R-ESRGAN 4x+ Anime6B",
]


def _unique_choices(values):
    result = []
    seen = set()
    for value in values:
        if value is None:
            continue
        value = str(value).strip()
        key = value.casefold()
        if value and key not in seen:
            seen.add(key)
            result.append(value)
    return result


def _scan_model_files(root, *, keep_suffix=True):
    root = Path(root)
    if not root.is_dir():
        return []
    result = []
    try:
        paths = sorted(
            (path for path in root.rglob("*") if path.is_file()),
            key=lambda path: path.as_posix().casefold(),
        )
    except OSError:
        return result
    for path in paths:
        if path.suffix.lower() not in MODEL_FILE_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if not keep_suffix:
            relative = relative.with_suffix("")
        result.append(relative.as_posix())
    return result


def _scan_flow_files(root):
    root = Path(root)
    if not root.is_dir():
        return []
    try:
        return [path.relative_to(root).as_posix() for path in sorted(root.rglob("*.json"), key=lambda p: p.as_posix().casefold()) if path.is_file()]
    except OSError:
        return []


def flow_checkpoint_choices(flow_name):
    """選択中のComfyUI API workflowに記載されたcheckpoint／UNet候補を返す。"""
    if not flow_name:
        return []
    path = Path(flow_name)
    if not path.is_absolute():
        path = COMFY_FLOWS_DIR / path
    try:
        with path.open(encoding="utf-8") as source:
            workflow = json.load(source)
    except (OSError, ValueError):
        return []
    values = []
    loader_inputs = {"CheckpointLoaderSimple": "ckpt_name", "UNETLoader": "unet_name"}
    nodes = workflow.get("nodes", []) if isinstance(workflow.get("nodes"), list) else workflow.values()
    for node in nodes:
        if isinstance(node, dict):
            input_name = loader_inputs.get(node.get("class_type") or node.get("type"))
            raw_inputs = node.get("inputs", {})
            value = raw_inputs.get(input_name) if input_name and isinstance(raw_inputs, dict) else None
            if input_name and value is None and isinstance(node.get("widgets_values"), list):
                widget_index = 0
                for item in node.get("inputs", []):
                    if "widget" not in item:
                        continue
                    if item.get("name") == input_name and widget_index < len(node["widgets_values"]):
                        value = node["widgets_values"][widget_index]
                        break
                    widget_index += 1
            if value and str(value).strip() and str(value).strip() not in values:
                values.append(str(value).strip())
    return values
def _local_backend_choices():
    if RUNTIME_BACKEND == "comfyui":
        return {
            "checkpoints": _unique_choices(
                _scan_model_files(CHECKPOINTS_DIR)
                + _scan_model_files(SD_ROOT / "models" / "diffusion_models")
                + _scan_model_files(RUNTIME_DIR / "models" / "diffusion_models")
            ),
            "upscalers": _scan_model_files(RUNTIME_DIR / "models" / "upscale_models"),
            "samplers": list(COMFYUI_SAMPLER_CHOICES),
            "flows": _scan_flow_files(COMFY_FLOWS_DIR),
        }

    model_root = RUNTIME_DIR / "models"
    upscalers = list(A1111_UPSCALER_CHOICES)
    for folder_name in ("ESRGAN", "RealESRGAN", "SwinIR", "LDSR", "ScuNET", "BSRGAN"):
        upscalers.extend(_scan_model_files(model_root / folder_name, keep_suffix=False))
    return {
        "checkpoints": _scan_model_files(CHECKPOINTS_DIR),
        "upscalers": _unique_choices(upscalers),
        "samplers": list(A1111_SAMPLER_CHOICES),
        "flows": [],
    }


def _comfy_input_choices(payload, node_name, input_name):
    node_info = payload.get(node_name, payload) if isinstance(payload, dict) else {}
    spec = node_info.get("input", {}).get("required", {}).get(input_name, [])
    if isinstance(spec, (list, tuple)) and spec and isinstance(spec[0], (list, tuple)):
        return [str(value) for value in spec[0]]
    return []


def load_backend_choices(api_url="", query_api=False):
    """ローカルのモデル候補に、起動中APIの正確な登録名を統合する。"""
    local = _local_backend_choices()
    api_choices = {"checkpoints": [], "upscalers": [], "samplers": [], "flows": []}
    warnings = []
    if query_api:
        if requests is None:
            warnings.append("requests が未インストールのためAPI候補を取得できません")
        else:
            base_url = api_url.strip().rstrip("/")
            if RUNTIME_BACKEND == "a1111" and "/sdapi/" in base_url:
                base_url = base_url.split("/sdapi/", 1)[0]
            if not base_url:
                warnings.append("API URLが空です")
            elif RUNTIME_BACKEND == "comfyui":
                specs = (
                    ("checkpoints", "CheckpointLoaderSimple", "ckpt_name"),
                    ("upscalers", "UpscaleModelLoader", "model_name"),
                    ("samplers", "KSampler", "sampler_name"),
                )
                for key, node_name, input_name in specs:
                    try:
                        response = requests.get(f"{base_url}/object_info/{node_name}", timeout=5)
                        response.raise_for_status()
                        api_choices[key].extend(
                            _comfy_input_choices(response.json(), node_name, input_name)
                        )
                    except Exception as exc:
                        warnings.append(f"{node_name}: {exc}")
            else:
                specs = (
                    ("checkpoints", "sd-models", ("title", "model_name", "filename")),
                    ("upscalers", "upscalers", ("name",)),
                    ("samplers", "samplers", ("name",)),
                )
                for key, endpoint, fields in specs:
                    try:
                        response = requests.get(f"{base_url}/sdapi/v1/{endpoint}", timeout=5)
                        response.raise_for_status()
                        for item in response.json():
                            if not isinstance(item, dict):
                                continue
                            value = next((item.get(field) for field in fields if item.get(field)), None)
                            if value:
                                api_choices[key].append(str(value))
                    except Exception as exc:
                        warnings.append(f"{endpoint}: {exc}")

    merged = {
        key: _unique_choices(api_choices[key] + local[key])
        for key in ("checkpoints", "upscalers", "samplers", "flows")
    }
    return merged, warnings


def extract_tagger_tags(result):
    caption = result.get("caption", result) if isinstance(result, dict) else result
    if isinstance(caption, str):
        return [tag.strip() for tag in caption.split(",") if tag.strip()]
    if isinstance(caption, list):
        return [str(tag).strip() for tag in caption if str(tag).strip()]
    if isinstance(caption, dict):
        tag_data = caption.get("tag", caption)
        if isinstance(tag_data, str):
            return [tag.strip() for tag in tag_data.split(",") if tag.strip()]
        if isinstance(tag_data, dict):
            return [str(tag).strip() for tag in tag_data if str(tag).strip()]
    if isinstance(result, dict):
        tag_data = result.get("tags", {}).get("tag", {})
        if isinstance(tag_data, dict):
            return [str(tag).strip() for tag in tag_data if str(tag).strip()]
    raise RuntimeError(f"未対応のTagger応答形式です: {str(result)[:300]}")




def _safe_thread(logbox, func, *args, **kwargs):
    def runner():
        try:
            func(*args, **kwargs)
        except Exception as exc:
            try:
                logbox.log(f'❌ エラー発生: {type(exc).__name__}: {exc}')
            except Exception:
                print(f'ERROR: {type(exc).__name__}: {exc}')
    import threading
    threading.Thread(target=runner, daemon=True).start()
