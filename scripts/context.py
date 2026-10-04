
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
#   "責務": "user paths JSONと既定値・旧key互換からpath設定をロードする。",
#   "処理": ["新形式またはlegacy JSONを読む", "不正時に既定値へ戻しmodels_root由来のpathを補完する"],
#   "引数": [], "戻り値": "有効なpath setting dict"
# }
def _load_user_paths():
    defaults = {
        "sd_root": str(APP_DIR),
        "models_root": str(APP_DIR / "user_data" / "input" / "models"),
        "checkpoints": str(APP_DIR / "user_data" / "input" / "models" / "checkpoints"),
        "comfy_flows": str(APP_DIR / "user_data" / "input" / "models" / "flows"),
        "wildcards": str(APP_DIR / "wildcards"),
        "a1111_dir": str(APP_DIR / "external" / "stable-diffusion-webui"),
        "comfyui_dir": str(APP_DIR / "external" / "ComfyUI"),
        "pixai_tagger_dir": str(APP_DIR / "external" / "pixai_tagger" / "pixai-tagger-v0.9-demo"),
        "taggui_dir": str(APP_DIR / "external" / "taggui"),
        "taggui_exe": str(APP_DIR / "external" / "taggui-v1.34.0-windows" / "taggui.exe"),
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
    result = {**defaults, **values}
    if "models_root" not in values and "input_models" in values:
        result["models_root"] = values["input_models"]
    if "checkpoints" not in values:
        result["checkpoints"] = str(Path(result["models_root"]) / "checkpoints")
    if "comfy_flows" not in values:
        result["comfy_flows"] = str(Path(result["models_root"]) / "flows")
    return result


USER_PATHS = _load_user_paths()


# {
#   "責務": "環境変数、user config、fallbackの優先順でpathを解決する。",
#   "処理": ["優先値を取得しuser expansionとabsolute resolveを行う"],
#   "引数": {"key": "user path key", "environment_key": "上書き環境変数名", "fallback": "最終既定値"}, "戻り値": "解決済みPath"
# }
def _configured_path(key, environment_key, fallback):
    return Path(os.environ.get(environment_key, USER_PATHS.get(key, fallback))).expanduser().resolve()


SD_ROOT = _configured_path("sd_root", "KADOKA_TOOLS_SD_ROOT", str(APP_DIR))


# {
#   "責務": "process argvから--backendの値を読み取る。",
#   "処理": ["分離引数と等号形式を走査し値を小文字化する"],
#   "引数": [], "戻り値": "backend名。未指定なら空文字"
# }
def _backend_from_command_line():
    for index, value in enumerate(sys.argv):
        if value == "--backend" and index + 1 < len(sys.argv):
            return sys.argv[index + 1].strip().lower()
        if value.startswith("--backend="):
            return value.split("=", 1)[1].strip().lower()
    return ""


# {
#   "責務": "argvにapi-only optionがあるかを判定する。",
#   "処理": ["argv itemとの完全一致を検査する"],
#   "引数": [], "戻り値": "option有無bool"
# }
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


# {
#   "責務": "必要時にPillow Image moduleを遅延importして依存競合を避ける。",
#   "処理": ["PIL.Imageをimportし失敗を利用者向けRuntimeErrorへ変換する"],
#   "引数": [], "戻り値": "Pillow Image module"
# }
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


# {
#   "責務": "入力候補を大文字小文字を区別せず重複排除する。",
#   "処理": ["空値を除きtrimした文字列を順序保持で重複排除する"],
#   "引数": {"values": "任意候補値のiterable"}, "戻り値": "一意な文字列list"
# }
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


# {
#   "責務": "root配下から対応model拡張子の相対file名を列挙する。",
#   "処理": ["directoryとfile accessを安全に検査する", "suffix filter後に相対pathを安定順で返す"],
#   "引数": {"root": "走査root", "keep_suffix": "suffixを返却名に残すか"}, "戻り値": "相対model path list"
# }
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


# {
#   "責務": "root配下のJSON workflow fileを相対pathで列挙する。",
#   "処理": ["directoryを検証しJSON fileをcase-insensitive安定順で走査する"],
#   "引数": {"root": "workflow走査root"}, "戻り値": "相対flow path list"
# }
def _scan_flow_files(root):
    root = Path(root)
    if not root.is_dir():
        return []
    try:
        return [path.relative_to(root).as_posix() for path in sorted(root.rglob("*.json"), key=lambda p: p.as_posix().casefold()) if path.is_file()]
    except OSError:
        return []


# {
#   "責務": "ComfyUI workflow名をconfigured rootまたはlegacy root配下のfileへ解決する。",
#   "処理": ["absolute pathをそのまま扱う", "configured候補を優先し存在しなければlegacy候補を使う"],
#   "引数": {"flow_name": "workflow名またはpath"}, "戻り値": "解決されたPath"
# }
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


# {
#   "責務": "workflow JSONからcheckpoint loaderとUNet loaderの選択値を抽出する。",
#   "処理": ["flowを解決・parseする", "API形式またはnode widget形式のloader値を重複なく収集する"],
#   "引数": {"flow_name": "workflow名またはpath"}, "戻り値": "model名list。未読込なら空list"
# }
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
#   "責務": "active backendでprimary base modelとして選択可能な候補を返す。",
#   "処理": ["checkpointを取得しComfyUI時だけUNetを加えて重複排除する"],
#   "引数": {"choices": "backend候補dict"}, "戻り値": "一意なbase model名list"
# }
def base_model_choices(choices):
    """Return models selectable as the primary base in the active backend."""
    models = list(choices.get("checkpoints", []))
    if RUNTIME_BACKEND == "comfyui":
        models.extend(choices.get("unets", []))
    return _unique_choices(models)


# {
#   "責務": "選択backendのmodel/upscaler/sampler/flowをローカルfile systemから列挙する。",
#   "処理": ["backend別directoryを走査する", "legacy/runtime model locationを統合しbackend候補dictを作る"],
#   "引数": [], "戻り値": "local model choice dict"
# }
def _local_backend_choices():
    if RUNTIME_BACKEND == "comfyui":
        checkpoint_files = (
            _scan_model_files(CHECKPOINTS_DIR)
            + [file for legacy_root in LEGACY_CHECKPOINTS_DIRS for file in _scan_model_files(legacy_root)]
            + _scan_model_files(RUNTIME_DIR / "models" / "checkpoints")
        )
        unet_files = (
            _scan_model_files(MODELS_DIR / "diffusion_models")
            + _scan_model_files(MODELS_DIR / "unet")
            + _scan_model_files(LEGACY_MODELS_DIR / "diffusion_models")
            + _scan_model_files(LEGACY_MODELS_DIR / "unet")
            + _scan_model_files(RUNTIME_DIR / "models" / "diffusion_models")
            + _scan_model_files(RUNTIME_DIR / "models" / "unet")
        )
        lora_files = (
            _scan_model_files(MODELS_DIR / "Lora")
            + _scan_model_files(MODELS_DIR / "loras")
            + _scan_model_files(LEGACY_MODELS_DIR / "Lora")
            + _scan_model_files(LEGACY_MODELS_DIR / "loras")
            + _scan_model_files(RUNTIME_DIR / "models" / "loras")
        )
        vae_files = (
            _scan_model_files(MODELS_DIR / "VAE")
            + _scan_model_files(MODELS_DIR / "vae")
            + _scan_model_files(LEGACY_MODELS_DIR / "VAE")
            + _scan_model_files(LEGACY_MODELS_DIR / "vae")
            + _scan_model_files(RUNTIME_DIR / "models" / "vae")
        )
        return {
            "checkpoints": _unique_choices(checkpoint_files),
            "unets": _unique_choices(unet_files),
            "loras": _unique_choices(lora_files),
            "vaes": _unique_choices(vae_files),
            "upscalers": _scan_model_files(RUNTIME_DIR / "models" / "upscale_models"),
            "samplers": list(COMFYUI_SAMPLER_CHOICES),
            "flows": _unique_choices(
                _scan_flow_files(COMFY_FLOWS_DIR)
                + _scan_flow_files(LEGACY_MODELS_DIR / "flows")
            ),
        }

    model_root = RUNTIME_DIR / "models"
    upscalers = list(A1111_UPSCALER_CHOICES)
    for folder_name in ("ESRGAN", "RealESRGAN", "SwinIR", "LDSR", "ScuNET", "BSRGAN"):
        upscalers.extend(_scan_model_files(model_root / folder_name, keep_suffix=False))
    return {
        "checkpoints": _unique_choices(_scan_model_files(CHECKPOINTS_DIR) + [file for legacy_root in LEGACY_CHECKPOINTS_DIRS for file in _scan_model_files(legacy_root)]),
        "unets": [],
        "loras": _unique_choices(
            _scan_model_files(MODELS_DIR / "Lora")
            + _scan_model_files(MODELS_DIR / "loras")
            + _scan_model_files(LEGACY_MODELS_DIR / "Lora")
            + _scan_model_files(LEGACY_MODELS_DIR / "loras")
            + _scan_model_files(A1111_DIR / "models" / "Lora")
        ),
        "vaes": _unique_choices(
            _scan_model_files(MODELS_DIR / "VAE")
            + _scan_model_files(MODELS_DIR / "vae")
            + _scan_model_files(LEGACY_MODELS_DIR / "VAE")
            + _scan_model_files(LEGACY_MODELS_DIR / "vae")
            + _scan_model_files(A1111_DIR / "models" / "VAE")
            + _scan_model_files(RUNTIME_DIR / "models" / "VAE")
        ),
        "upscalers": _unique_choices(upscalers),
        "samplers": list(A1111_SAMPLER_CHOICES),
        "flows": [],
    }


# {
#   "責務": "ローカルbackend候補と任意の稼働API登録候補を統合する。",
#   "処理": ["local choicesをロードする", "要求時にbackend catalog APIを照会し警告と候補を統合する"],
#   "引数": {"api_url": "backend API base URL", "query_api": "API照会を有効化するか"}, "戻り値": "候補dictとwarning listのtuple"
# }
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


# {
#   "責務": "複数のTagger response形式からtag名listを正規化する。",
#   "処理": ["caption/tagsのstr・list・dict形式を解析する", "未対応構造ならRuntimeErrorを送出する"],
#   "引数": {"result": "Tagger応答JSONまたは値"}, "戻り値": "trim済みtag名list"
# }
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




 # {
 #   "責務": "例外をlogへ通知するdaemon worker threadを起動する。",
 #   "処理": ["callableと引数をrunnerへ渡しthreadを開始する"],
 #   "引数": {"logbox": "エラー表示先", "func": "実行callable", "args": "位置引数", "kwargs": "keyword引数"}, "戻り値": []
 # }
def _safe_thread(logbox, func, *args, **kwargs):
    # {
    #   "責務": "対象callableを実行し例外をGUI logまたはstderrへ報告する。",
    #   "処理": ["funcを指定引数で呼ぶ", "失敗時にlogboxを試し、さらに失敗すればstderrへ出す"],
    #   "引数": [], "戻り値": []
    # }
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
