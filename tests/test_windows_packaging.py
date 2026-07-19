from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

import launcher as launcher_module


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "packaging" / "windows" / "msix" / "AppxManifest.xml.template"
NAMESPACES = {
    "appx": "http://schemas.microsoft.com/appx/manifest/foundation/windows10",
    "uap": "http://schemas.microsoft.com/appx/manifest/uap/windows10",
    "rescap": "http://schemas.microsoft.com/appx/manifest/foundation/windows10/restrictedcapabilities",
}


class WindowsPackagingTests(unittest.TestCase):
    def test_manifest_uses_reserved_store_identity(self) -> None:
        root = ET.parse(MANIFEST).getroot()
        identity = root.find("appx:Identity", NAMESPACES)
        self.assertIsNotNone(identity)
        assert identity is not None
        self.assertEqual(identity.attrib["Name"], "yupyom.HankoPDF")
        self.assertEqual(identity.attrib["Publisher"], "CN=7927EB7F-72E2-4822-A979-3ADE223146BE")
        self.assertEqual(identity.attrib["ProcessorArchitecture"], "x64")
        self.assertEqual(identity.attrib["Version"], "{{VERSION}}")

    def test_manifest_launches_the_pyinstaller_desktop_app(self) -> None:
        root = ET.parse(MANIFEST).getroot()
        application = root.find("appx:Applications/appx:Application", NAMESPACES)
        self.assertIsNotNone(application)
        assert application is not None
        self.assertEqual(application.attrib["Executable"], "Hanko PDF.exe")
        self.assertEqual(application.attrib["EntryPoint"], "Windows.FullTrustApplication")
        capability = root.find("appx:Capabilities/rescap:Capability", NAMESPACES)
        self.assertIsNotNone(capability)
        assert capability is not None
        self.assertEqual(capability.attrib["Name"], "runFullTrust")

    def test_only_frozen_windows_uses_webview_profile_directory(self) -> None:
        with (
            patch.object(launcher_module.sys, "platform", "win32"),
            patch.object(launcher_module.sys, "frozen", True, create=True),
            patch.object(launcher_module, "DATA_DIR", Path("C:/app-data")),
            patch.object(launcher_module.os, "getpid", return_value=1234),
            patch.object(launcher_module.uuid, "uuid4", side_effect=["test-uuid-1", "test-uuid-2"]),
        ):
            self.assertEqual(
                launcher_module.webview_start_options(),
                {
                    "storage_path": str(Path("C:/app-data") / "webview-sessions" / "1234-test-uuid-1"),
                    "private_mode": True,
                },
            )
            self.assertEqual(
                launcher_module.webview_start_options(),
                {
                    "storage_path": str(Path("C:/app-data") / "webview-sessions" / "1234-test-uuid-2"),
                    "private_mode": True,
                },
            )

        with (
            patch.object(launcher_module.sys, "platform", "darwin"),
            patch.object(launcher_module.sys, "frozen", True, create=True),
        ):
            self.assertEqual(launcher_module.webview_start_options(), {})

    def test_native_api_does_not_expose_the_webview_window_graph(self) -> None:
        native_api = launcher_module.NativeFileApi()
        self.assertNotIn("window", native_api.__dict__)
        self.assertIn("_window", native_api.__dict__)

    def test_studio_loader_keeps_preview_hidden_until_svg_is_ready(self) -> None:
        script = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
        markup = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="studioPreview" alt="作成中の印影プレビュー" hidden', markup)
        self.assertIn('runtime.platform === "win32" && runtime.frozen', script)
        self.assertIn("window.setTimeout(resolve, 32)", script)
        self.assertIn('<link rel="icon" href="data:,">', markup)
        self.assertIn("elements.studioPreview.hidden = false;\n    hideFontLoading();", script)
        self.assertNotIn("window.pywebview.api.get_font_catalog()", script)
        self.assertNotIn("window.pywebview.api.get_stamp_preview(studioPayload())", script)
        self.assertIn("await loadTemplates();\n  await loadRegisteredStamps();\n  await loadSettings();", script)
        self.assertNotIn("Promise.all([loadTemplates(), loadRegisteredStamps(), loadSettings()])", script)
