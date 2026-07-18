"""ローカルで動く、見た目のためのPDF押印ツール。"""

from __future__ import annotations

import base64
import html
import json
import math
import os
import re
import shutil
import sys
import uuid
from pathlib import Path
from threading import Lock, Thread, current_thread
from typing import Any

import fitz  # PyMuPDF
from fastapi import File, Form, FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from stamp_generator import StampDesignError, available_fonts, create_stamp_svg, parse_design, validate_svg_asset


ROOT = Path(__file__).resolve().parent
STATIC_DIR = Path(getattr(sys, "_MEIPASS", ROOT)) / "static"


def application_data_dir() -> Path:
    """実行形式ではアプリ本体ではなく、書き込み可能な場所へ保存する。"""
    configured_directory = os.environ.get("HANKO_DATA_DIR")
    if configured_directory:
        return Path(configured_directory).expanduser()
    if getattr(sys, "frozen", False) and sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Hanko PDF"
    return ROOT


DATA_DIR = application_data_dir()
WORK_DIR = DATA_DIR / "tmp" / "pdfs"
DOCUMENT_DIR = WORK_DIR / "documents"
STAMP_DIR = WORK_DIR / "stamps"
STAMP_DESIGN_ASSET_DIR = WORK_DIR / "stamp-design-assets"
REGISTERED_STAMPS_DIR = DATA_DIR / "registered-stamps"
EXPORT_DIR = DATA_DIR / "exports"
BATCH_EXPORT_DIR = EXPORT_DIR / "batches"
TEMPLATES_PATH = DATA_DIR / "templates.json"
SETTINGS_PATH = DATA_DIR / "settings.json"
REGISTERED_STAMPS_PATH = DATA_DIR / "registered-stamps.json"

MAX_UPLOAD_BYTES = 35 * 1024 * 1024
MAX_BATCH_FILES = 30
MAX_BATCH_BYTES = 150 * 1024 * 1024
POINTS_PER_MM = 72 / 25.4
VALID_STAMP_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg", ".pdf"}
UUID_RE = re.compile(r"^[0-9a-f]{32}$")
TEMPLATE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
MAX_TEMPLATES = 100
MAX_TEMPLATE_NAME_LENGTH = 80
MAX_REGISTERED_STAMPS = 200
MAX_STAMP_DIMENSION_MM = 500
DEFAULT_SETTINGS = {"filenameSuffix": "押印済み", "batchCollision": "rename"}

