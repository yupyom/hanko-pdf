param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

Push-Location $ProjectRoot
try {
    # ICO は Windows 実行ファイルの埋め込み用。PNG の元アセットから常に再生成する。
    & $Python -c @'
from pathlib import Path
from PIL import Image

root = Path.cwd()
source = root / "assets" / "hanko-icon.png"
destination = root / "assets" / "hanko-icon.ico"
with Image.open(source) as image:
    image.save(destination, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
'@
    & $Python -m PyInstaller --noconfirm --clean "packaging\windows\Hanko PDF.spec"
}
finally {
    Pop-Location
}
