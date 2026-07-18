from __future__ import annotations

import unittest
from pathlib import Path
from xml.etree import ElementTree as ET


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
