
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


# {
#   責務: [
#     _default_user_paths: 指定したアプリ配置場所に対する既定パスを構築する
#   ]
#   処理: [
#     1: アプリ配置場所をPathとして正規化する
#     2: 各機能の既定パスを構築して返す
#   ]
#   引数: [
#     app_dir: 既定値の起点。省略時は現在のAPP_DIRを使用する
#   ]
#   戻り値: [
#     user_paths: 設定キーと既定パスの対応
#   ]
# }
def _default_user_paths(app_dir=None):
    """Build portable defaults relative to the checked-out application folder."""
    app_dir = Path(APP_DIR if app_dir is None else app_dir)
    return {
        "sd_root": str(app_dir),
        "models_root": str(app_dir / "user_data" / "input" / "models"),
        "checkpoints": str(app_dir / "user_data" / "input" / "models" / "checkpoints"),
        "comfy_flows": str(app_dir / "user_data" / "input" / "models" / "flows"),
        "wildcards": str(app_dir / "wildcards"),
        "a1111_dir": str(app_dir / "external" / "stable-diffusion-webui"),
        "comfyui_dir": str(app_dir / "external" / "ComfyUI"),
        "pixai_tagger_dir": str(app_dir / "external" / "pixai_tagger" / "pixai-tagger-v0.9-demo"),
        "taggui_dir": str(app_dir / "external" / "taggui"),
        "taggui_exe": str(app_dir / "external" / "taggui-v1.34.0-windows" / "taggui.exe"),
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
        "youtube_downloader_dir": str(app_dir / "external" / "youtubez_downloader"),
        "nuno_touka_dir": str(app_dir / "nuno" / "_touka"),
    }


def _load_user_paths():
    defaults = _default_user_paths()
    try:
        source_path = USER_DATA_FILE if USER_DATA_FILE.is_file() else LEGACY_USER_DATA_FILE
        with source_path.open("r", encoding="utf-8") as source:
            values = json.load(source)
        if not isinstance(values, dict):
            values = {}
    except (FileNotFoundError, OSError, ValueError):
        values = {}
    result = {**defaults, **values}
    if "models_root" not in values and "input_models" in values:
        result["models_root"] = values["input_models"]
    if "checkpoints" not in values:
        result["checkpoints"] = str(Path(result["models_root"]) / "checkpoints")
    if "comfy_flows" not in values:
        result["comfy_flows"] = str(Path(result["models_root"]) / "flows")
    return result


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


def _api_only_from_command_line():
    return any(value == "--api-only" for value in sys.argv)


_backend_environment = os.environ.get("KADOKA_TOOLS_BACKEND", "").strip().lower()
_backend_argument = _backend_from_command_line()
API_ONLY_MODE = _api_only_from_command_line() or os.environ.get("KADOKA_TOOLS_API_ONLY", "").strip() == "1"
BACKEND_SELECTION_REQUIRED = not (_backend_environment or _backend_argument)
RUNTIME_BACKEND = _backend_argument or _backend_environment or "a1111"
if RUNTIME_BACKEND not in {"a1111", "comfyui"}:
    RUNTIME_BACKEND = "a1111"
A1111_DIR = _configured_path("a1111_dir", "KADOKA_TOOLS_A1111_DIR", str(SD_ROOT / "external" / "stable-diffusion-webui"))
COMFYUI_DIR = _configured_path("comfyui_dir", "KADOKA_TOOLS_COMFYUI_DIR", str(SD_ROOT / "external" / "ComfyUI"))
RUNTIME_DIR = Path(os.environ.get(
    "KADOKA_TOOLS_RUNTIME_DIR",
    str(COMFYUI_DIR if RUNTIME_BACKEND == "comfyui" else A1111_DIR),
)).resolve()
BACKEND_DISPLAY_NAME = "ComfyUI" if RUNTIME_BACKEND == "comfyui" else "WebUI1111"
USER_INPUT_DIR = _configured_path("input_root", "KADOKA_TOOLS_INPUT_ROOT", str(USER_INPUT_DIR))
INPUT_MODELS_DIR = _configured_path("input_models", "KADOKA_TOOLS_INPUT_MODELS", str(USER_INPUT_DIR / "models"))
MODELS_DIR = _configured_path("models_root", "KADOKA_TOOLS_MODELS_ROOT", str(INPUT_MODELS_DIR))
LEGACY_MODELS_DIR = APP_DIR / "models"
CHECKPOINTS_DIR = _configured_path("checkpoints", "KADOKA_TOOLS_CHECKPOINTS_DIR", str(MODELS_DIR / "checkpoints"))
LEGACY_CHECKPOINTS_DIRS = (LEGACY_MODELS_DIR / "checkpoints", APP_DIR / "checkpoints")
COMFY_FLOWS_DIR = _configured_path("comfy_flows", "KADOKA_TOOLS_COMFY_FLOWS_DIR", str(MODELS_DIR / "flows"))
WILDCARDS_DIR = _configured_path("wildcards", "KADOKA_TOOLS_WILDCARDS_DIR", str(SD_ROOT / "wildcards"))
PIXAI_TAGGER_DIR = _configured_path("pixai_tagger_dir", "KADOKA_TOOLS_PIXAI_TAGGER_DIR", str(SD_ROOT / "external" / "pixai_tagger" / "pixai-tagger-v0.9-demo"))
TAGGUI_DIR = _configured_path("taggui_dir", "KADOKA_TOOLS_TAGGUI_DIR", str(SD_ROOT / "external" / "taggui"))
TAGGUI_PACKAGED_EXE = _configured_path("taggui_exe", "KADOKA_TOOLS_TAGGUI_EXE", str(SD_ROOT / "external" / "taggui-v1.34.0-windows" / "taggui.exe"))
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


