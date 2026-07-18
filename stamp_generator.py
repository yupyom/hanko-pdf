"""フォント輪郭から、編集可能なSVG印影を生成するクロスプラットフォームのコア。"""

from __future__ import annotations

import hashlib
import html
import json
import logging
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

import fitz
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.ttLib import TTCollection, TTFont


CANVAS_SIZE = 1000
FONT_EXTENSIONS = {".ttf", ".otf", ".ttc"}
HEX_COLOR = "0123456789abcdefABCDEF"
JAPANESE_WINDOWS_LANGUAGE = 0x411
JAPANESE_MAC_LANGUAGE = 11
SVG_NAMESPACE = "http://www.w3.org/2000/svg"
MAX_SVG_ASSETS = 24
MAX_SVG_ASSET_BYTES = 5 * 1024 * 1024

# 一部のOS同梱フォントは壊れていなくてもnameテーブルの警告を出す。
# 利用できないフォントは個別に除外するため、一覧取得時はログを静かにする。
logging.getLogger("fontTools").setLevel(logging.ERROR)


class StampDesignError(ValueError):
    """ユーザーにそのまま表示できる、印影設計の入力エラー。"""


@dataclass(frozen=True)
class FontRecord:
    identifier: str
    family_identifier: str
    family: str
    localized_family: str
    full_name: str
    localized_full_name: str
    style: str
    localized_style: str
    weight: int
    path: Path
    index: int

    def as_api_value(self) -> dict[str, str | int]:
        return {
            "id": self.identifier,
            "familyId": self.family_identifier,
            "family": self.localized_family,
            "familyEnglish": self.family,
            "name": self.localized_full_name,
            "nameEnglish": self.full_name,
            "style": self.localized_style,
            "styleEnglish": self.style,
            "weight": self.weight,
        }


@dataclass(frozen=True)
class GlyphTransform:
    index: int
    x: float
    y: float
    scale_x: float
    scale_y: float


@dataclass(frozen=True)
class SvgColorTargets:
    """SVG内で印影色に置換する、明示的に指定された色の対象。"""

    fill: bool
    stroke: bool
    inherited: bool

    @property
    def enabled(self) -> bool:
        return self.fill or self.stroke or self.inherited


@dataclass(frozen=True)
class SvgAssetPlacement:
    source_svg: str
    view_box: tuple[float, float, float, float]
    x_percent: float
    y_percent: float
    size_percent: float
    color_targets: SvgColorTargets


@dataclass(frozen=True)
class StampDesign:
    format: str
    size_mm: float
    width_mm: float
    height_mm: float
    text: str
    company_name: str
    role_text: str
    font: FontRecord
    direction: str
    representation: str
    frame: str
    color: str
    frame_width: float
    padding: float
    corner_radius_mm: float
    line_width: float
    line_angle_snap: float
    line_detail: int
    text_scale_x: float
    text_scale_y: float
    line_spacing: float
    letter_spacing: float
    company_text_scale_x: float
    company_text_scale_y: float
    company_ring_offset_mm: float
    company_end_gap_mm: float
    embed_metadata: bool
    glyph_transforms: tuple[GlyphTransform, ...]
    company_glyph_transforms: tuple[GlyphTransform, ...]
    svg_assets: tuple[SvgAssetPlacement, ...]

    @property
    def body_text(self) -> str:
        return self.role_text if self.format == "company" else self.text

    @property
    def canvas_width(self) -> float:
        return CANVAS_SIZE * self.width_mm / self.height_mm

    @property
    def canvas_height(self) -> float:
        return CANVAS_SIZE

    @property
    def clip_frame(self) -> str:
        return self.frame if self.frame_width > 0 else "none"


