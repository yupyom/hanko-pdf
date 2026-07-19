param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

Push-Location $ProjectRoot
try {
    # ICO は Windows 実行ファイルの埋め込み用。PNG の元アセットから常に再生成する。
    $script = @'
from pathlib import Path
from PIL import Image

root = Path.cwd()
source = root / "assets" / "hanko-icon.png"
destination = root / "assets" / "hanko-icon.ico"
with Image.open(source) as image:
    image.save(destination, format="ICO", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
'@
    # Windows PowerShell 5.1 は -c に渡した文字列内の引用符を失うことがあるため、
    # Python コードは一時ファイルとして実行する。
    $scriptPath = Join-Path $ProjectRoot "build\windows-icon-generator.py"
    Set-Content -LiteralPath $scriptPath -Value $script -Encoding UTF8
    & $Python $scriptPath
    if ($LASTEXITCODE -ne 0) { throw "Windows 用 ICO の生成に失敗しました。" }
    & $Python -m PyInstaller --noconfirm --clean "packaging\windows\Hanko PDF.spec"
    if ($LASTEXITCODE -ne 0) { throw "Windows one-folder ビルドに失敗しました。" }
}
finally {
    Pop-Location
}