def resolve_comfy_flow_path(flow_name):
    """Resolve a workflow from the configured root, then its legacy location."""
    path = Path(flow_name)
    if path.is_absolute():
        return path
    configured = COMFY_FLOWS_DIR / path
    if configured.is_file():
        return configured
    legacy = LEGACY_MODELS_DIR / "flows" / path
    return legacy if legacy.is_file() else configured


def flow_checkpoint_choices(flow_name):
    """選択中のComfyUI API workflowに記載されたcheckpoint／UNet候補を返す。"""
    if not flow_name:
        return []
    path = resolve_comfy_flow_path(flow_name)
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


# {
#   責務: [base_model_choices: 選択中backendの主モデル候補をcatalogへ問い合わせる]
#   処理: [1: 選択中backendのGenerationBackendCatalogを生成する, 2: 候補mappingを渡して主モデル名を返す]
#   引数: [choices: checkpoint等を含む候補mapping]
#   戻り値: [list[str]: 選択中backendで主モデルとして利用可能な候補]
# }
def base_model_choices(choices):
    from .backend.generation_backend_catalog_factory import create_generation_backend_catalog

    catalog = create_generation_backend_catalog(RUNTIME_BACKEND)
    return catalog.primary_model_choices(choices)


# {
#   責務: [_local_backend_choices: 選択中backend catalogからローカル候補を取得する]
#   処理: [1: 共通パス設定をcatalog用ルートmappingへまとめる, 2: 選択中catalogへ走査関数とともに渡す]
#   引数: []
#   戻り値: [ChoiceMap: 選択中backendのローカル生成候補]
# }
def _local_backend_choices():
    from .backend.generation_backend_catalog_factory import create_generation_backend_catalog

    catalog = create_generation_backend_catalog(RUNTIME_BACKEND)
    roots = {
        "checkpoints": CHECKPOINTS_DIR,
        "legacy_checkpoints": LEGACY_CHECKPOINTS_DIRS,
        "models": MODELS_DIR,
        "legacy_models": LEGACY_MODELS_DIR,
        "runtime": RUNTIME_DIR,
        "a1111": A1111_DIR,
        "comfy_flows": COMFY_FLOWS_DIR,
    }
    return catalog.local_choices(roots, _scan_model_files, _scan_flow_files, _unique_choices)


def load_backend_choices(api_url="", query_api=False):
    """ローカルのモデル候補に、起動中APIの正確な登録名を統合する。"""
    local = _local_backend_choices()
    api_choices = {"checkpoints": [], "unets": [], "loras": [], "vaes": [], "upscalers": [], "samplers": [], "flows": []}
    warnings = []
    if query_api:
        if requests is None:
            warnings.append("requests が未インストールのためAPI候補を取得できません")
        else:
            base_url = api_url.strip().rstrip("/")
            if not base_url:
                warnings.append("API URLが空です")
            else:
                from .backend.generation_backend_catalog_factory import create_generation_backend_catalog

                catalog = create_generation_backend_catalog(RUNTIME_BACKEND)
                queried_choices, query_warnings = catalog.query_choices(base_url, requests.get)
                for key in ("checkpoints", "unets", "loras", "vaes", "upscalers", "samplers"):
                    api_choices[key].extend(queried_choices[key])
                warnings.extend(query_warnings)

    merged = {
        key: _unique_choices(api_choices[key] + local[key])
        for key in ("checkpoints", "unets", "loras", "vaes", "upscalers", "samplers", "flows")
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