def _font_directories() -> tuple[Path, ...]:
    home = Path.home()
    directories = [
        home / ".fonts",
        home / ".local" / "share" / "fonts",
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
    ]
    if os.name == "nt":
        windows = Path(os.environ.get("WINDIR", r"C:\\Windows"))
        directories.extend([windows / "Fonts", home / "AppData" / "Local" / "Microsoft" / "Windows" / "Fonts"])
    elif hasattr(os, "uname") and os.uname().sysname == "Darwin":
        directories.extend([Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library" / "Fonts"])
    return tuple(directory for directory in directories if directory.is_dir())


def _font_files() -> Iterable[Path]:
    seen: set[Path] = set()
    for directory in _font_directories():
        try:
            for path in directory.rglob("*"):
                if path.suffix.lower() in FONT_EXTENSIONS and path.is_file() and path not in seen:
                    seen.add(path)
                    yield path
        except OSError:
            continue


def _coretext_font_files() -> Iterable[Path]:
    """macOSのフォント登録情報から、実体フォントファイルを得る。"""
    if not (hasattr(os, "uname") and os.uname().sysname == "Darwin"):
        return
    try:
        from CoreText import (
            CTFontCollectionCreateFromAvailableFonts,
            CTFontCollectionCreateMatchingFontDescriptors,
            CTFontDescriptorCopyAttribute,
            kCTFontURLAttribute,
        )
    except ImportError:
        return
    try:
        collection = CTFontCollectionCreateFromAvailableFonts(None)
        descriptors = CTFontCollectionCreateMatchingFontDescriptors(collection) or ()
    except Exception:
        return
    for descriptor in descriptors:
        try:
            url = CTFontDescriptorCopyAttribute(descriptor, kCTFontURLAttribute)
            value = url.path() if url is not None else None
            path = Path(str(value)) if value else None
            if path is None or path.suffix.lower() not in FONT_EXTENSIONS or not path.is_file():
                continue
            yield path
        except Exception:
            continue


def _font_count(path: Path) -> int:
    if path.suffix.lower() != ".ttc":
        return 1
    try:
        collection = TTCollection(path, lazy=True)
        try:
            return len(collection.fonts)
        finally:
            collection.close()
    except Exception:
        return 0


def _font_sources() -> Iterable[tuple[Path, int]]:
    """直接検出とCore Text検出を統合し、同一ファイル・同一面を重複させない。"""
    seen: set[Path] = set()
    for paths in (_font_files(), _coretext_font_files()):
        for path in paths:
            try:
                resolved_path = path.resolve()
            except OSError:
                resolved_path = path
            if resolved_path in seen:
                continue
            seen.add(resolved_path)
            for index in range(_font_count(path)):
                yield path, index


def _font_names(font: TTFont, name_id: int, fallback: str) -> tuple[str, str]:
    """英語／既定名と日本語ローカライズ名をnameテーブルから得る。"""
    default = ""
    localized = ""
    try:
        records = [record for record in font["name"].names if record.nameID == name_id]
    except Exception:
        records = []
    for record in records:
        try:
            value = record.toUnicode().strip()
        except Exception:
            continue
        if not value:
            continue
        if record.platformID == 3 and record.langID == JAPANESE_WINDOWS_LANGUAGE:
            localized = localized or value
        elif record.platformID == 1 and record.langID == JAPANESE_MAC_LANGUAGE:
            localized = localized or value
        if record.platformID == 3 and record.langID in {0x409, 0}:
            default = default or value
        elif not default:
            default = value
    if not default:
        try:
            debug_name = font["name"].getDebugName(name_id)
        except Exception:
            debug_name = None
        default = str(debug_name).strip() if debug_name else fallback
    return default or fallback, localized or default or fallback


@lru_cache(maxsize=1)
def font_catalog() -> tuple[FontRecord, ...]:
    """直接のファイル走査とmacOSの登録情報を統合する。壊れたフォントは一覧から除外する。"""
    records: list[FontRecord] = []
    for path, index in _font_sources():
        try:
            font = TTFont(path, fontNumber=index, lazy=True)
            if not font.getBestCmap() or "hmtx" not in font or "hhea" not in font:
                font.close()
                continue
            legacy_family, localized_legacy_family = _font_names(font, 1, path.stem)
            typographic_family, localized_typographic_family = _font_names(font, 16, "")
            family = typographic_family or legacy_family
            localized_family = localized_typographic_family or localized_legacy_family
            full_name, localized_full_name = _font_names(font, 4, family)
            legacy_style, localized_legacy_style = _font_names(font, 2, "Regular")
            typographic_style, localized_typographic_style = _font_names(font, 17, "")
            style = typographic_style or legacy_style
            localized_style = localized_typographic_style or localized_legacy_style
            weight = int(font["OS/2"].usWeightClass) if "OS/2" in font else 400
            font.close()
        except Exception:
            continue
        source = f"{path.resolve()}:{index}".encode("utf-8")
        identifier = hashlib.sha256(source).hexdigest()[:20]
        family_source = family.casefold().strip().encode("utf-8")
        family_identifier = hashlib.sha256(family_source).hexdigest()[:16]
        records.append(
            FontRecord(
                identifier,
                family_identifier,
                family,
                localized_family,
                full_name,
                localized_full_name,
                style,
                localized_style,
                max(1, min(weight, 1000)),
                path,
                index,
            )
        )
    return tuple(
        sorted(
            records,
            key=lambda record: (
                record.localized_family.casefold(),
                record.weight,
                record.localized_style.casefold(),
                str(record.path),
            ),
        )
    )


def available_fonts() -> list[dict[str, str | int]]:
    # 先頭が「.」のファミリーはOS内部UI用で、通常のフォント選択画面には表示しない。
    return [record.as_api_value() for record in font_catalog() if not record.family.startswith(".") and not record.localized_family.startswith(".")]


def _font_by_identifier(identifier: Any) -> FontRecord:
    value = str(identifier or "")
    for record in font_catalog():
        if record.identifier == value:
            return record
    raise StampDesignError("選択したフォントが見つかりません。フォント一覧を更新してください。")


def _number(value: Any, label: str, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise StampDesignError(f"{label}は数値で指定してください。") from None
    if not minimum <= number <= maximum:
        raise StampDesignError(f"{label}は{minimum:g}から{maximum:g}の範囲で指定してください。")
    return number


def _color(value: Any) -> str:
    color = str(value or "")
    if len(color) != 7 or color[0] != "#" or any(character not in HEX_COLOR for character in color[1:]):
        raise StampDesignError("印影の色は #RRGGBB 形式で指定してください。")
    return color.lower()


def _text(value: Any, label: str, maximum: int, *, multiline: bool = True, allow_empty: bool = False) -> str:
    # 行頭・行末の全角／半角スペースも、印面レイアウトで使う文字として残す。
    text = str(value or "").replace("\r\n", "\n").replace("\r", "\n")
    if not text and allow_empty:
        return ""
    if not multiline and "\n" in text:
        raise StampDesignError(f"{label}には改行を入れられません。")
    lines = text.split("\n")
    visible_count = sum(1 for character in text if character != "\n")
    if not text or visible_count > maximum or len(lines) > 4 or any(not line for line in lines):
        suffix = "（改行は3回まで）" if multiline else ""
        raise StampDesignError(f"{label}は1〜{maximum}文字で指定してください{suffix}。")
    return text


def _svg_name(value: str) -> str:
    return value.rsplit("}", 1)[-1].lower()


def _svg_number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r"\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?)\s*(px|mm|cm|in|pt|pc)?\s*", value)
    if not match:
        return None
    factors = {None: 1, "px": 1, "mm": 96 / 25.4, "cm": 96 / 2.54, "in": 96, "pt": 96 / 72, "pc": 16}
    return float(match.group(1)) * factors[match.group(2)]


def _svg_view_box(root: ET.Element) -> tuple[float, float, float, float]:
    value = root.get("viewBox")
    if value:
        try:
            values = [float(item) for item in re.split(r"[\s,]+", value.strip()) if item]
        except ValueError:
            values = []
        if len(values) == 4 and all(math.isfinite(item) for item in values) and values[2] > 0 and values[3] > 0:
            return (values[0], values[1], values[2], values[3])
        raise StampDesignError("SVGのviewBoxが正しくありません。")
    width = _svg_number(root.get("width"))
    height = _svg_number(root.get("height"))
    if width and height and width > 0 and height > 0:
        return (0, 0, width, height)
    raise StampDesignError("SVGには正のviewBox、またはpx指定の幅と高さが必要です。")


def _is_external_svg_reference(value: str) -> bool:
    reference = value.strip().strip("\"'")
    return bool(reference) and not reference.startswith("#") and not reference.startswith("data:image/")


def _validated_svg_asset(value: Any) -> tuple[str, tuple[float, float, float, float]]:
    if not isinstance(value, str) or not value.strip():
        raise StampDesignError("配置するSVGデータが正しくありません。")
    encoded = value.encode("utf-8")
    if len(encoded) > MAX_SVG_ASSET_BYTES:
        raise StampDesignError("配置するSVGは5MB以下にしてください。")
    if re.search(r"<!\s*(?:doctype|entity)\b", value, flags=re.IGNORECASE):
        raise StampDesignError("DOCTYPEまたはENTITYを含むSVGは配置できません。")
    try:
        root = ET.fromstring(encoded)
    except ET.ParseError as error:
        raise StampDesignError("SVGを読み取れませんでした。") from error
    if _svg_name(root.tag) != "svg":
        raise StampDesignError("SVGのルート要素が正しくありません。")
    blocked = {"script", "foreignobject", "iframe", "object", "embed", "audio", "video", "animate", "animatetransform", "set"}
    for element in root.iter():
        if _svg_name(element.tag) in blocked:
            raise StampDesignError("スクリプトまたは埋め込み要素を含むSVGは配置できません。")
        for attribute, raw in list(element.attrib.items()):
            name = _svg_name(attribute)
            raw_value = str(raw)
            if name.startswith("on"):
                del element.attrib[attribute]
                continue
            if name in {"href", "src"} and _is_external_svg_reference(raw_value):
                raise StampDesignError("外部ファイルを参照するSVGは配置できません。")
            references = re.findall(r"url\(\s*['\"]?\s*([^\s'\")]+)", raw_value, flags=re.IGNORECASE)
            if any(_is_external_svg_reference(reference) for reference in references):
                raise StampDesignError("外部ファイルを参照するSVGは配置できません。")
            if name == "style" and re.search(r"@import|expression\s*\(", raw_value, flags=re.IGNORECASE):
                raise StampDesignError("外部スタイルを参照するSVGは配置できません。")
    view_box = _svg_view_box(root)
    if max(abs(item) for item in view_box) > 10_000_000:
        raise StampDesignError("SVGのサイズが大きすぎます。")
    root.set("width", "100%")
    root.set("height", "100%")
    root.set("x", "0")
    root.set("y", "0")
    root.set("preserveAspectRatio", root.get("preserveAspectRatio", "xMidYMid meet"))
    ET.register_namespace("", SVG_NAMESPACE)
    return ET.tostring(root, encoding="unicode"), view_box


def validate_svg_asset(value: Any) -> tuple[float, float, float, float]:
    """アップロード時にSVGの安全性と描画に必要な寸法を確認する。"""
    _, view_box = _validated_svg_asset(value)
    return view_box


def _svg_color_targets(value: Any, legacy_enabled: bool) -> SvgColorTargets:
    """SVGごとの色置換対象を読み込む。旧形式のデータにも安全に対応する。"""
    if value is None:
        return SvgColorTargets(legacy_enabled, legacy_enabled, legacy_enabled)
    if not isinstance(value, dict):
        raise StampDesignError("SVGの色置換対象が正しくありません。")
    return SvgColorTargets(
        fill=_boolean(value.get("fill", False), "SVGの塗りの色置換"),
        stroke=_boolean(value.get("stroke", False), "SVGの線の色置換"),
        inherited=_boolean(value.get("inherited", False), "SVGの親要素・styleの色置換"),
    )


def _svg_assets(value: Any, legacy_color_replacement: bool = False) -> tuple[SvgAssetPlacement, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > MAX_SVG_ASSETS:
        raise StampDesignError(f"配置できるSVGは{MAX_SVG_ASSETS}個までです。")
    result: list[SvgAssetPlacement] = []
    for item in value:
        if not isinstance(item, dict):
            raise StampDesignError("SVGの配置内容が正しくありません。")
        source_svg, view_box = _validated_svg_asset(item.get("svgContent"))
        result.append(
            SvgAssetPlacement(
                source_svg=source_svg,
                view_box=view_box,
                x_percent=_number(item.get("xPercent", 50), "SVGの横位置", -50, 150),
                y_percent=_number(item.get("yPercent", 50), "SVGの縦位置", -50, 150),
                size_percent=_number(item.get("sizePercent", 30), "SVGの大きさ", 2, 200),
                color_targets=_svg_color_targets(item.get("colorTargets"), legacy_color_replacement),
            )
        )
    return tuple(result)


def _glyph_transforms(value: Any, maximum_index: int) -> tuple[GlyphTransform, ...]:
    if value is None:
        return ()
    if not isinstance(value, list) or len(value) > maximum_index:
        raise StampDesignError("文字ごとの調整内容が正しくありません。")
    transforms: list[GlyphTransform] = []
    seen: set[int] = set()
    for item in value:
        if not isinstance(item, dict) or isinstance(item.get("index"), bool):
            raise StampDesignError("文字ごとの調整内容が正しくありません。")
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            raise StampDesignError("文字ごとの調整内容が正しくありません。") from None
        if index in seen or not 0 <= index < maximum_index:
            raise StampDesignError("文字ごとの調整対象が正しくありません。")
        seen.add(index)
        transforms.append(
            GlyphTransform(
                index,
                _number(item.get("x", 0), "文字の横位置", -300, 300),
                _number(item.get("y", 0), "文字の縦位置", -300, 300),
                _number(item.get("scaleX", 1), "文字の横倍率", 0.25, 3),
                _number(item.get("scaleY", 1), "文字の縦倍率", 0.25, 3),
            )
        )
    return tuple(sorted(transforms, key=lambda item: item.index))


def _boolean(value: Any, label: str) -> bool:
    if isinstance(value, bool):
        return value
    raise StampDesignError(f"{label}が正しくありません。")


def parse_design(payload: Any) -> StampDesign:
    if not isinstance(payload, dict):
        raise StampDesignError("印影作成の内容が正しくありません。")
    stamp_format = payload.get("format", "personal")
    if stamp_format not in {"personal", "company", "company_square", "stamp"}:
        raise StampDesignError("印影フォーマットが正しくありません。")

    stamp_length_mm = 0.0
    stamp_orientation = "horizontal"
    if stamp_format == "company":
        text = ""
        company_name = _text(payload.get("companyName", ""), "会社名", 28, multiline=False, allow_empty=True)
        role_text = _text(payload.get("roleText", ""), "中央の役職名", 12, allow_empty=True)
        default_size = 18
        frame = "round"
    elif stamp_format == "company_square":
        text = _text(payload.get("squareText", ""), "会社名", 16, allow_empty=True)
        company_name = ""
        role_text = ""
        default_size = 21
        frame = "square"
    elif stamp_format == "stamp":
        text = _text(payload.get("stampText", payload.get("text", "超極秘")), "文字", 12, allow_empty=True)
        company_name = ""
        role_text = ""
        default_size = 13
        frame = "square"
        stamp_length_mm = _number(payload.get("stampLengthMm", 27), "スタンプの長辺", 27, 42)
        if stamp_length_mm not in {27, 42}:
            raise StampDesignError("スタンプの長辺は27mmまたは42mmを選択してください。")
        stamp_orientation = payload.get("stampOrientation", "horizontal")
        if stamp_orientation not in {"horizontal", "vertical"}:
            raise StampDesignError("スタンプの向きが正しくありません。")
    else:
        text = _text(payload.get("text", ""), "文字", 12, allow_empty=True)
        company_name = ""
        role_text = ""
        default_size = 9.5
        frame = payload.get("frame", "round")

    direction = stamp_orientation if stamp_format == "stamp" else payload.get("direction", "horizontal")
    requested_representation = payload.get("representation", "outline")
    if direction not in {"horizontal", "vertical"}:
        raise StampDesignError("文字方向が正しくありません。")
    if requested_representation not in {"outline", "geometric"}:
        raise StampDesignError("文字表現が正しくありません。")
    # スタンプは可読性を優先した輪郭表現のみとし、UIを経由しない入力でも
    # 線刻化へ切り替わらないようにする。
    representation = "outline" if stamp_format == "stamp" else requested_representation
    if frame not in {"round", "square", "none"}:
        raise StampDesignError("枠の種類が正しくありません。")

    body_count = sum(1 for character in (role_text or text) if character != "\n")
    company_count = len(company_name)
    legacy_svg_color_replacement = _boolean(payload.get("svgAssetsUseStampColor", False), "SVG画像の色置換")
    svg_assets = _svg_assets(payload.get("svgAssets"), legacy_svg_color_replacement)
    size_mm = _number(payload.get("sizeMm", default_size), "仕上がりサイズ", 5, 42)
    if stamp_format == "stamp":
        width_mm, height_mm = (
            (stamp_length_mm, default_size)
            if stamp_orientation == "horizontal"
            else (default_size, stamp_length_mm)
        )
    else:
        width_mm = size_mm
        height_mm = size_mm
    return StampDesign(
        format=stamp_format,
        size_mm=size_mm,
        width_mm=width_mm,
        height_mm=height_mm,
        text=text,
        company_name=company_name,
        role_text=role_text,
        font=_font_by_identifier(payload.get("fontId")),
        direction=direction,
        representation=representation,
        frame=frame,
        color=_color(payload.get("color", "#d94236")),
        frame_width=_number(payload.get("frameWidth", 28), "枠線の太さ", 0, 80),
        padding=_number(payload.get("padding", 100), "余白", 30, 300),
        corner_radius_mm=_number(payload.get("cornerRadiusMm", 1), "角丸", 0, 5),
        line_width=_number(payload.get("lineWidth", 12), "線刻の太さ", 4, 90),
        line_angle_snap=_number(payload.get("lineAngleSnap", 8), "線刻の傾き吸着", 0, 25),
        # 線刻化は装飾的な補助機能として、各文字の長辺を240pxでサンプリングする。
        # 高解像度では輪郭の微細な凹凸まで枝分かれとして残りやすいため、読みやすさと
        # プレビュー速度のバランスを優先する。
        line_detail=round(_number(payload.get("lineDetail", 240), "線刻の精度", 160, 1280)),
        text_scale_x=_number(payload.get("textScaleX", 1), "全体の横倍率", 0.25, 3),
        text_scale_y=_number(payload.get("textScaleY", 1), "全体の縦倍率", 0.25, 3),
        line_spacing=_number(payload.get("lineSpacing", 0), "行間", -3, 3),
        letter_spacing=_number(payload.get("letterSpacing", 0), "文字間", -3, 3),
        company_text_scale_x=_number(payload.get("companyTextScaleX", 1), "外周文字の横倍率", 0.25, 3),
        company_text_scale_y=_number(payload.get("companyTextScaleY", 1), "外周文字の縦倍率", 0.25, 3),
        company_ring_offset_mm=_number(payload.get("companyRingOffsetMm", 0), "外周文字の内円からの距離調整", -3, 3),
        company_end_gap_mm=_number(payload.get("companyEndGapMm", 0), "外周文字の始終余白", 0, 8),
        embed_metadata=_boolean(payload.get("embedMetadata", False), "メタデータの埋め込み"),
        glyph_transforms=_glyph_transforms(payload.get("glyphTransforms"), body_count),
        company_glyph_transforms=_glyph_transforms(payload.get("companyGlyphTransforms"), company_count) if company_count else (),
        svg_assets=svg_assets,
    )


def _open_font(record: FontRecord) -> TTFont:
    try:
        return TTFont(record.path, fontNumber=record.index, lazy=True)
    except Exception as error:
        raise StampDesignError(f"フォントを開けませんでした: {record.localized_full_name}") from error


def _glyph(font: TTFont, character: str) -> tuple[str, int]:
    cmap = font.getBestCmap()
    metrics = font["hmtx"].metrics
    glyph_name = cmap.get(ord(character))
    if not glyph_name or glyph_name not in metrics:
        raise StampDesignError(f"選択したフォントには「{character}」の輪郭がありません。")
    return glyph_name, int(metrics[glyph_name][0])


def _path_for_glyph(glyph_set: Any, glyph_name: str) -> str:
    pen = SVGPathPen(glyph_set)
    glyph_set[glyph_name].draw(pen)
    return pen.getCommands()


def _adjusted_glyph(
    path: str,
    glyph_name: str,
    character: str,
    index: int,
    base_transform: str,
    center_x: float,
    center_y: float,
    adjustments: dict[int, GlyphTransform],
    index_attribute: str = "data-index",
    global_center_x: float = CANVAS_SIZE / 2,
    global_center_y: float = CANVAS_SIZE / 2,
    global_scale_x: float = 1,
    global_scale_y: float = 1,
) -> str:
    path_element = (
        f'<path {index_attribute}="{index}" data-character="{html.escape(character)}" '
        f'data-glyph="{html.escape(glyph_name)}" d="{path}" transform="{base_transform}"/>'
    )
    content = path_element
    if global_scale_x != 1 or global_scale_y != 1:
        content = (
            f'<g transform="translate({global_center_x:.4f} {global_center_y:.4f}) '
            f'scale({global_scale_x:.5f} {global_scale_y:.5f}) '
            f'translate({-global_center_x:.4f} {-global_center_y:.4f})">{content}</g>'
        )
    adjustment = adjustments.get(index)
    if not adjustment:
        return content
    adjusted_center_x = global_center_x + (center_x - global_center_x) * global_scale_x
    adjusted_center_y = global_center_y + (center_y - global_center_y) * global_scale_y
    offset_x = adjustment.x + adjusted_center_x * (1 - adjustment.scale_x)
    offset_y = adjustment.y + adjusted_center_y * (1 - adjustment.scale_y)
    return (
        f'<g transform="matrix({adjustment.scale_x:.5f} 0 0 {adjustment.scale_y:.5f} '
        f'{offset_x:.4f} {offset_y:.4f})">{content}</g>'
    )


def _indexed_lines(font: TTFont, text: str, glyph_set: Any) -> list[list[tuple[int, str, str, int, str]]]:
    lines: list[list[tuple[int, str, str, int, str]]] = []
    index = 0
    for line in text.split("\n"):
        result: list[tuple[int, str, str, int, str]] = []
        for character in line:
            glyph_name, advance = _glyph(font, character)
            result.append((index, character, glyph_name, advance, _path_for_glyph(glyph_set, glyph_name)))
            index += 1
        lines.append(result)
    return lines


def _layout_text_paths(
    font: TTFont,
    text: str,
    bounds: tuple[float, float, float, float],
    direction: str,
    transforms: tuple[GlyphTransform, ...],
    global_scale_x: float = 1,
    global_scale_y: float = 1,
    line_spacing: float = 0,
    letter_spacing: float = 0,
) -> list[str]:
    glyph_set = font.getGlyphSet()
    lines = _indexed_lines(font, text, glyph_set)
    upem = int(font["head"].unitsPerEm)
    ascent = int(font["hhea"].ascent)
    descent = int(font["hhea"].descent)
    line_height = max(1, ascent - descent)
    left, top, width, height = bounds
    global_center_x = left + width / 2
    global_center_y = top + height / 2
    adjustments = {item.index: item for item in transforms}
    elements: list[str] = []
    # 行間・文字間は0を基準にした加減算で扱う。-3では仮想ボディを
    # 重ねるほど詰められ、手書き系フォントでも余白を追い込める。
    default_line_advance = line_height + upem * 0.035
    line_advance = max(line_height * 0.08, default_line_advance + upem * 0.275 * line_spacing)
    tracking = upem * (0.025 + 0.275 * letter_spacing)

    def tracking_after(advance: int) -> float:
        # 負方向でも順序を反転させず、字送りを約8%まで詰められるようにする。
        return max(-advance + upem * 0.08, tracking)

    character_advance = max(line_height * 0.08, line_height + tracking)

    if direction == "horizontal":
        widths = [
            sum(item[3] for item in line) + sum(tracking_after(item[3]) for item in line[:-1])
            for line in lines
        ]
        total_height = line_height + line_advance * max(0, len(lines) - 1)
        scale = min(width / max(1, max(widths)), height / max(1, total_height))
        y = top + (height - total_height * scale) / 2
        for line, line_width in zip(lines, widths):
            center_y = y + line_height * scale / 2
            baseline = center_y + (ascent + descent) * scale / 2
            x = left + (width - line_width * scale) / 2
            for index, character, glyph_name, advance, path in line:
                base = f"translate({x:.4f} {baseline:.4f}) scale({scale:.8f} {-scale:.8f})"
                if path:
                    elements.append(
                        _adjusted_glyph(
                            path, glyph_name, character, index, base, x + advance * scale / 2, center_y, adjustments,
                            global_center_x=global_center_x, global_center_y=global_center_y,
                            global_scale_x=global_scale_x, global_scale_y=global_scale_y,
                        )
                    )
                x += (advance + (tracking_after(advance) if index != line[-1][0] else 0)) * scale
            y += line_advance * scale
        return elements

    column_widths = [max((item[3] for item in line), default=upem) for line in lines]
    # 縦組みの改行は列になる。負の行間では列も重なるが、順序は反転させない。
    column_gap = max(-min(column_widths) + upem * 0.08, upem * (0.035 + 0.275 * line_spacing))
    total_width = sum(column_widths) + column_gap * max(0, len(lines) - 1)
    maximum_height = max(
        line_height + character_advance * max(0, len(line) - 1)
        for line in lines
    )
    scale = min(width / max(1, total_width), height / max(1, maximum_height))
    right = left + (width + total_width * scale) / 2
    for line, column_width in zip(lines, column_widths):
        column_right = right
        column_left = column_right - column_width * scale
        total_line_height = (line_height + character_advance * max(0, len(line) - 1)) * scale
        y = top + (height - total_line_height) / 2
        for index, character, glyph_name, advance, path in line:
            center_y = y + line_height * scale / 2
            x = column_left + (column_width - advance) * scale / 2
            baseline = center_y + (ascent + descent) * scale / 2
            base = f"translate({x:.4f} {baseline:.4f}) scale({scale:.8f} {-scale:.8f})"
            if path:
                elements.append(
                    _adjusted_glyph(
                        path, glyph_name, character, index, base, column_left + column_width * scale / 2, center_y, adjustments,
                        global_center_x=global_center_x, global_center_y=global_center_y,
                        global_scale_x=global_scale_x, global_scale_y=global_scale_y,
                    )
                )
            y += character_advance * scale
        right = column_left - column_gap * scale
    return elements


def _circular_adjusted_glyph(
    path: str,
    glyph_name: str,
    character: str,
    index: int,
    center_x: float,
    center_y: float,
    rotation: float,
    scale: float,
    advance: int,
    vertical_center: float,
    adjustments: dict[int, GlyphTransform],
    global_scale_x: float,
    global_scale_y: float,
) -> str:
    """円周文字を接線・法線座標で変形し、文字中心を円周上に固定する。"""
    adjustment = adjustments.get(index)
    offset_x = adjustment.x if adjustment else 0
    offset_y = adjustment.y if adjustment else 0
    scale_x = global_scale_x * (adjustment.scale_x if adjustment else 1)
    scale_y = global_scale_y * (adjustment.scale_y if adjustment else 1)
    transform = (
        f"translate({center_x:.4f} {center_y:.4f}) rotate({rotation:.4f}) "
        f"translate({offset_x:.4f} {offset_y:.4f}) "
        f"scale({scale:.8f} {-scale:.8f}) "
        f"scale({scale_x:.5f} {scale_y:.5f}) "
        # フォント座標の原点は字面の左下にある。字送りの中央を原点へ移してから
        # 配置することで、先頭文字（例: 「・」）の中心を円の真上へ置く。
        f"translate({-advance / 2:.4f} {-vertical_center:.4f})"
    )
    return (
        f'<path data-company-index="{index}" data-character="{html.escape(character)}" '
        f'data-glyph="{html.escape(glyph_name)}" d="{path}" transform="{transform}"/>'
    )


def _circular_text_paths(
    font: TTFont,
    text: str,
    transforms: tuple[GlyphTransform, ...],
    global_scale_x: float = 1,
    global_scale_y: float = 1,
    ring_offset_mm: float = 0,
    end_gap_mm: float = 0,
    size_mm: float = 18,
) -> list[str]:
    if not text:
        return []
    glyph_set = font.getGlyphSet()
    glyphs = []
    for character in text:
        glyph_name, advance = _glyph(font, character)
        glyphs.append((character, glyph_name, advance, _path_for_glyph(glyph_set, glyph_name)))
    ascent = int(font["hhea"].ascent)
    descent = int(font["hhea"].descent)
    line_height = max(1, ascent - descent)
    # 外周文字の基準円は内円（r=245）と外枠の間に置く。オフセットは実寸mmで
    # 受け、サイズが16.5mmでも18mmでも同じ実寸だけ全周を内外へ移動する。
    # 文字の大きさと字間は基準円で決め、位置だけを移動させる。
    base_radius = 365
    radius = base_radius + ring_offset_mm / size_mm * CANVAS_SIZE
    radial_scale = 150 / line_height
    usual_step = 360 / max(1, len(glyphs))
    arc_width = base_radius * math.radians(usual_step) * 0.82
    scale = min(radial_scale, arc_width / max(item[2] for item in glyphs))
    if len(glyphs) == 1:
        angle_step = 0
    else:
        # 先頭／終端の字幅ぶんだけを円周の切れ目にする。0mmなら両端は接し、
        # 指定したmmだけ切れ目を広げられる。
        join_degrees = math.degrees((glyphs[0][2] + glyphs[-1][2]) * scale * 0.9 / (2 * base_radius))
        end_gap_degrees = min(300, end_gap_mm / size_mm * 360)
        angle_step = (360 - join_degrees - end_gap_degrees) / (len(glyphs) - 1)
    vertical_center = (ascent + descent) / 2
    adjustments = {item.index: item for item in transforms}
    elements: list[str] = []
    for index, (character, glyph_name, advance, path) in enumerate(glyphs):
        # 先頭文字の左右中心を円の真上に置き、始終余白だけを切れ目として加える。
        angle = -90 + index * angle_step
        radians = math.radians(angle)
        x = CANVAS_SIZE / 2 + radius * math.cos(radians)
        y = CANVAS_SIZE / 2 + radius * math.sin(radians)
        rotation = angle + 90
        if path:
            elements.append(
                _circular_adjusted_glyph(
                    path, glyph_name, character, index, x, y, rotation, scale, advance, vertical_center,
                    adjustments, global_scale_x, global_scale_y,
                )
            )
    return elements


def _company_body_elements(design: StampDesign) -> tuple[list[str], list[str]]:
    font = _open_font(design.font)
    try:
        ring = _circular_text_paths(
            font,
            design.company_name,
            design.company_glyph_transforms,
            design.company_text_scale_x,
            design.company_text_scale_y,
            design.company_ring_offset_mm,
            design.company_end_gap_mm,
            design.size_mm,
        )
        role = _layout_text_paths(
            font,
            design.role_text,
            (285, 285, 430, 430),
            design.direction,
            design.glyph_transforms,
            design.text_scale_x,
            design.text_scale_y,
            design.line_spacing,
            design.letter_spacing,
        )
        return ring, role
    finally:
        font.close()


def _stamp_body_elements(design: StampDesign) -> list[str]:
    if design.format == "company":
        ring, role = _company_body_elements(design)
        return ring + role
    font = _open_font(design.font)
    try:
        inner_width = design.canvas_width - design.padding * 2
        inner_height = design.canvas_height - design.padding * 2
        return _layout_text_paths(
            font,
            design.text,
            (design.padding, design.padding, inner_width, inner_height),
            design.direction,
            design.glyph_transforms,
            design.text_scale_x,
            design.text_scale_y,
            design.line_spacing,
            design.letter_spacing,
        )
    finally:
        font.close()


_NEIGHBOR_OFFSETS = ((0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1))


def _neighbors(point: tuple[int, int], pixels: set[tuple[int, int]]) -> list[tuple[int, int]]:
    x, y = point
    neighbors: list[tuple[int, int]] = []
    for dx, dy in _NEIGHBOR_OFFSETS:
        candidate = (x + dx, y + dy)
        if candidate not in pixels:
            continue
        # 直交する画素を経由できる角では斜め辺を追加しない。交点の周囲に
        # 1画素の三角形ができ、太いSVG線に小さな突起が出るのを防ぐ。
        if dx and dy and ((x + dx, y) in pixels or (x, y + dy) in pixels):
            continue
        neighbors.append(candidate)
    return neighbors


def _thin_pixels(pixels: set[tuple[int, int]]) -> set[tuple[int, int]]:
    """Zhang-Suen法で塗り輪郭を1画素幅の中心線へ細線化する。"""
    result = set(pixels)
    # 消去候補になり得るのは白地に接する輪郭だけ。従来は塗りつぶし領域の
    # 全画素を毎回走査していたため、1文字1280pxでは待ち時間が大きくなった。
    # 消去のたびに近傍だけを候補へ加えることで、高解像度のまま計算量を抑える。
    candidates = {
        point
        for point in result
        if any((point[0] + dx, point[1] + dy) not in result for dx, dy in _NEIGHBOR_OFFSETS)
    }
    while result:
        changed = False
        for phase in (0, 1):
            remove: list[tuple[int, int]] = []
            for x, y in candidates:
                values = [((x + dx, y + dy) in result) for dx, dy in _NEIGHBOR_OFFSETS]
                count = sum(values)
                if count < 2 or count > 6:
                    continue
                transitions = sum(not values[index] and values[(index + 1) % 8] for index in range(8))
                if transitions != 1:
                    continue
                north, east, south, west = values[0], values[2], values[4], values[6]
                if phase == 0:
                    if north and east and south or east and south and west:
                        continue
                elif north and east and west or north and south and west:
                    continue
                remove.append((x, y))
            if remove:
                result.difference_update(remove)
                changed = True
                affected = {
                    (x + dx, y + dy)
                    for x, y in remove
                    for dx, dy in _NEIGHBOR_OFFSETS
                    if (x + dx, y + dy) in result
                }
                candidates = {point for point in candidates if point in result} | affected
        if not changed:
            break
    return result


def _edge(a: tuple[int, int], b: tuple[int, int]) -> tuple[tuple[int, int], tuple[int, int]]:
    return (a, b) if a <= b else (b, a)


def _trace_pixels(pixels: set[tuple[int, int]]) -> list[list[tuple[int, int]]]:
    used: set[tuple[tuple[int, int], tuple[int, int]]] = set()
    paths: list[list[tuple[int, int]]] = []

    def follow(start: tuple[int, int], second: tuple[int, int]) -> list[tuple[int, int]]:
        points = [start, second]
        used.add(_edge(start, second))
        current = second
        while True:
            available = [neighbor for neighbor in _neighbors(current, pixels) if _edge(current, neighbor) not in used]
            if current != start and len(_neighbors(current, pixels)) != 2:
                break
            if not available:
                break
            following = available[0]
            used.add(_edge(current, following))
            points.append(following)
            current = following
            if current == start:
                break
        return points

    nodes = [point for point in pixels if len(_neighbors(point, pixels)) != 2]
    for point in nodes:
        for neighbor in _neighbors(point, pixels):
            if _edge(point, neighbor) not in used:
                paths.append(follow(point, neighbor))
    for point in pixels:
        for neighbor in _neighbors(point, pixels):
            if _edge(point, neighbor) not in used:
                paths.append(follow(point, neighbor))
    return paths


def _point_distance(point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]) -> float:
    if start == end:
        return math.dist(point, start)
    numerator = abs((end[1] - start[1]) * point[0] - (end[0] - start[0]) * point[1] + end[0] * start[1] - end[1] * start[0])
    return numerator / math.dist(start, end)


def _simplify(points: list[tuple[float, float]], tolerance: float = 1.2) -> list[tuple[float, float]]:
    if len(points) <= 2:
        return points
    distances = [_point_distance(point, points[0], points[-1]) for point in points[1:-1]]
    maximum = max(distances, default=0)
    if maximum <= tolerance:
        return [points[0], points[-1]]
    index = distances.index(maximum) + 1
    return _simplify(points[: index + 1], tolerance)[:-1] + _simplify(points[index:], tolerance)


def _smooth_points(points: list[tuple[int, int]], passes: int = 2) -> list[tuple[float, float]]:
    """中心線の画素階段を低域通過フィルターで均し、端点は動かさない。"""
    if len(points) < 3:
        return [(float(x), float(y)) for x, y in points]
    closed = points[0] == points[-1]
    result = [(float(x), float(y)) for x, y in (points[:-1] if closed else points)]
    for _ in range(passes):
        if closed:
            result = [
                (
                    (result[index - 1][0] + 2 * point[0] + result[(index + 1) % len(result)][0]) / 4,
                    (result[index - 1][1] + 2 * point[1] + result[(index + 1) % len(result)][1]) / 4,
                )
                for index, point in enumerate(result)
            ]
        else:
            result = [result[0]] + [
                (
                    (result[index - 1][0] + 2 * result[index][0] + result[index + 1][0]) / 4,
                    (result[index - 1][1] + 2 * result[index][1] + result[index + 1][1]) / 4,
                )
                for index in range(1, len(result) - 1)
            ] + [result[-1]]
    return result + [result[0]] if closed else result


def _simplified_trace(points: list[tuple[int, int]], pixels_per_canvas_unit: float) -> list[tuple[float, float]]:
    """解像度に応じた平滑化・簡略化で、曲線の階段状ノイズを抑える。"""
    # ラスターのpxではなくSVG座標系で一定の許容誤差になるようにする。
    # 解像度だけを上げて微細なノイズまで残してしまうことを避ける。
    tolerance = max(1.2, 3.2 * pixels_per_canvas_unit)
    # 高解像度では1画素が小さくなるので、もう一段だけ低域通過させる。
    smoothed = _smooth_points(points, passes=3 if pixels_per_canvas_unit >= 1 else 2)
    if len(smoothed) < 4 or smoothed[0] != smoothed[-1]:
        return _simplify(smoothed, tolerance)
    core = smoothed[:-1]
    middle = len(core) // 2
    first_half = _simplify(core[: middle + 1], tolerance)
    second_half = _simplify(core[middle:] + [core[0]], tolerance)
    return first_half[:-1] + second_half


def _snap_cardinal_segments(points: list[tuple[float, float]], threshold_degrees: float) -> list[tuple[float, float]]:
    """ほぼ水平・垂直な中心線を、その方向へ吸着して微小な傾きを除く。"""
    if threshold_degrees <= 0 or len(points) < 2:
        return points
    closed = len(points) > 3 and points[0] == points[-1]
    result = list(points[:-1] if closed else points)
    for index in range(1, len(result)):
        previous = result[index - 1]
        current = result[index]
        dx, dy = current[0] - previous[0], current[1] - previous[1]
        if not dx and not dy:
            continue
        degrees = abs(math.degrees(math.atan2(dy, dx))) % 90
        if min(degrees, 90 - degrees) > threshold_degrees:
            continue
        if abs(dx) >= abs(dy):
            result[index] = (current[0], previous[1])
        else:
            result[index] = (previous[0], current[1])
    return result + [result[0]] if closed else result


def _unit(vector: tuple[float, float]) -> tuple[float, float]:
    length = math.hypot(*vector)
    return (vector[0] / length, vector[1] / length) if length else (0.0, 0.0)


def _curve_tangent(points: list[tuple[float, float]], index: int, closed: bool) -> tuple[float, float]:
    if not closed and index == 0:
        return _unit((points[1][0] - points[0][0], points[1][1] - points[0][1]))
    if not closed and index == len(points) - 1:
        return _unit((points[-1][0] - points[-2][0], points[-1][1] - points[-2][1]))
    previous = points[index - 1]
    following = points[(index + 1) % len(points)]
    current = points[index]
    incoming = _unit((current[0] - previous[0], current[1] - previous[1]))
    outgoing = _unit((following[0] - current[0], following[1] - current[1]))
    # 約80度以上の折れは角として残し、それより緩い変化だけを滑らかにつなぐ。
    if incoming[0] * outgoing[0] + incoming[1] * outgoing[1] < 0.18:
        return (0.0, 0.0)
    return _unit((following[0] - previous[0], following[1] - previous[1]))


def _bezier_command(
    points: list[tuple[float, float]],
    scale_x: float,
    scale_y: float,
    offset_x: float = 0,
    offset_y: float = 0,
) -> str:
    scaled = [(offset_x + (x + 0.5) * scale_x, offset_y + (y + 0.5) * scale_y) for x, y in points]
    if len(scaled) < 2:
        return ""
    closed = len(scaled) > 3 and scaled[0] == scaled[-1]
    if closed:
        scaled = scaled[:-1]
    command = [f"M{scaled[0][0]:.3f} {scaled[0][1]:.3f}"]
    if len(scaled) == 2:
        command.append(f"L{scaled[1][0]:.3f} {scaled[1][1]:.3f}")
        return "".join(command)
    tangents = [_curve_tangent(scaled, index, closed) for index in range(len(scaled))]
    segment_count = len(scaled) if closed else len(scaled) - 1
    for index in range(segment_count):
        start = scaled[index]
        end = scaled[(index + 1) % len(scaled)]
        distance = math.dist(start, end) / 3
        first = (start[0] + tangents[index][0] * distance, start[1] + tangents[index][1] * distance)
        next_index = (index + 1) % len(scaled)
        second = (end[0] - tangents[next_index][0] * distance, end[1] - tangents[next_index][1] * distance)
        command.append(f"C{first[0]:.3f} {first[1]:.3f} {second[0]:.3f} {second[1]:.3f} {end[0]:.3f} {end[1]:.3f}")
    if closed:
        command.append("Z")
    return "".join(command)


@lru_cache(maxsize=128)
def _skeleton_commands(outline_paths: str, resolution: int, angle_snap: float) -> str:
    raster_svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="1000" height="1000" viewBox="0 0 1000 1000">'
        f'<g fill="#000000">{outline_paths}</g></svg>'
    )
    document = fitz.open(stream=raster_svg.encode("utf-8"), filetype="svg")
    try:
        page = document[0]
        bounds: fitz.Rect | None = None
        for drawing in page.get_drawings():
            rectangle = drawing["rect"]
            if rectangle.is_empty:
                continue
            bounds = rectangle if bounds is None else bounds | rectangle
        if bounds is None or bounds.is_empty:
            raise StampDesignError("選択した文字の輪郭を読み取れませんでした。")
        # 余白を少し取って輪郭を切らずに、文字の長辺が指定解像度になるよう切り出す。
        margin = max(3, min(30, max(bounds.width, bounds.height) * 0.025))
        clip = fitz.Rect(
            max(page.rect.x0, bounds.x0 - margin),
            max(page.rect.y0, bounds.y0 - margin),
            min(page.rect.x1, bounds.x1 + margin),
            min(page.rect.y1, bounds.y1 + margin),
        )
        sampling_scale = resolution / max(1, clip.width, clip.height)
        pixmap = page.get_pixmap(
            matrix=fitz.Matrix(sampling_scale, sampling_scale),
            clip=clip,
            alpha=True,
        )
        alpha_index = pixmap.n - 1
        samples = pixmap.samples
        pixels = {
            (x, y)
            for y in range(pixmap.height)
            for x in range(pixmap.width)
            if samples[(y * pixmap.width + x) * pixmap.n + alpha_index] >= 96
        }
        width = pixmap.width
        height = pixmap.height
        scale_x = clip.width / width
        scale_y = clip.height / height
    finally:
        document.close()
    skeleton = _thin_pixels(pixels)
    commands: list[str] = []
    for raw_points in _trace_pixels(skeleton):
        points = _snap_cardinal_segments(_simplified_trace(raw_points, sampling_scale), angle_snap)
        if len(points) < 2:
            continue
        command = _bezier_command(points, scale_x, scale_y, clip.x0, clip.y0)
        if command:
            commands.append(command)
    if not commands:
        raise StampDesignError("選択した文字から線刻表現を作れませんでした。別の書体をお試しください。")
    return " ".join(commands)


def _line_paths(outline_elements: list[str], design: StampDesign) -> str:
    paths: list[str] = []
    for index, outline in enumerate(outline_elements):
        commands = _skeleton_commands(outline, design.line_detail, design.line_angle_snap)
        paths.append(
            f'<path data-line-glyph="{index}" d="{commands}" fill="none" stroke="{design.color}" '
            f'stroke-width="{design.line_width:.3f}" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    return "".join(paths)


def _svg_paint_is_none(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"none", "transparent"}


def _recolored_svg_style(
    style: str,
    color: str,
    targets: SvgColorTargets,
    *,
    is_inherited_style: bool = False,
) -> str:
    def replace(match: re.Match[str]) -> str:
        property_name, value = match.group(1), match.group(2)
        property_key = property_name.casefold()
        if property_key == "fill":
            should_replace = targets.fill or (is_inherited_style and targets.inherited)
        elif property_key == "stroke":
            should_replace = targets.stroke or (is_inherited_style and targets.inherited)
        else:
            should_replace = targets.inherited
        if not should_replace or _svg_paint_is_none(value):
            return match.group(0)
        return f"{property_name}:{color}"

    return re.sub(r"\b(fill|stroke|color)\s*:\s*([^;}]+)", replace, style, flags=re.IGNORECASE)


def _svg_with_stamp_color(source_svg: str, color: str, targets: SvgColorTargets) -> str:
    """指定されたSVGの色だけを印影色に置換し、描画属性を新設しない。"""
    root = ET.fromstring(source_svg.encode("utf-8"))
    drawable = {"path", "circle", "ellipse", "rect", "polygon", "polyline", "line", "text", "tspan", "use"}
    inherited_elements = {"svg", "g", "symbol", "marker", "pattern", "mask", "clipPath"}
    for element in root.iter():
        name = _svg_name(element.tag)
        is_inherited_element = name in inherited_elements
        style = element.get("style")
        if style and (name in drawable or is_inherited_element):
            element.set(
                "style",
                _recolored_svg_style(style, color, targets, is_inherited_style=is_inherited_element),
            )
        if name == "style" and element.text:
            # CSSルールはどの要素に適用されるかをここでは判定できないため、
            # 親要素・style を選んだ場合は style 内の色も置換対象とする。
            element.text = _recolored_svg_style(element.text, color, targets, is_inherited_style=True)
        if name not in drawable and not is_inherited_element:
            continue
        fill = element.get("fill")
        stroke = element.get("stroke")
        if fill is not None and not _svg_paint_is_none(fill) and (targets.fill or (is_inherited_element and targets.inherited)):
            element.set("fill", color)
        if stroke is not None and not _svg_paint_is_none(stroke) and (targets.stroke or (is_inherited_element and targets.inherited)):
            element.set("stroke", color)
        if targets.inherited and element.get("color") is not None and not _svg_paint_is_none(element.get("color")):
            element.set("color", color)
    ET.register_namespace("", SVG_NAMESPACE)
    return ET.tostring(root, encoding="unicode")


def _position_svg_asset(source_svg: str, x: float, y: float, width: float, height: float) -> str:
    """ユーザーSVG自身を印面内のビューポートとして配置する。

    SVGをさらに別のSVGで包むと、負の座標を持つviewBoxや百分率の寸法を
    WebKitが正しく解決できない場合がある。そのため、検証済みのルートSVGへ
    直接、絶対座標の表示領域を与える。
    """
    root = ET.fromstring(source_svg.encode("utf-8"))
    root.set("x", f"{x:.4f}")
    root.set("y", f"{y:.4f}")
    root.set("width", f"{width:.4f}")
    root.set("height", f"{height:.4f}")
    root.set("preserveAspectRatio", root.get("preserveAspectRatio", "xMidYMid meet"))
    ET.register_namespace("", SVG_NAMESPACE)
    return ET.tostring(root, encoding="unicode")


def _svg_asset_elements(design: StampDesign) -> str:
    """ユーザーSVGを印面座標へ配置する。外側で本文クリップを適用する。"""
    elements: list[str] = []
    short_side = min(design.canvas_width, design.canvas_height)
    for index, asset in enumerate(design.svg_assets):
        _, _, source_width, source_height = asset.view_box
        long_side = short_side * asset.size_percent / 100
        if source_width >= source_height:
            width, height = long_side, long_side * source_height / source_width
        else:
            width, height = long_side * source_width / source_height, long_side
        x = design.canvas_width * asset.x_percent / 100 - width / 2
        y = design.canvas_height * asset.y_percent / 100 - height / 2
        source_svg = _svg_with_stamp_color(asset.source_svg, design.color, asset.color_targets) if asset.color_targets.enabled else asset.source_svg
        source_svg = _position_svg_asset(source_svg, x, y, width, height)
        elements.append(
            f'<g data-svg-asset="{index}">{source_svg}</g>'
        )
    return "".join(elements)


def _corner_radius(design: StampDesign) -> float:
    return design.corner_radius_mm / design.height_mm * design.canvas_height


def _frame(design: StampDesign) -> str:
    inset = design.frame_width / 2 + 28
    if design.format == "company":
        outer_radius = CANVAS_SIZE / 2 - inset
        inner_width = max(7, design.frame_width * 0.72)
        return (
            f'<circle cx="500" cy="500" r="{outer_radius:.3f}" fill="none" stroke="{design.color}" stroke-width="{design.frame_width:.3f}"/>'
            f'<circle cx="500" cy="500" r="245" fill="none" stroke="{design.color}" stroke-width="{inner_width:.3f}"/>'
        )
    if design.frame == "none" or design.frame_width <= 0:
        return ""
    if design.frame == "round":
        radius = min(design.canvas_width, design.canvas_height) / 2 - inset
        return f'<circle cx="{design.canvas_width / 2:.3f}" cy="{design.canvas_height / 2:.3f}" r="{radius:.3f}" fill="none" stroke="{design.color}" stroke-width="{design.frame_width:.3f}"/>'
    width = design.canvas_width - inset * 2
    height = design.canvas_height - inset * 2
    radius = _corner_radius(design)
    return f'<rect x="{inset:.3f}" y="{inset:.3f}" width="{width:.3f}" height="{height:.3f}" rx="{radius:.3f}" ry="{radius:.3f}" fill="none" stroke="{design.color}" stroke-width="{design.frame_width:.3f}"/>'


def _clip_definition(design: StampDesign) -> str:
    """本文を枠線の中心で切り、枠線は後から重ねて彫刻の接触感を保つ。"""
    if design.clip_frame == "none":
        return ""
    inset = design.frame_width / 2 + 28
    if design.frame == "round":
        radius = min(design.canvas_width, design.canvas_height) / 2 - inset
        shape = f'<circle cx="{design.canvas_width / 2:.3f}" cy="{design.canvas_height / 2:.3f}" r="{radius:.3f}"/>'
        if design.format == "company":
            return (
                '<defs>'
                f'<clipPath id="stamp-body-clip" clipPathUnits="userSpaceOnUse">{shape}</clipPath>'
                '<clipPath id="stamp-company-role-clip" clipPathUnits="userSpaceOnUse"><circle cx="500" cy="500" r="245"/></clipPath>'
                '</defs>'
            )
    else:
        width = design.canvas_width - inset * 2
        height = design.canvas_height - inset * 2
        radius = _corner_radius(design)
        shape = f'<rect x="{inset:.3f}" y="{inset:.3f}" width="{width:.3f}" height="{height:.3f}" rx="{radius:.3f}" ry="{radius:.3f}"/>'
    return f'<defs><clipPath id="stamp-body-clip" clipPathUnits="userSpaceOnUse">{shape}</clipPath></defs>'


def _stamp_text_metadata(design: StampDesign) -> str:
    if not design.embed_metadata:
        return ""
    # 検索用のメタデータではレイアウトの改行を文字列へ持ち込まない。
    texts = [re.sub(r"[\r\n]+", "", value) for value in (design.company_name, design.role_text, design.text) if value]
    payload = {"schema": "hanko-pdf/stamp-metadata/1", "format": design.format, "texts": texts}
    return f'<metadata id="hanko-stamp-metadata">{html.escape(json.dumps(payload, ensure_ascii=False))}</metadata>'


def create_stamp_svg(payload: Any) -> bytes:
    """SVGテキストを使わず、すべて輪郭パス・図形として印影を返す。"""
    design = payload if isinstance(payload, StampDesign) else parse_design(payload)
    clip = _clip_definition(design)
    if design.format == "company":
        ring_elements, role_elements = _company_body_elements(design)
        if design.representation == "geometric":
            ring_body = _line_paths(ring_elements, design)
            role_body = _line_paths(role_elements, design)
        else:
            ring_body = f'<g fill="{design.color}">{"".join(ring_elements)}</g>'
            role_body = f'<g fill="{design.color}">{"".join(role_elements)}</g>'
        ring_body += _svg_asset_elements(design)
        body = (
            f'<!--STAMP_COMPANY_RING_START--><g clip-path="url(#stamp-body-clip)">{ring_body}</g><!--STAMP_COMPANY_RING_END-->'
            f'<!--STAMP_COMPANY_ROLE_START--><g clip-path="url(#stamp-company-role-clip)">{role_body}</g><!--STAMP_COMPANY_ROLE_END-->'
        )
    else:
        outline_elements = _stamp_body_elements(design)
        if design.representation == "geometric":
            body = _line_paths(outline_elements, design)
        else:
            body = f'<g fill="{design.color}">{"".join(outline_elements)}</g>'
        body += _svg_asset_elements(design)
        body = f'<g clip-path="url(#stamp-body-clip)">{body}</g>' if clip else body
    body_layer = f'<!--STAMP_BODY_START--><g id="stamp-body">{body}</g><!--STAMP_BODY_END-->'
    frame_layer = f'<!--STAMP_FRAME_START--><g id="stamp-frame">{_frame(design)}</g><!--STAMP_FRAME_END-->'
    svg = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{design.width_mm:g}mm" height="{design.height_mm:g}mm" viewBox="0 0 {design.canvas_width:.6f} {design.canvas_height:.6f}" '
        f'data-stamp-format="{design.format}" data-stamp-clip="{design.clip_frame}" data-stamp-corner-radius-mm="{design.corner_radius_mm:g}" data-stamp-frame-width="{design.frame_width:g}">'
        f'{_stamp_text_metadata(design)}{clip}{body_layer}{frame_layer}</svg>'
    )
    return svg.encode("utf-8")