for directory in (DOCUMENT_DIR, STAMP_DIR, STAMP_DESIGN_ASSET_DIR, REGISTERED_STAMPS_DIR, EXPORT_DIR, BATCH_EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Hanko PDF", docs_url=None, redoc_url=None)


# フォント一覧は初回のOS／ファイル走査に時間がかかるため、ウィンドウを表示する
# 前のサーバー起動時点で準備を始める。APIアクセス側は同じスレッドの終了を待つので、
# 起動直後に印影作成画面を開いても走査を二重に走らせない。
_font_preload_lock = Lock()
_font_preload_thread: Thread | None = None


def _preload_fonts() -> None:
    try:
        available_fonts()
    except Exception:
        # 個別のフォントの破損などで事前読み込みに失敗しても、アプリ起動自体は
        # 続ける。/api/fonts からの通常取得時にあらためてエラーを返す。
        pass


def start_font_preload() -> None:
    """フォント一覧の初回走査を、起動を妨げない形で開始する。"""
    global _font_preload_thread
    with _font_preload_lock:
        if _font_preload_thread is not None:
            return
        _font_preload_thread = Thread(
            target=_preload_fonts,
            name="hanko-font-preload",
            daemon=True,
        )
        _font_preload_thread.start()


def wait_for_font_preload() -> None:
    """事前読み込み中なら完了を待ち、同じフォント走査を重複させない。"""
    with _font_preload_lock:
        thread = _font_preload_thread
    if thread is not None and thread is not current_thread():
        thread.join()


@app.on_event("startup")
def preload_fonts_at_startup() -> None:
    start_font_preload()


def fail(message: str, status_code: int = 400) -> None:
    raise HTTPException(status_code=status_code, detail=message)


def safe_id(value: str) -> str:
    if not UUID_RE.fullmatch(value):
        fail("ファイル識別子が正しくありません。", 404)
    return value


def safe_integer(value: Any, label: str, minimum: int = 0, maximum: int = 999) -> int:
    if isinstance(value, bool):
        fail(f"{label}が正しくありません。")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        fail(f"{label}が正しくありません。")
    if str(parsed) != str(value).strip() and not isinstance(value, int):
        fail(f"{label}が正しくありません。")
    if not minimum <= parsed <= maximum:
        fail(f"{label}が正しくありません。")
    return parsed


def number(value: Any, label: str, minimum: float = 0.0, maximum: float = 1000.0) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        fail(f"{label}は数値で指定してください。")
    if not minimum <= parsed <= maximum:
        fail(f"{label}は{minimum}から{maximum}の範囲で指定してください。")
    return parsed


async def read_upload(upload: UploadFile) -> bytes:
    content = await upload.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        fail("空のファイルはアップロードできません。")
    if len(content) > MAX_UPLOAD_BYTES:
        fail("ファイルは35MB以下にしてください。")
    return content


def document_path(document_id: str) -> Path:
    path = DOCUMENT_DIR / safe_id(document_id) / "document.pdf"
    if not path.is_file():
        fail("PDFが見つかりません。ページを再読み込みしてもう一度アップロードしてください。", 404)
    return path


def document_filename(document_id: str) -> str:
    """アップロード時の表示名を、書き出し候補名として安全に復元する。"""
    directory = DOCUMENT_DIR / safe_id(document_id)
    try:
        filename = (directory / "source-name.txt").read_text(encoding="utf-8").strip()
    except OSError:
        return "document.pdf"
    return Path(filename).name or "document.pdf"


def stamp_path(stamp_id: str) -> Path:
    directory = STAMP_DIR / safe_id(stamp_id)
    matches = list(directory.glob("stamp.*"))
    if len(matches) == 1:
        return matches[0]
    record = registered_stamp_record(stamp_id)
    path = REGISTERED_STAMPS_DIR / f"{record['id']}{record['extension']}"
    if not path.is_file():
        fail("登録済み印影ファイルが見つかりません。", 404)
    return path


def stamp_design_asset_path(asset_id: str) -> Path:
    path = STAMP_DESIGN_ASSET_DIR / safe_id(asset_id) / "asset.svg"
    if not path.is_file():
        fail("配置するSVGが見つかりません。もう一度追加してください。", 404)
    return path


def hydrated_stamp_design_payload(payload: Any) -> Any:
    """クライアントのSVG識別子を、生成時だけ保存済みのSVG本体へ置換する。"""
    if not isinstance(payload, dict) or "svgAssets" not in payload:
        return payload
    assets = payload.get("svgAssets")
    if not isinstance(assets, list):
        fail("SVGの配置内容が正しくありません。")
    hydrated_assets: list[dict[str, Any]] = []
    for item in assets:
        if not isinstance(item, dict):
            fail("SVGの配置内容が正しくありません。")
        source = stamp_design_asset_path(str(item.get("assetId", "")))
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            fail("配置するSVGを読み取れませんでした。")
        hydrated = dict(item)
        hydrated["svgContent"] = content
        hydrated_assets.append(hydrated)
    result = dict(payload)
    result["svgAssets"] = hydrated_assets
    return result


def export_path(export_id: str) -> Path:
    path = EXPORT_DIR / f"hanko-stamped-{safe_id(export_id)}.pdf"
    if not path.is_file():
        fail("書き出しPDFが見つかりません。もう一度書き出してください。", 404)
    return path


def batch_directory(batch_id: str) -> Path:
    directory = BATCH_EXPORT_DIR / safe_id(batch_id)
    if not directory.is_dir():
        fail("一括書き出しデータが見つかりません。もう一度書き出してください。", 404)
    return directory


def atomic_write_json(path: Path, value: Any, error_label: str) -> None:
    temporary_path = path.with_suffix(".tmp")
    try:
        temporary_path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(path)
    except OSError as error:
        temporary_path.unlink(missing_ok=True)
        fail(f"{error_label}できませんでした: {error}", 500)


def _svg_length_mm(value: str | None) -> float | None:
    if not value:
        return None
    match = re.fullmatch(r"\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|cm|in|pt|pc)\s*", value)
    if not match:
        return None
    amount = float(match.group(1))
    unit = match.group(2)
    factors = {"mm": 1, "cm": 10, "in": 25.4, "pt": 25.4 / 72, "pc": 25.4 / 6}
    return amount * factors[unit]


def _svg_physical_size_mm(path: Path) -> tuple[float, float] | None:
    try:
        header = path.read_bytes()[:32768].decode("utf-8", errors="ignore")
    except OSError:
        return None
    root = re.search(r"<svg\b[^>]*>", header, flags=re.IGNORECASE)
    if not root:
        return None
    width_match = re.search(r'\bwidth\s*=\s*["\']([^"\']+)["\']', root.group(0), flags=re.IGNORECASE)
    height_match = re.search(r'\bheight\s*=\s*["\']([^"\']+)["\']', root.group(0), flags=re.IGNORECASE)
    width = _svg_length_mm(width_match.group(1) if width_match else None)
    height = _svg_length_mm(height_match.group(1) if height_match else None)
    return (width, height) if width and height else None


def _raster_dpi(path: Path) -> tuple[float, float] | None:
    """PNGのpHYsとJPEGのJFIFから、埋め込まれた解像度だけを読む。"""
    try:
        content = path.read_bytes()
    except OSError:
        return None
    if content.startswith(b"\x89PNG\r\n\x1a\n"):
        offset = 8
        while offset + 12 <= len(content):
            length = int.from_bytes(content[offset:offset + 4], "big")
            chunk_type = content[offset + 4:offset + 8]
            chunk = content[offset + 8:offset + 8 + length]
            if chunk_type == b"pHYs" and len(chunk) == 9 and chunk[8] == 1:
                x_ppm = int.from_bytes(chunk[:4], "big")
                y_ppm = int.from_bytes(chunk[4:8], "big")
                if x_ppm and y_ppm:
                    return x_ppm * 0.0254, y_ppm * 0.0254
            offset += length + 12
        return None
    if content.startswith(b"\xff\xd8"):
        offset = 2
        while offset + 4 <= len(content):
            if content[offset] != 0xFF:
                offset += 1
                continue
            marker = content[offset + 1]
            offset += 2
            if marker in {0xD8, 0xD9}:
                continue
            if offset + 2 > len(content):
                break
            length = int.from_bytes(content[offset:offset + 2], "big")
            segment = content[offset + 2:offset + length]
            if marker == 0xE0 and segment.startswith(b"JFIF\x00") and len(segment) >= 12:
                unit, x_density, y_density = segment[7], int.from_bytes(segment[8:10], "big"), int.from_bytes(segment[10:12], "big")
                if x_density and y_density and unit in {1, 2}:
                    multiplier = 1 if unit == 1 else 2.54
                    return x_density * multiplier, y_density * multiplier
            offset += max(length, 2)
    return None


def stamp_default_dimensions(path: Path) -> tuple[float, float, bool]:
    """元ファイルに実寸情報があれば優先し、なければ扱いやすい9.5mmにする。"""
    suffix = path.suffix.lower()
    try:
        if suffix == ".svg":
            dimensions = _svg_physical_size_mm(path)
            if dimensions:
                return round(dimensions[0], 3), round(dimensions[1], 3), True
        elif suffix == ".pdf":
            document = fitz.open(path)
            try:
                if document.page_count:
                    return round(document[0].rect.width / POINTS_PER_MM, 3), round(document[0].rect.height / POINTS_PER_MM, 3), True
            finally:
                document.close()
        else:
            dpi = _raster_dpi(path)
            if dpi:
                pixmap = fitz.Pixmap(str(path))
                return round(pixmap.width / dpi[0] * 25.4, 3), round(pixmap.height / dpi[1] * 25.4, 3), True
    except Exception:
        # 実寸の取得失敗は印影自体の読み込み失敗ではないため、既定値へ戻す。
        pass
    return 9.5, 9.5, False


def _registered_stamp_record(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    stamp_id = str(value.get("id", ""))
    filename = Path(str(value.get("filename", ""))).name
    extension = str(value.get("extension", "")).lower()
    if not UUID_RE.fullmatch(stamp_id) or not filename or extension not in VALID_STAMP_EXTENSIONS:
        return None
    try:
        width_mm = number(value.get("defaultWidthMm"), "印影の幅", 0.1, MAX_STAMP_DIMENSION_MM)
        height_mm = number(value.get("defaultHeightMm"), "印影の高さ", 0.1, MAX_STAMP_DIMENSION_MM)
    except HTTPException:
        return None
    if not (REGISTERED_STAMPS_DIR / f"{stamp_id}{extension}").is_file():
        return None
    return {
        "id": stamp_id,
        "filename": filename,
        "extension": extension,
        "defaultWidthMm": width_mm,
        "defaultHeightMm": height_mm,
        "sizeDetected": bool(value.get("sizeDetected", False)),
        "registered": True,
    }


def stored_registered_stamps() -> list[dict[str, Any]]:
    try:
        raw = json.loads(REGISTERED_STAMPS_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    if not isinstance(raw, list):
        return []
    return [record for item in raw if (record := _registered_stamp_record(item))]


def registered_stamp_record(stamp_id: str) -> dict[str, Any]:
    stamp_id = safe_id(stamp_id)
    for record in stored_registered_stamps():
        if record["id"] == stamp_id:
            return record
    fail("登録済み印影が見つかりません。", 404)


def save_registered_stamps(stamps: list[dict[str, Any]]) -> None:
    atomic_write_json(REGISTERED_STAMPS_PATH, stamps, "登録済み印影を保存")


def stored_templates() -> list[dict[str, Any]]:
    """アプリが記憶する配置テンプレートを読む。壊れた保存データは空として扱う。"""
    try:
        templates = json.loads(TEMPLATES_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return []
    return templates if isinstance(templates, list) else []


def validate_templates(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        fail("テンプレートの形式が正しくありません。")
    if len(value) > MAX_TEMPLATES:
        fail(f"テンプレートは{MAX_TEMPLATES}件まで保存できます。")

    templates: list[dict[str, Any]] = []
    for template in value:
        if not isinstance(template, dict):
            fail("テンプレートの形式が正しくありません。")
        template_id = str(template.get("id", ""))
        name = str(template.get("name", "")).strip()
        placements = template.get("placements")
        if not TEMPLATE_ID_RE.fullmatch(template_id) or not name or len(name) > MAX_TEMPLATE_NAME_LENGTH:
            fail("テンプレートの名前または識別子が正しくありません。")
        if not isinstance(placements, list) or not placements or len(placements) > 100:
            fail("テンプレートの配置は1個から100個で指定してください。")

        normalized_placements: list[dict[str, float | int]] = []
        for placement in placements:
            if not isinstance(placement, dict):
                fail("テンプレートの配置情報が正しくありません。")
            legacy_size = placement.get("sizeMm")
            width_mm = number(placement.get("widthMm", legacy_size), "印影の幅", 0.1, MAX_STAMP_DIMENSION_MM)
            height_mm = number(placement.get("heightMm", legacy_size), "印影の高さ", 0.1, MAX_STAMP_DIMENSION_MM)
            normalized_placements.append(
                {
                    "page": safe_integer(placement.get("page"), "テンプレートのページ番号"),
                    "xMm": number(placement.get("xMm"), "横位置"),
                    "yMm": number(placement.get("yMm"), "縦位置"),
                    "widthMm": width_mm,
                    "heightMm": height_mm,
                    "rotationDegrees": safe_integer(placement.get("rotationDegrees", 0), "印影の角度", -90, 90),
                }
            )
        templates.append({"id": template_id, "name": name, "placements": normalized_placements})
    return templates


def validated_settings(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        fail("書き出し設定の形式が正しくありません。")
    suffix = str(value.get("filenameSuffix", "")).strip()
    collision = value.get("batchCollision")
    if not suffix or len(suffix) > 40 or any(character in suffix for character in "\\/:*?\"<>|"):
        fail("ファイル名の末尾は1〜40文字で、\\ / : * ? \" < > | は使えません。")
    if collision not in {"rename", "cancel"}:
        fail("一括書き出し時の重複時の扱いが正しくありません。")
    return {"filenameSuffix": suffix, "batchCollision": collision}


def stored_settings() -> dict[str, str]:
    try:
        value = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        return validated_settings(value)
    except (FileNotFoundError, json.JSONDecodeError, OSError, HTTPException):
        return DEFAULT_SETTINGS.copy()


def page_info(document: fitz.Document) -> list[dict[str, float]]:
    return [
        {
            "widthMm": round(page.rect.width / POINTS_PER_MM, 3),
            "heightMm": round(page.rect.height / POINTS_PER_MM, 3),
        }
        for page in document
    ]


def svg_clip_metadata(path: Path) -> tuple[str, float, float, str] | None:
    """このアプリが生成したSVGに埋め込んだ、PDF変換用のクリップ情報を読む。"""
    try:
        header = path.read_bytes()[:8192]
    except OSError:
        return None
    shape_match = re.search(rb'data-stamp-clip="(round|square|none)"', header)
    format_match = re.search(rb'data-stamp-format="(personal|company|company_square|stamp)"', header)
    radius_match = re.search(rb'data-stamp-corner-radius-mm="([0-9]+(?:\.[0-9]+)?)"', header)
    frame_width_match = re.search(rb'data-stamp-frame-width="([0-9]+(?:\.[0-9]+)?)"', header)
    if not shape_match:
        return None
    shape = shape_match.group(1).decode("ascii")
    radius = float(radius_match.group(1)) if radius_match else 0.0
    frame_width = float(frame_width_match.group(1)) if frame_width_match else 0.0
    stamp_format = format_match.group(1).decode("ascii") if format_match else "personal"
    return shape, radius, frame_width, stamp_format


def pdf_circle_clip(width: float, height: float, frame_width: float) -> str:
    return pdf_circle_clip_radius(width, height, min(width, height) * (500 - (frame_width / 2 + 28)) / 1000)


def pdf_circle_clip_radius(width: float, height: float, radius: float) -> str:
    center_x = width / 2
    center_y = height / 2
    control = radius * 0.552284749831
    return (
        f"{center_x + radius:.5f} {center_y:.5f} m\n"
        f"{center_x + radius:.5f} {center_y + control:.5f} {center_x + control:.5f} {center_y + radius:.5f} {center_x:.5f} {center_y + radius:.5f} c\n"
        f"{center_x - control:.5f} {center_y + radius:.5f} {center_x - radius:.5f} {center_y + control:.5f} {center_x - radius:.5f} {center_y:.5f} c\n"
        f"{center_x - radius:.5f} {center_y - control:.5f} {center_x - control:.5f} {center_y - radius:.5f} {center_x:.5f} {center_y - radius:.5f} c\n"
        f"{center_x + control:.5f} {center_y - radius:.5f} {center_x + radius:.5f} {center_y - control:.5f} {center_x + radius:.5f} {center_y:.5f} c\nh\n"
    )


def pdf_rounded_rectangle_clip(width: float, height: float, radius_mm: float, frame_width: float) -> str:
    inset = min(width, height) * (frame_width / 2 + 28) / 1000
    left, bottom = inset, inset
    right, top = width - inset, height - inset
    radius = min(radius_mm * POINTS_PER_MM, (right - left) / 2, (top - bottom) / 2)
    if radius <= 0:
        return f"{left:.5f} {bottom:.5f} {right - left:.5f} {top - bottom:.5f} re\n"
    control = radius * 0.552284749831
    return (
        f"{left + radius:.5f} {bottom:.5f} m\n{right - radius:.5f} {bottom:.5f} l\n"
        f"{right - radius + control:.5f} {bottom:.5f} {right:.5f} {bottom + radius - control:.5f} {right:.5f} {bottom + radius:.5f} c\n"
        f"{right:.5f} {top - radius:.5f} l\n{right:.5f} {top - radius + control:.5f} {right - radius + control:.5f} {top:.5f} {right - radius:.5f} {top:.5f} c\n"
        f"{left + radius:.5f} {top:.5f} l\n{left + radius - control:.5f} {top:.5f} {left:.5f} {top - radius + control:.5f} {left:.5f} {top - radius:.5f} c\n"
        f"{left:.5f} {bottom + radius:.5f} l\n{left:.5f} {bottom + radius - control:.5f} {left + radius - control:.5f} {bottom:.5f} {left + radius:.5f} {bottom:.5f} c\nh\n"
    )


def apply_pdf_clip(document: fitz.Document, clipping_path: str) -> None:
    """PDFのコンテンツへベクターのクリッピングパスを追加する。"""
    if not document.page_count:
        return
    page = document[0]
    page.clean_contents()
    contents = page.get_contents()
    if not contents:
        return
    xref = contents[0]
    stream = document.xref_stream(xref)
    document.update_stream(xref, f"q\n{clipping_path}W n\n".encode("ascii") + stream + b"\nQ\n")


def apply_pdf_stamp_clip(document: fitz.Document, metadata: tuple[str, float, float, str] | None) -> None:
    """MuPDFがSVG clipPathを無視するため、変換後PDFへ同じ外周クリップを焼き込む。"""
    if not metadata or metadata[0] == "none" or not document.page_count:
        return
    shape, radius_mm, frame_width, _ = metadata
    rectangle = document[0].rect
    clipping_path = (
        pdf_circle_clip(rectangle.width, rectangle.height, frame_width)
        if shape == "round"
        else pdf_rounded_rectangle_clip(rectangle.width, rectangle.height, radius_mm, frame_width)
    )
    apply_pdf_clip(document, clipping_path)


def apply_pdf_company_role_clip(document: fitz.Document) -> None:
    """会社認印の中央役職だけを、内円の中心線でクリップする。"""
    if not document.page_count:
        return
    rectangle = document[0].rect
    apply_pdf_clip(document, pdf_circle_clip_radius(rectangle.width, rectangle.height, min(rectangle.width, rectangle.height) * 0.245))


def split_generated_svg(content: bytes) -> tuple[bytes, bytes] | None:
    """生成SVGを本文と枠へ分け、PDFでは本文だけをクリップできるようにする。"""
    body_pattern = rb'<!--STAMP_BODY_START-->.*?<!--STAMP_BODY_END-->'
    frame_pattern = rb'<!--STAMP_FRAME_START-->.*?<!--STAMP_FRAME_END-->'
    if not re.search(body_pattern, content, flags=re.DOTALL) or not re.search(frame_pattern, content, flags=re.DOTALL):
        return None
    body_only = re.sub(frame_pattern, b"", content, flags=re.DOTALL)
    frame_only = re.sub(body_pattern, b"", content, flags=re.DOTALL)
    return body_only, frame_only


def split_company_body_svg(content: bytes) -> tuple[bytes, bytes] | None:
    """会社認印の外周文字と中央役職を、PDF用に別のSVGレイヤーとして取り出す。"""
    ring_pattern = rb'<!--STAMP_COMPANY_RING_START-->.*?<!--STAMP_COMPANY_RING_END-->'
    role_pattern = rb'<!--STAMP_COMPANY_ROLE_START-->.*?<!--STAMP_COMPANY_ROLE_END-->'
    frame_pattern = rb'<!--STAMP_FRAME_START-->.*?<!--STAMP_FRAME_END-->'
    if not re.search(ring_pattern, content, flags=re.DOTALL) or not re.search(role_pattern, content, flags=re.DOTALL):
        return None
    ring_only = re.sub(role_pattern, b"", content, flags=re.DOTALL)
    role_only = re.sub(ring_pattern, b"", content, flags=re.DOTALL)
    return (
        re.sub(frame_pattern, b"", ring_only, flags=re.DOTALL),
        re.sub(frame_pattern, b"", role_only, flags=re.DOTALL),
    )


def svg_bytes_to_pdf(content: bytes) -> fitz.Document:
    svg_document = fitz.open(stream=content, filetype="svg")
    try:
        pdf_bytes = svg_document.convert_to_pdf()
    finally:
        svg_document.close()
    return fitz.open(stream=pdf_bytes, filetype="pdf")


def open_vector_stamp(path: Path) -> fitz.Document:
    """PDFまたはSVGを、show_pdf_pageで使えるPDFドキュメントとして開く。"""
    if path.suffix.lower() == ".pdf":
        return fitz.open(path)

    content = path.read_bytes()
    metadata = svg_clip_metadata(path)
    layers = split_generated_svg(content)
    if not layers or not metadata or metadata[0] == "none":
        return svg_bytes_to_pdf(content)

    company_layers = split_company_body_svg(content) if metadata[3] == "company" else None
    if company_layers:
        ring_document = svg_bytes_to_pdf(company_layers[0])
        role_document = svg_bytes_to_pdf(company_layers[1])
        frame_document = svg_bytes_to_pdf(layers[1])
        try:
            apply_pdf_stamp_clip(ring_document, metadata)
            apply_pdf_company_role_clip(role_document)
            result = fitz.open()
            rectangle = ring_document[0].rect
            page = result.new_page(width=rectangle.width, height=rectangle.height)
            page.show_pdf_page(page.rect, ring_document, 0, keep_proportion=False)
            page.show_pdf_page(page.rect, role_document, 0, keep_proportion=False, overlay=True)
            page.show_pdf_page(page.rect, frame_document, 0, keep_proportion=False, overlay=True)
            return result
        finally:
            ring_document.close()
            role_document.close()
            frame_document.close()

    body_document = svg_bytes_to_pdf(layers[0])
    frame_document = svg_bytes_to_pdf(layers[1])
    try:
        apply_pdf_stamp_clip(body_document, metadata)
        result = fitz.open()
        rectangle = body_document[0].rect
        page = result.new_page(width=rectangle.width, height=rectangle.height)
        page.show_pdf_page(page.rect, body_document, 0, keep_proportion=False)
        page.show_pdf_page(page.rect, frame_document, 0, keep_proportion=False, overlay=True)
        return result
    finally:
        body_document.close()
        frame_document.close()


def preview_stamp(path: Path) -> bytes:
    """どの入力形式でもブラウザ表示用のPNGにする。"""
    suffix = path.suffix.lower()
    if suffix in {".pdf", ".svg"}:
        document = open_vector_stamp(path)
    else:
        document = fitz.open(path)
    try:
        if not document.page_count:
            fail("印影ファイルにページまたは画像がありません。")
        pixmap = document[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
        return pixmap.tobytes("png")
    finally:
        document.close()


def rotated_size(width_mm: float, height_mm: float, rotation_degrees: int) -> tuple[float, float]:
    radians = math.radians(rotation_degrees)
    return (
        abs(width_mm * math.cos(radians)) + abs(height_mm * math.sin(radians)),
        abs(width_mm * math.sin(radians)) + abs(height_mm * math.cos(radians)),
    )


def stamp_metadata_texts(path: Path) -> list[str]:
    """このアプリ形式のSVG metadataから、PDFへ渡す検索用文字列を読む。"""
    if path.suffix.lower() != ".svg":
        return []
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []
    match = re.search(r'<metadata\b[^>]*\bid=["\']hanko-stamp-metadata["\'][^>]*>(.*?)</metadata>', source, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []
    try:
        metadata = json.loads(html.unescape(match.group(1)))
    except json.JSONDecodeError:
        return []
    if not isinstance(metadata, dict) or metadata.get("schema") != "hanko-pdf/stamp-metadata/1":
        return []
    texts = metadata.get("texts")
    if not isinstance(texts, list):
        return []
    result: list[str] = []
    for value in texts:
        if not isinstance(value, str):
            continue
        text = " ".join(value.split())
        if text and text not in result:
            result.append(text)
    return result


def merge_stamp_keywords(document: fitz.Document, texts: list[str]) -> None:
    if not texts:
        return
    metadata = document.metadata
    current = metadata.get("keywords") or ""
    keywords = [value.strip() for value in re.split(r"[,;]", current) if value.strip()]
    for text in texts:
        if text not in keywords:
            keywords.append(text)
    metadata["keywords"] = ", ".join(keywords)
    document.set_metadata(metadata)


def rotated_stamp_document(path: Path, rotation_degrees: int) -> fitz.Document:
    """任意角度を保つため、透明PNGを含む一時ベクターPDFへ回転を焼き込む。"""
    source = open_vector_stamp(path) if path.suffix.lower() in {".pdf", ".svg"} else fitz.open(path)
    try:
        if not source.page_count:
            fail("印影ファイルにページまたは画像がありません。")
        source_page = source[0]
        width, height = source_page.rect.width, source_page.rect.height
        pixmap = source_page.get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
    finally:
        source.close()
    radians = math.radians(rotation_degrees)
    bounding_width = abs(width * math.cos(radians)) + abs(height * math.sin(radians))
    bounding_height = abs(width * math.sin(radians)) + abs(height * math.cos(radians))
    image = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{bounding_width:.6f}pt" height="{bounding_height:.6f}pt" '
        f'viewBox="0 0 {bounding_width:.6f} {bounding_height:.6f}">'
        f'<image href="data:image/png;base64,{image}" width="{width:.6f}" height="{height:.6f}" preserveAspectRatio="none" '
        f'transform="translate({bounding_width / 2:.6f} {bounding_height / 2:.6f}) rotate({rotation_degrees}) translate({-width / 2:.6f} {-height / 2:.6f})"/>'
        '</svg>'
    )
    return svg_bytes_to_pdf(svg.encode("utf-8"))


def normalized_placements(document: fitz.Document, placements: Any) -> list[dict[str, Any]]:
    if not isinstance(placements, list) or not placements:
        fail("印影を1つ以上配置してください。")
    if len(placements) > 100:
        fail("一度に配置できる印影は100個までです。")

    normalized: list[dict[str, Any]] = []
    for placement in placements:
        if not isinstance(placement, dict):
            fail("印影の配置情報が正しくありません。")
        page_index = safe_integer(placement.get("page"), "印影のページ番号", 0, document.page_count - 1)
        x_mm = number(placement.get("xMm"), "横位置")
        y_mm = number(placement.get("yMm"), "縦位置")
        legacy_size = placement.get("sizeMm")
        stamped_width_mm = number(placement.get("widthMm", legacy_size), "印影の幅", 0.1, MAX_STAMP_DIMENSION_MM)
        stamped_height_mm = number(placement.get("heightMm", legacy_size), "印影の高さ", 0.1, MAX_STAMP_DIMENSION_MM)
        rotation_degrees = safe_integer(placement.get("rotationDegrees", 0), "印影の角度", -90, 90)
        source_path = stamp_path(str(placement.get("stampId", "")))
        page = document[page_index]
        page_width_mm = page.rect.width / POINTS_PER_MM
        page_height_mm = page.rect.height / POINTS_PER_MM
        bounding_width_mm, bounding_height_mm = rotated_size(stamped_width_mm, stamped_height_mm, rotation_degrees)
        left_mm = x_mm + stamped_width_mm / 2 - bounding_width_mm / 2
        top_mm = y_mm + stamped_height_mm / 2 - bounding_height_mm / 2
        if left_mm < -0.001 or top_mm < -0.001 or left_mm + bounding_width_mm > page_width_mm + 0.001 or top_mm + bounding_height_mm > page_height_mm + 0.001:
            fail("印影がPDFページの範囲を超えています。位置またはサイズを調整してください。")
        normalized.append(
            {
                "page": page_index,
                "xMm": x_mm,
                "yMm": y_mm,
                "widthMm": stamped_width_mm,
                "heightMm": stamped_height_mm,
                "rotationDegrees": rotation_degrees,
                "boundingXmm": left_mm,
                "boundingYmm": top_mm,
                "boundingWidthMm": bounding_width_mm,
                "boundingHeightMm": bounding_height_mm,
                "source": source_path,
            }
        )
    return normalized


def stamp_document(document: fitz.Document, placements: Any, output_path: Path, embed_stamp_metadata: bool = False) -> list[dict[str, Any]]:
    """検証済みの配置をPDFに適用し、別ファイルとして保存する。"""
    normalized = normalized_placements(document, placements)
    source_documents: dict[str, fitz.Document] = {}
    rotated_documents: dict[tuple[str, int], fitz.Document] = {}
    metadata_texts: list[str] = []
    try:
        for placement in normalized:
            source_path = placement["source"]
            page = document[placement["page"]]
            rotation_degrees = placement["rotationDegrees"]
            rectangle = fitz.Rect(
                placement["boundingXmm"] * POINTS_PER_MM,
                placement["boundingYmm"] * POINTS_PER_MM,
                (placement["boundingXmm"] + placement["boundingWidthMm"]) * POINTS_PER_MM,
                (placement["boundingYmm"] + placement["boundingHeightMm"]) * POINTS_PER_MM,
            )
            if embed_stamp_metadata:
                metadata_texts.extend(stamp_metadata_texts(source_path))
            if rotation_degrees:
                source_key = (str(source_path), rotation_degrees)
                if source_key not in rotated_documents:
                    rotated_documents[source_key] = rotated_stamp_document(source_path, rotation_degrees)
                page.show_pdf_page(rectangle, rotated_documents[source_key], 0, overlay=True, keep_proportion=False)
            elif source_path.suffix.lower() in {".pdf", ".svg"}:
                source_key = str(source_path)
                if source_key not in source_documents:
                    source_documents[source_key] = open_vector_stamp(source_path)
                page.show_pdf_page(rectangle, source_documents[source_key], 0, overlay=True, keep_proportion=False)
            else:
                page.insert_image(rectangle, filename=str(source_path), overlay=True, keep_proportion=False)
        if embed_stamp_metadata:
            merge_stamp_keywords(document, metadata_texts)
        document.save(output_path, garbage=4, deflate=True)
        return normalized
    finally:
        for source_document in source_documents.values():
            source_document.close()
        for source_document in rotated_documents.values():
            source_document.close()


def output_filename(source_name: str, settings: dict[str, str]) -> str:
    stem = Path(source_name).stem.strip() or "document"
    # パス区切りや制御文字を除き、保存ダイアログへ安全な候補名だけを渡す。
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", stem).rstrip(". ") or "document"
    return f"{stem}_{settings['filenameSuffix']}.pdf"


def stamp_source_filename(design: Any) -> str:
    """入力文字を残した、SVG書き出し用の安全なファイル名を返す。"""
    if design.format == "company":
        parts = (design.company_name, design.role_text)
    else:
        parts = (design.body_text,)
    # 改行は印面レイアウトのための情報なので、保存名では連結して扱う。
    text = "_".join(re.sub(r"[\r\n]+", "", part).strip() for part in parts if part.strip())
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f]', "_", text)
    stem = re.sub(r"\s+", "_", stem).strip("._ ")[:80].rstrip("._ ") or "印影"
    return f"stamp_{stem}.svg"


def unique_filename(filename: str, used_names: set[str]) -> str:
    candidate = filename
    index = 2
    while candidate.casefold() in used_names:
        candidate = f"{Path(filename).stem} ({index}).pdf"
        index += 1
    used_names.add(candidate.casefold())
    return candidate


def placement_page_sizes(document: fitz.Document, placements: Any) -> dict[int, tuple[float, float]]:
    normalized = normalized_placements(document, placements)
    return {
        placement["page"]: (document[placement["page"]].rect.width, document[placement["page"]].rect.height)
        for placement in normalized
    }


def ensure_batch_page_sizes(document: fitz.Document, expected: dict[int, tuple[float, float]]) -> None:
    for page_index, (expected_width, expected_height) in expected.items():
        if page_index >= document.page_count:
            fail("一括処理するPDFのページ数が、配置テンプレートに足りません。")
        page = document[page_index]
        if abs(page.rect.width - expected_width) > 0.5 or abs(page.rect.height - expected_height) > 0.5:
            fail("一括処理は、配置するページの用紙サイズが同じPDFだけを対象にできます。")


def batch_export_files(batch_id: str) -> list[tuple[Path, str]]:
    directory = batch_directory(batch_id)
    manifest_path = directory / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries = manifest["files"]
    except (OSError, ValueError, KeyError, TypeError):
        fail("一括書き出しデータが壊れています。もう一度書き出してください。", 500)
    if not isinstance(entries, list) or not entries:
        fail("一括書き出しデータが壊れています。もう一度書き出してください。", 500)

    files: list[tuple[Path, str]] = []
    for entry in entries:
        if not isinstance(entry, dict):
            fail("一括書き出しデータが壊れています。もう一度書き出してください。", 500)
        filename = entry.get("filename")
        if not isinstance(filename, str) or Path(filename).name != filename or not filename.endswith(".pdf"):
            fail("一括書き出しデータが壊れています。もう一度書き出してください。", 500)
        path = directory / filename
        if not path.is_file():
            fail("一括書き出しPDFが見つかりません。もう一度書き出してください。", 404)
        files.append((path, filename))
    return files


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/documents")
async def upload_document(file: UploadFile = File(...)) -> dict[str, Any]:
    if Path(file.filename or "").suffix.lower() != ".pdf":
        fail("押印対象にはPDFを選択してください。")
    content = await read_upload(file)
    document_id = uuid.uuid4().hex
    directory = DOCUMENT_DIR / document_id
    directory.mkdir()
    path = directory / "document.pdf"
    path.write_bytes(content)
    (directory / "source-name.txt").write_text(Path(file.filename or "document.pdf").name, encoding="utf-8")

    try:
        document = fitz.open(path)
        if document.needs_pass:
            fail("パスワード付きPDFには対応していません。")
        if document.page_count == 0:
            fail("ページのないPDFには押印できません。")
        pages = page_info(document)
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        fail(f"PDFを開けませんでした: {error}")
    finally:
        try:
            document.close()
        except UnboundLocalError:
            pass

    return {"id": document_id, "filename": file.filename, "pages": pages}


@app.get("/api/documents/{document_id}/pages/{page_number}")
def render_document_page(document_id: str, page_number: int) -> Response:
    path = document_path(document_id)
    try:
        document = fitz.open(path)
        if page_number < 0 or page_number >= document.page_count:
            fail("指定されたページはありません。", 404)
        pixmap = document[page_number].get_pixmap(matrix=fitz.Matrix(1.75, 1.75), alpha=False)
        return Response(pixmap.tobytes("png"), media_type="image/png")
    except HTTPException:
        raise
    except Exception as error:
        fail(f"ページを表示できませんでした: {error}")
    finally:
        try:
            document.close()
        except UnboundLocalError:
            pass


@app.post("/api/stamps")
async def upload_stamp(file: UploadFile = File(...)) -> dict[str, Any]:
    extension = Path(file.filename or "").suffix.lower()
    if extension not in VALID_STAMP_EXTENSIONS:
        fail("印影は PNG / JPG / WEBP / SVG / PDF のいずれかを選択してください。")

    content = await read_upload(file)
    stamp_id = uuid.uuid4().hex
    directory = STAMP_DIR / stamp_id
    directory.mkdir()
    path = directory / f"stamp{extension}"
    path.write_bytes(content)
    try:
        preview_stamp(path)
        default_width_mm, default_height_mm, size_detected = stamp_default_dimensions(path)
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        fail(f"印影ファイルを読み取れませんでした: {error}")
    return {
        "id": stamp_id,
        "filename": Path(file.filename or "stamp").name,
        "defaultWidthMm": default_width_mm,
        "defaultHeightMm": default_height_mm,
        "sizeDetected": size_detected,
    }


@app.post("/api/stamps/generated")
async def create_stamp(request: Request) -> dict[str, Any]:
    try:
        design = parse_design(hydrated_stamp_design_payload(await request.json()))
        content = create_stamp_svg(design)
    except StampDesignError as error:
        fail(str(error))
    stamp_id = uuid.uuid4().hex
    directory = STAMP_DIR / stamp_id
    directory.mkdir()
    (directory / "stamp.svg").write_bytes(content)
    filename = stamp_source_filename(design)
    (directory / "source-name.txt").write_text(filename, encoding="utf-8")
    return {
        "id": stamp_id,
        "filename": filename,
        "downloadUrl": f"/api/stamps/{stamp_id}/source",
        "defaultSizeMm": design.size_mm,
        "defaultWidthMm": design.width_mm,
        "defaultHeightMm": design.height_mm,
        "sizeDetected": True,
    }


@app.post("/api/stamp-design-assets")
async def upload_stamp_design_asset(file: UploadFile = File(...)) -> dict[str, Any]:
    if Path(file.filename or "").suffix.lower() != ".svg":
        fail("配置できるのはSVGファイルだけです。")
    content = await read_upload(file)
    try:
        source = content.decode("utf-8")
        view_box = validate_svg_asset(source)
    except UnicodeDecodeError:
        fail("SVGはUTF-8形式で保存してください。")
    except StampDesignError as error:
        fail(str(error))
    asset_id = uuid.uuid4().hex
    directory = STAMP_DESIGN_ASSET_DIR / asset_id
    directory.mkdir()
    (directory / "asset.svg").write_bytes(content)
    return {"id": asset_id, "filename": Path(file.filename or "asset.svg").name, "viewBox": view_box}


@app.post("/api/stamp-designs/preview")
async def preview_stamp_design(request: Request) -> Response:
    try:
        content = create_stamp_svg(hydrated_stamp_design_payload(await request.json()))
    except StampDesignError as error:
        fail(str(error))
    return Response(content, media_type="image/svg+xml")


@app.get("/api/stamps/{stamp_id}/preview")
def stamp_preview(stamp_id: str) -> Response:
    try:
        return Response(preview_stamp(stamp_path(stamp_id)), media_type="image/png")
    except HTTPException:
        raise
    except Exception as error:
        fail(f"印影プレビューを作成できませんでした: {error}")


@app.get("/api/stamps/{stamp_id}/source")
def download_generated_stamp(stamp_id: str) -> FileResponse:
    path = stamp_path(stamp_id)
    if path.suffix.lower() != ".svg":
        fail("SVGとして書き出せるのは、このアプリで作成した印影だけです。", 400)
    name_path = path.parent / "source-name.txt"
    filename = name_path.read_text(encoding="utf-8").strip() if name_path.exists() else "hanko-stamp.svg"
    return FileResponse(path, media_type="image/svg+xml", filename=Path(filename).name or "hanko-stamp.svg")


@app.get("/api/registered-stamps")
def get_registered_stamps() -> dict[str, list[dict[str, Any]]]:
    return {"stamps": stored_registered_stamps()}


@app.post("/api/stamps/{stamp_id}/register")
async def register_stamp(stamp_id: str, request: Request) -> dict[str, Any]:
    source = stamp_path(stamp_id)
    try:
        payload = await request.json()
    except (json.JSONDecodeError, UnicodeDecodeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    filename = Path(str(payload.get("filename", source.name))).name or source.name
    records = stored_registered_stamps()
    if len(records) >= MAX_REGISTERED_STAMPS:
        fail(f"登録できる印影は{MAX_REGISTERED_STAMPS}件までです。")
    registered_id = uuid.uuid4().hex
    extension = source.suffix.lower()
    destination = REGISTERED_STAMPS_DIR / f"{registered_id}{extension}"
    try:
        shutil.copy2(source, destination)
        width_mm, height_mm, size_detected = stamp_default_dimensions(destination)
        record = {
            "id": registered_id,
            "filename": filename,
            "extension": extension,
            "defaultWidthMm": width_mm,
            "defaultHeightMm": height_mm,
            "sizeDetected": size_detected,
            "registered": True,
        }
        save_registered_stamps([record, *records])
        return record
    except HTTPException:
        destination.unlink(missing_ok=True)
        raise
    except OSError as error:
        destination.unlink(missing_ok=True)
        fail(f"印影を登録できませんでした: {error}", 500)


@app.delete("/api/registered-stamps/{stamp_id}")
def delete_registered_stamp(stamp_id: str) -> dict[str, bool]:
    record = registered_stamp_record(stamp_id)
    records = [item for item in stored_registered_stamps() if item["id"] != record["id"]]
    try:
        (REGISTERED_STAMPS_DIR / f"{record['id']}{record['extension']}").unlink(missing_ok=True)
        save_registered_stamps(records)
    except OSError as error:
        fail(f"登録済み印影を削除できませんでした: {error}", 500)
    return {"deleted": True}


@app.get("/api/fonts")
def get_fonts() -> dict[str, list[dict[str, str | int]]]:
    wait_for_font_preload()
    return {"fonts": available_fonts()}


@app.get("/api/templates")
def get_templates() -> list[dict[str, Any]]:
    return stored_templates()


@app.put("/api/templates")
async def save_templates(request: Request) -> list[dict[str, Any]]:
    templates = validate_templates(await request.json())
    atomic_write_json(TEMPLATES_PATH, templates, "テンプレートを保存")
    return templates


@app.get("/api/settings")
def get_settings() -> dict[str, str]:
    return stored_settings()


@app.put("/api/settings")
async def save_settings(request: Request) -> dict[str, str]:
    settings = validated_settings(await request.json())
    atomic_write_json(SETTINGS_PATH, settings, "書き出し設定を保存")
    return settings


@app.post("/api/export")
async def export_pdf(request: Request) -> dict[str, str]:
    payload = await request.json()
    if not isinstance(payload, dict):
        fail("出力内容が正しくありません。")
    document_id = str(payload.get("documentId", ""))
    embed_stamp_metadata = payload.get("embedStampMetadata", False)
    if not isinstance(embed_stamp_metadata, bool):
        fail("メタデータの埋め込み指定が正しくありません。")
    original_path = document_path(document_id)
    export_id = uuid.uuid4().hex
    output_path = EXPORT_DIR / f"hanko-stamped-{export_id}.pdf"
    try:
        document = fitz.open(original_path)
        stamp_document(document, payload.get("placements"), output_path, embed_stamp_metadata)
    except HTTPException:
        output_path.unlink(missing_ok=True)
        raise
    except Exception as error:
        output_path.unlink(missing_ok=True)
        fail(f"PDFを書き出せませんでした: {error}")
    finally:
        try:
            document.close()
        except UnboundLocalError:
            pass

    return {
        "id": export_id,
        "filename": output_filename(document_filename(document_id), stored_settings()),
        "downloadUrl": f"/api/exports/{export_id}",
    }


@app.post("/api/batches")
async def export_batch(
    files: list[UploadFile] = File(...),
    reference_document_id: str = Form(...),
    placements_json: str = Form(...),
    embed_stamp_metadata: bool = Form(False),
) -> dict[str, Any]:
    if not files or len(files) > MAX_BATCH_FILES:
        fail(f"一括処理できるPDFは1〜{MAX_BATCH_FILES}件です。")
    try:
        placements = json.loads(placements_json)
    except json.JSONDecodeError:
        fail("一括書き出しの配置情報が正しくありません。")

    reference_path = document_path(reference_document_id)
    contents: list[tuple[str, bytes]] = []
    total_bytes = 0
    for file in files:
        filename = file.filename or "document.pdf"
        if Path(filename).suffix.lower() != ".pdf":
            fail("一括処理の対象にはPDFだけを選択してください。")
        content = await read_upload(file)
        total_bytes += len(content)
        if total_bytes > MAX_BATCH_BYTES:
            fail("一括処理するPDFの合計サイズは150MB以下にしてください。")
        contents.append((filename, content))

    batch_id = uuid.uuid4().hex
    directory = BATCH_EXPORT_DIR / batch_id
    directory.mkdir()
    documents: list[tuple[str, fitz.Document]] = []
    try:
        reference_document = fitz.open(reference_path)
        try:
            expected_pages = placement_page_sizes(reference_document, placements)
        finally:
            reference_document.close()
        for filename, content in contents:
            try:
                document = fitz.open(stream=content, filetype="pdf")
            except Exception as error:
                fail(f"「{filename}」をPDFとして開けませんでした: {error}")
            try:
                if document.needs_pass:
                    fail(f"「{filename}」はパスワード付きPDFのため一括処理できません。")
                if document.page_count == 0:
                    fail(f"「{filename}」にはページがありません。")
                ensure_batch_page_sizes(document, expected_pages)
                # 各PDFにも同じ配置が収まることを、保存前に改めて検証する。
                normalized_placements(document, placements)
            except Exception:
                document.close()
                raise
            documents.append((filename, document))

        used_names: set[str] = set()
        entries: list[dict[str, str]] = []
        settings = stored_settings()
        for filename, document in documents:
            destination_name = unique_filename(output_filename(filename, settings), used_names)
            stamp_document(document, placements, directory / destination_name, embed_stamp_metadata)
            entries.append({"filename": destination_name})
        atomic_write_json(directory / "manifest.json", {"files": entries}, "一括書き出し情報を保存")
    except HTTPException:
        shutil.rmtree(directory, ignore_errors=True)
        raise
    except Exception as error:
        shutil.rmtree(directory, ignore_errors=True)
        fail(f"PDFを一括書き出しできませんでした: {error}")
    finally:
        for _, document in documents:
            document.close()

    return {"id": batch_id, "files": [entry["filename"] for entry in entries]}


@app.get("/api/exports/{export_id}")
def download_export(export_id: str) -> FileResponse:
    return FileResponse(export_path(export_id), media_type="application/pdf", filename="hanko-stamped.pdf")


@app.get("/api/batches/{batch_id}/files/{file_index}")
def download_batch_export(batch_id: str, file_index: int) -> FileResponse:
    files = batch_export_files(batch_id)
    if file_index < 0 or file_index >= len(files):
        fail("指定された一括書き出しPDFはありません。", 404)
    path, filename = files[file_index]
    return FileResponse(path, media_type="application/pdf", filename=filename)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
