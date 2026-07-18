from __future__ import annotations

import unittest
import re
import math
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fontTools.ttLib import TTFont

import app as app_module
from app import merge_stamp_keywords, open_vector_stamp, rotated_size, stamp_default_dimensions, stamp_metadata_texts, stamp_source_filename
from stamp_generator import (
    FontRecord,
    StampDesignError,
    _cached_font_catalog,
    _font_sources,
    _save_font_catalog_cache,
    _snap_cardinal_segments,
    available_fonts,
    configure_font_catalog_cache,
    create_stamp_svg,
    font_catalog,
    parse_design,
)


def japanese_font_id() -> str:
    for record in font_catalog():
        font = TTFont(record.path, fontNumber=record.index, lazy=True)
        try:
            cmap = font.getBestCmap() or {}
            if all(ord(character) in cmap for character in "田中英世株式会社代表取締役印"):
                return record.identifier
        finally:
            font.close()
    raise unittest.SkipTest("日本語のテスト用フォントがありません。")


class StampGeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.font_id = japanese_font_id()

    def base(self) -> dict[str, object]:
        return {
            "fontId": self.font_id,
            "color": "#ca3833",
            "frameWidth": 22,
        }

    def test_multiline_personal_stamp_is_outlined_svg(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中\n英世",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "glyphTransforms": [{"index": 2, "x": -18, "y": 10, "scaleX": 1.12, "scaleY": 1.08}],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('width="12mm"', svg)
        self.assertIn('data-index="3"', svg)
        self.assertIn("matrix(1.12000", svg)
        self.assertIn('<clipPath id="stamp-body-clip"', svg)
        self.assertGreaterEqual(svg.count('r="461.000"'), 2)
        body_layer = svg.split("<!--STAMP_BODY_START-->", 1)[1].split("<!--STAMP_BODY_END-->", 1)[0]
        frame_layer = svg.split("<!--STAMP_FRAME_START-->", 1)[1].split("<!--STAMP_FRAME_END-->", 1)[0]
        self.assertIn('clip-path="url(#stamp-body-clip)"', body_layer)
        self.assertNotIn("clip-path", frame_layer)
        self.assertNotIn("<text", svg)

    def test_company_stamp_has_outer_and_inner_frames(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中",
            "roleText": "代表取\n締役印",
            "direction": "vertical",
            "representation": "outline",
            "companyGlyphTransforms": [{"index": 1, "x": 8, "y": -5, "scaleX": 1.1, "scaleY": 1.05}],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertGreaterEqual(svg.count("<circle"), 3)
        self.assertIn('data-company-index="0"', svg)
        self.assertIn("translate(8.0000 -5.0000)", svg)
        self.assertIn("scale(1.10000 1.05000)", svg)
        self.assertIn('width="18mm"', svg)
        self.assertNotIn("<text", svg)

    def test_company_ring_scales_glyphs_without_scaling_their_circle(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中",
            "roleText": "代表印",
            "direction": "vertical",
            "representation": "outline",
        }
        baseline = create_stamp_svg(payload).decode("utf-8")
        scaled = create_stamp_svg(payload | {"companyTextScaleX": 1.7, "companyTextScaleY": 0.6}).decode("utf-8")
        centers = lambda svg: re.findall(
            r'data-company-index="\d+".*?transform="translate\(([-.\d]+) ([-.\d]+)\) rotate', svg,
        )
        self.assertEqual(centers(baseline), centers(scaled))
        self.assertIn("scale(1.70000 0.60000)", scaled)
        self.assertNotIn("translate(500.0000 500.0000) scale(1.70000 0.60000)", scaled)

    def test_company_ring_distance_offset_moves_all_glyph_centers_radially(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中",
            "roleText": "代表印",
            "direction": "vertical",
            "representation": "outline",
        }
        baseline = create_stamp_svg(payload).decode("utf-8")
        moved = create_stamp_svg(payload | {"companyRingOffsetMm": -1.5}).decode("utf-8")
        centers = lambda svg: [
            (float(x), float(y))
            for x, y in re.findall(
                r'data-company-index="\d+".*?transform="translate\(([-.\d]+) ([-.\d]+)\) rotate', svg,
            )
        ]
        baseline_centers = centers(baseline)
        moved_centers = centers(moved)
        self.assertEqual(len(baseline_centers), len(moved_centers))
        scales = lambda svg: re.findall(
            r'data-company-index="\d+".*?rotate\([-.\d]+\) translate\([-.\d]+ [-.\d]+\) scale\(([-.\d]+ [-.\d]+)\)',
            svg,
        )
        self.assertEqual(scales(baseline), scales(moved))
        for x, y in baseline_centers:
            self.assertAlmostEqual(math.hypot(x - 500, y - 500), 365, places=3)
        expected_radius = 365 - 1.5 / 18 * 1000
        for x, y in moved_centers:
            self.assertAlmostEqual(math.hypot(x - 500, y - 500), expected_radius, places=3)

    def test_company_ring_first_glyph_center_is_at_top_of_circle(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "・株式会社田中",
            "roleText": "代表印",
            "direction": "vertical",
            "representation": "outline",
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        match = re.search(
            r'data-company-index="0".*?transform="translate\(([-.\d]+) ([-.\d]+)\) rotate\(([-.\d]+)\) '
            r'translate\(0\.0000 0\.0000\) scale\([-.\d]+ [-.\d]+\) scale\([-.\d]+ [-.\d]+\) '
            r'translate\(([-.\d]+) ([-.\d]+)\)"',
            svg,
        )
        self.assertIsNotNone(match)
        assert match is not None
        center_x, center_y, rotation, origin_x, origin_y = map(float, match.groups())
        self.assertAlmostEqual(center_x, 500)
        self.assertAlmostEqual(center_y, 135)
        self.assertAlmostEqual(rotation, 0)
        self.assertLess(origin_x, 0)
        self.assertLess(origin_y, 0)

    def test_company_ring_individual_adjustments_use_tangent_and_normal_axes(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中",
            "roleText": "代表印",
            "direction": "vertical",
            "representation": "outline",
            "companyGlyphTransforms": [{"index": 2, "x": 12, "y": -7, "scaleX": 1.15, "scaleY": 0.85}],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertRegex(
            svg,
            r'data-company-index="2".*?rotate\([-.\d]+\) translate\(12\.0000 -7\.0000\) '
            r'scale\([-.\d]+ [-.\d]+\) scale\(1\.15000 0\.85000\) translate\([-.\d]+ [-.\d]+\)',
        )

    def test_company_stamp_starts_at_top_and_clips_role_to_inner_circle(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中印堂",
            "roleText": "代表取\n締役印",
            "direction": "vertical",
            "representation": "outline",
            "companyEndGapMm": 0,
            "textScaleX": 1.4,
            "textScaleY": 1.2,
            "companyTextScaleX": 1.1,
            "companyTextScaleY": 1.05,
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('id="stamp-company-role-clip"', svg)
        self.assertIn('translate(500.0000 135.0000) rotate(0.0000)', svg)
        self.assertIn('clip-path="url(#stamp-company-role-clip)"', svg)
        self.assertIn('scale(1.40000 1.20000)', svg)
        self.assertIn('scale(1.10000 1.05000)', svg)

    def test_geometric_mode_outputs_centerline_paths(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 10.5,
            "text": "田中",
            "direction": "horizontal",
            "representation": "geometric",
            "frame": "round",
            "padding": 80,
            "lineWidth": 12,
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertEqual(svg.count('data-line-glyph="'), 2)
        self.assertIn('stroke-linecap="round"', svg)
        self.assertIn("C", svg)
        self.assertNotIn("<rect", svg)
        self.assertNotIn("<text", svg)

    def test_high_resolution_line_mode_changes_curve_sampling(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "u",
            "direction": "horizontal",
            "representation": "geometric",
            "frame": "round",
            "padding": 100,
            "lineWidth": 12,
        }
        self.assertEqual(parse_design(payload).line_detail, 240)
        low_resolution = create_stamp_svg(payload | {"lineDetail": 160})
        high_resolution = create_stamp_svg(payload | {"lineDetail": 240})
        self.assertNotEqual(low_resolution, high_resolution)
        with self.assertRaises(StampDesignError):
            parse_design(payload | {"lineDetail": 1281})

    def test_line_angle_snap_straightens_nearly_cardinal_segments(self) -> None:
        snapped = _snap_cardinal_segments([(0.0, 0.0), (100.0, 6.0), (104.0, 110.0)], 8)
        self.assertEqual(snapped, [(0.0, 0.0), (100.0, 0.0), (100.0, 110.0)])
        self.assertEqual(
            _snap_cardinal_segments([(0.0, 0.0), (100.0, 6.0)], 0),
            [(0.0, 0.0), (100.0, 6.0)],
        )

    def test_stamp_format_forces_outline_representation(self) -> None:
        payload = self.base() | {
            "format": "stamp",
            "stampLengthMm": 27,
            "stampOrientation": "horizontal",
            "stampText": "回覧",
            "representation": "geometric",
        }
        design = parse_design(payload)
        self.assertEqual(design.representation, "outline")
        self.assertEqual(design.line_angle_snap, 8)
        with self.assertRaises(StampDesignError):
            parse_design(payload | {"lineAngleSnap": 26})

    def test_company_square_has_size_and_rounded_clip(self) -> None:
        payload = self.base() | {
            "format": "company_square",
            "sizeMm": 21,
            "squareText": "株式会社\n田中",
            "direction": "vertical",
            "representation": "outline",
            "padding": 60,
            "cornerRadiusMm": 1.5,
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('width="21mm"', svg)
        self.assertIn("<clipPath", svg)
        self.assertIn("rx=", svg)
        self.assertIn('<rect x="39.000"', svg)

    def test_pdf_conversion_bakes_in_svg_clip(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 9.5,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 30,
            "glyphTransforms": [
                {"index": 0, "x": -100, "y": 0, "scaleX": 1.5, "scaleY": 1.4},
                {"index": 1, "x": 100, "y": 0, "scaleX": 1.5, "scaleY": 1.4},
            ],
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stamp.svg"
            path.write_bytes(create_stamp_svg(payload))
            document = open_vector_stamp(path)
            try:
                content = b"".join(
                    document.xref_stream(xref)
                    for xref in range(1, document.xref_length())
                    if document.xref_is_stream(xref)
                )
                page_content = b"".join(document.xref_stream(xref) for xref in document[0].get_contents())
            finally:
                document.close()
        self.assertIn(b"W n", content)
        self.assertEqual(page_content.count(b" Do"), 2)

    def test_company_pdf_conversion_clips_outer_and_inner_text_layers(self) -> None:
        payload = self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "株式会社田中印堂",
            "roleText": "代表取\n締役印",
            "direction": "vertical",
            "representation": "outline",
        }
        with TemporaryDirectory() as directory:
            path = Path(directory) / "company.svg"
            path.write_bytes(create_stamp_svg(payload))
            document = open_vector_stamp(path)
            try:
                content = b"".join(
                    document.xref_stream(xref)
                    for xref in range(1, document.xref_length())
                    if document.xref_is_stream(xref)
                )
                page_content = b"".join(document.xref_stream(xref) for xref in document[0].get_contents())
            finally:
                document.close()
        self.assertGreaterEqual(content.count(b"W n"), 2)
        self.assertEqual(page_content.count(b" Do"), 3)

    def test_font_api_exposes_family_style_and_weight(self) -> None:
        font = available_fonts()[0]
        self.assertTrue(font["familyId"])
        self.assertTrue(font["family"])
        self.assertTrue(font["style"])
        self.assertIsInstance(font["weight"], int)

    def test_font_sources_merge_coretext_files_without_duplicates(self) -> None:
        direct = Path("/fonts/direct.ttf")
        registered = Path("/fonts/adobe.otf")
        with (
            patch("stamp_generator._font_files", return_value=iter([direct])),
            patch("stamp_generator._coretext_font_files", return_value=iter([direct, registered, registered])),
            patch("stamp_generator._font_count", side_effect=lambda path: 2 if path == direct else 1),
        ):
            self.assertEqual(list(_font_sources()), [(direct, 0), (direct, 1), (registered, 0)])

    def test_font_catalog_cache_uses_unchanged_font_manifest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / "sample.ttf"
            font_path.write_bytes(b"font")
            cache_path = root / "font-catalog-v1.json"
            record = FontRecord(
                "font-id", "family-id", "Sample", "サンプル", "Sample Regular", "サンプル レギュラー",
                "Regular", "標準", 400, font_path, 0,
            )
            configure_font_catalog_cache(cache_path)
            try:
                _save_font_catalog_cache((font_path,), (record,))
                self.assertEqual(_cached_font_catalog((font_path,)), (record,))
                font_path.write_bytes(b"changed font")
                self.assertIsNone(_cached_font_catalog((font_path,)))
            finally:
                configure_font_catalog_cache(None)

    def test_global_scales_and_negative_spacing_accept_full_range(self) -> None:
        payload = self.base() | {
            "format": "company_square",
            "sizeMm": 24,
            "squareText": "株式会社\n田中印堂\n之印",
            "direction": "vertical",
            "representation": "outline",
            "textScaleX": 3,
            "textScaleY": 3,
            "lineSpacing": -3,
            "letterSpacing": 3,
            "glyphTransforms": [{"index": 0, "x": 12, "y": -8, "scaleX": 3, "scaleY": 3}],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('scale(3.00000 3.00000)', svg)
        self.assertIn('matrix(3.00000 0 0 3.00000', svg)
        with self.assertRaises(StampDesignError):
            parse_design(payload | {"textScaleX": 3.01})
        with self.assertRaises(StampDesignError):
            parse_design(payload | {"lineSpacing": -3.01})
        with self.assertRaises(StampDesignError):
            parse_design(payload | {"letterSpacing": 3.01})

    def test_line_and_letter_spacing_change_the_layout(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
        }
        compact = create_stamp_svg(payload | {"lineSpacing": -3, "letterSpacing": -3})
        spacious = create_stamp_svg(payload | {"lineSpacing": 3, "letterSpacing": 3})
        self.assertNotEqual(compact, spacious)
        coordinates = lambda svg: [
            float(x)
            for _, x, _ in re.findall(r'data-index="(\d+)".*?transform="translate\(([^ ]+) ([^)]*)\)', svg.decode("utf-8"))
        ]
        compact_x = coordinates(compact)
        spacious_x = coordinates(spacious)
        self.assertGreater(spacious_x[1] - spacious_x[0], compact_x[1] - compact_x[0] + 70)

    def test_leading_and_trailing_half_and_full_width_spaces_are_preserved(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": " 田中　",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "glyphTransforms": [{"index": 3, "x": -18, "y": 0, "scaleX": 1, "scaleY": 1}],
        }
        design = parse_design(payload)
        self.assertEqual(design.text, " 田中　")
        self.assertEqual(len(design.glyph_transforms), 1)
        self.assertEqual(design.glyph_transforms[0].index, 3)

    def test_svg_assets_are_embedded_inside_the_stamp_mask(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": " 田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path fill="#123456" d="M0 0h20v10H0z"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 180,
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        body_layer = svg.split("<!--STAMP_BODY_START-->", 1)[1].split("<!--STAMP_BODY_END-->", 1)[0]
        self.assertIn('data-svg-asset="0"', body_layer)
        self.assertIn('clip-path="url(#stamp-body-clip)"', body_layer)
        asset_svg = body_layer.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertEqual(asset_svg.count("<svg"), 1)
        self.assertIn('x="', asset_svg)
        self.assertIn('y="', asset_svg)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "asset-stamp.svg"
            path.write_text(svg, encoding="utf-8")
            document = open_vector_stamp(path)
            try:
                self.assertGreater(document[0].rect.width, 0)
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
                colors = {tuple(pixmap.samples[index:index + pixmap.n]) for index in range(0, len(pixmap.samples), pixmap.n)}
                self.assertIn((18, 52, 86, 255), colors)
            finally:
                document.close()

    def test_empty_text_allows_an_svg_only_stamp(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path fill="#123456" d="M0 0h20v10H0z"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
                "colorTargets": {"fill": False, "stroke": False, "inherited": False},
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('data-svg-asset="0"', svg)
        self.assertNotIn('data-index="0"', svg)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "svg-only-stamp.svg"
            path.write_text(svg, encoding="utf-8")
            document = open_vector_stamp(path)
            try:
                pixmap = document[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
                self.assertGreater(sum(pixmap.samples[index + 3] > 0 for index in range(0, len(pixmap.samples), pixmap.n)), 0)
            finally:
                document.close()

    def test_empty_text_is_allowed_for_every_stamp_format(self) -> None:
        payloads = [
            self.base() | {
                "format": "personal", "sizeMm": 12, "text": "", "direction": "horizontal", "representation": "outline", "frame": "round",
            },
            self.base() | {
                "format": "company", "sizeMm": 18, "companyName": "", "roleText": "", "direction": "vertical", "representation": "outline",
            },
            self.base() | {
                "format": "company_square", "sizeMm": 21, "squareText": "", "direction": "vertical", "representation": "outline", "frame": "square",
            },
            self.base() | {
                "format": "stamp", "stampLengthMm": 27, "stampOrientation": "horizontal", "stampText": "", "representation": "outline", "frameWidth": 0,
            },
        ]
        for payload in payloads:
            design = parse_design(payload)
            self.assertEqual(create_stamp_svg(design)[:5], b"<?xml")

    def test_svg_asset_color_targets_recolor_fill_and_stroke(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path fill="#123456" d="M0 0h20v10H0z"/><path fill="none" stroke="#654321" d="M0 0L20 10"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
                "colorTargets": {"fill": True, "stroke": True, "inherited": False},
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        asset_svg = svg.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertIn('fill="#ca3833"', asset_svg)
        self.assertIn('stroke="#ca3833"', asset_svg)
        self.assertNotIn("#123456", asset_svg)
        self.assertNotIn("#654321", asset_svg)

    def test_svg_asset_color_targets_do_not_add_fill_to_stroke_only_paths(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path stroke="#111111" stroke-width="2" d="M0 0L20 10"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
                "colorTargets": {"fill": False, "stroke": True, "inherited": False},
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        asset_svg = svg.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertIn('stroke="#ca3833"', asset_svg)
        self.assertNotIn('fill="#ca3833"', asset_svg)
        self.assertNotIn('fill="', asset_svg)

    def test_svg_asset_color_targets_recolor_parent_fill(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10" fill="#1f1f1f"><path d="M0 0h20v10H0z"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
                "colorTargets": {"fill": False, "stroke": False, "inherited": True},
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        asset_svg = svg.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertIn('fill="#ca3833"', asset_svg)
        self.assertNotIn("#1f1f1f", asset_svg)

    def test_svg_asset_color_targets_recolor_internal_style_rules(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><style>.shape { fill: #1f1f1f; stroke: #222222; }</style><path class="shape" d="M0 0h20v10H0z"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
                "colorTargets": {"fill": False, "stroke": False, "inherited": True},
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        asset_svg = svg.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertIn("fill:#ca3833", asset_svg)
        self.assertIn("stroke:#ca3833", asset_svg)
        self.assertNotIn("#1f1f1f", asset_svg)
        self.assertNotIn("#222222", asset_svg)

    def test_legacy_svg_color_replacement_does_not_fill_stroke_only_paths(self) -> None:
        payload = self.base() | {
            "format": "personal",
            "sizeMm": 12,
            "text": "田中",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
            "padding": 70,
            "svgAssetsUseStampColor": True,
            "svgAssets": [{
                "svgContent": '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10"><path stroke="#111111" stroke-width="2" d="M0 0L20 10"/></svg>',
                "xPercent": 50,
                "yPercent": 50,
                "sizePercent": 50,
            }],
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        asset_svg = svg.split('<g data-svg-asset="0">', 1)[1].split("</g>", 1)[0]
        self.assertIn('stroke="#ca3833"', asset_svg)
        self.assertNotIn('fill="', asset_svg)

    def test_rectangular_stamp_embeds_text_metadata(self) -> None:
        payload = self.base() | {
            "format": "stamp",
            "sizeMm": 27,
            "stampLengthMm": 27,
            "stampOrientation": "horizontal",
            "stampText": "回覧\n至急",
            "direction": "horizontal",
            "representation": "outline",
            "frameWidth": 0,
            "embedMetadata": True,
        }
        svg = create_stamp_svg(payload).decode("utf-8")
        self.assertIn('width="27mm" height="13mm"', svg)
        self.assertIn('data-stamp-format="stamp"', svg)
        self.assertIn('data-stamp-clip="none"', svg)
        self.assertIn('<metadata id="hanko-stamp-metadata">', svg)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "stamp.svg"
            path.write_text(svg, encoding="utf-8")
            self.assertEqual(stamp_default_dimensions(path), (27.0, 13.0, True))
            self.assertEqual(stamp_metadata_texts(path), ["回覧至急"])

    def test_generated_svg_filename_uses_entered_text_safely(self) -> None:
        design = parse_design(self.base() | {
            "format": "personal",
            "sizeMm": 10.5,
            "text": "田中/英世",
            "direction": "horizontal",
            "representation": "outline",
            "frame": "round",
        })
        self.assertEqual(stamp_source_filename(design), "stamp_田中_英世.svg")
        company_design = parse_design(self.base() | {
            "format": "company",
            "sizeMm": 18,
            "companyName": "・合同会社アメショ商会",
            "roleText": "代表取\n締役印",
            "direction": "vertical",
            "representation": "outline",
        })
        self.assertEqual(stamp_source_filename(company_design), "stamp_・合同会社アメショ商会_代表取締役印.svg")

    def test_pdf_keywords_merge_and_rotation_bounds(self) -> None:
        document = fitz.open()
        try:
            document.new_page()
            metadata = document.metadata
            metadata["keywords"] = "既存"
            document.set_metadata(metadata)
            merge_stamp_keywords(document, ["回覧", "既存", "至急"])
            self.assertEqual(document.metadata["keywords"], "既存, 回覧, 至急")
        finally:
            document.close()
        width, height = rotated_size(27, 13, 90)
        self.assertAlmostEqual(width, 13)
        self.assertAlmostEqual(height, 27)

    def test_supplied_samples_open_as_pdfs_and_vector_stamps(self) -> None:
        sample_directory = Path(__file__).resolve().parents[1] / "dev_docs" / "sample"
        if not sample_directory.is_dir():
            self.skipTest("ローカル開発用サンプルは公開ソースに含めません。")
        pdfs = list(sample_directory.glob("*.pdf"))
        stamps = list(sample_directory.glob("*.svg"))
        self.assertGreaterEqual(len(pdfs), 3)
        self.assertGreaterEqual(len(stamps), 6)
        for path in pdfs:
            document = fitz.open(path)
            try:
                self.assertGreater(document.page_count, 0, path.name)
            finally:
                document.close()
        for path in stamps:
            document = open_vector_stamp(path)
            try:
                self.assertGreater(document[0].rect.width, 0, path.name)
                self.assertGreater(document[0].rect.height, 0, path.name)
            finally:
                document.close()


class FontPreloadTests(unittest.TestCase):
    def test_frozen_windows_uses_local_app_data(self) -> None:
        with (
            patch.object(app_module.sys, "frozen", True, create=True),
            patch.object(app_module.sys, "platform", "win32"),
            patch.dict(app_module.os.environ, {"LOCALAPPDATA": r"C:\\Users\\TestUser\\AppData\\Local"}, clear=True),
        ):
            self.assertEqual(
                app_module.application_data_dir(),
                Path(r"C:\\Users\\TestUser\\AppData\\Local") / "Hanko PDF",
            )

    def test_font_status_reports_runtime_and_scan_state(self) -> None:
        scan = {"state": "scanning", "completed": 12, "total": 40, "current": "YuGothM.ttc", "cache": False}
        with (
            patch.object(app_module.sys, "frozen", True, create=True),
            patch.object(app_module.sys, "platform", "win32"),
            patch.object(app_module, "font_scan_status", return_value=scan),
        ):
            self.assertEqual(
                app_module.get_font_status(),
                {"platform": "win32", "frozen": True, **scan},
            )

    def test_start_font_preload_starts_one_daemon_thread(self) -> None:
        with (
            patch.object(app_module, "_font_preload_thread", None),
            patch.object(app_module, "Thread") as thread_class,
        ):
            thread = thread_class.return_value
            app_module.start_font_preload()

        thread_class.assert_called_once_with(
            target=app_module._preload_fonts,
            name="hanko-font-preload",
            daemon=True,
        )
        thread.start.assert_called_once_with()

    def test_font_endpoint_returns_pending_while_background_preload_runs(self) -> None:
        class RunningThread:
            def is_alive(self) -> bool:
                return True

        with (
            patch.object(app_module, "_font_preload_thread", RunningThread()),
            patch.object(app_module, "available_fonts") as load_fonts,
        ):
            response = app_module.get_fonts()

        self.assertEqual(response.status_code, 202)
        load_fonts.assert_not_called()

    def test_font_endpoint_returns_fonts_after_background_preload(self) -> None:
        class FinishedThread:
            def is_alive(self) -> bool:
                return False

        fonts = [{"id": "font-1", "family": "Test"}]
        with (
            patch.object(app_module, "_font_preload_thread", FinishedThread()),
            patch.object(app_module, "available_fonts", return_value=fonts) as load_fonts,
        ):
            response = app_module.get_fonts()

        load_fonts.assert_called_once_with()
        self.assertEqual(response, {"fonts": fonts})


if __name__ == "__main__":
    unittest.main()
