param(
    [string]$Python = "python",
    [ValidatePattern('^\d+\.\d+\.\d+\.\d+$')]
    [string]$Version = "1.0.0.0",
    [string]$CertificatePath,
    [SecureString]$CertificatePassword,
    [switch]$SkipAppBuild
)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$DistRoot = Join-Path $ProjectRoot "dist"
$AppDistribution = Join-Path $DistRoot "Hanko PDF"
$StagingDirectory = Join-Path $ProjectRoot "build\msix\Hanko PDF"
$ValidationDirectory = Join-Path $ProjectRoot "build\msix-validation"
$OutputDirectory = Join-Path $DistRoot "msix"
$ManifestTemplate = Join-Path $PSScriptRoot "AppxManifest.xml.template"

function Get-WindowsSdkTool([string]$Name) {
    $kitsBin = "${env:ProgramFiles(x86)}\Windows Kits\10\bin"
    $candidates = @(
        Get-ChildItem -LiteralPath $kitsBin -Directory -ErrorAction SilentlyContinue |
            Where-Object { $_.Name -match '^\d+\.\d+\.\d+\.\d+$' } |
            Sort-Object { [Version]$_.Name } -Descending |
            ForEach-Object { Join-Path $_.FullName "x64\$Name" }
    )
    $tool = $candidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
    if (-not $tool) {
        throw "Windows SDK の $Name が見つかりません。Windows SDK の App Certification Kit をインストールしてください。"
    }
    return $tool
}

function New-StoreAsset([string]$Destination, [int]$Width, [int]$Height) {
    $script = @'
from pathlib import Path
import sys
from PIL import Image

source = Path(sys.argv[1])
destination = Path(sys.argv[2])
width = int(sys.argv[3])
height = int(sys.argv[4])
with Image.open(source) as original:
    image = original.convert("RGBA")
    image.thumbnail((width, height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    canvas.alpha_composite(image, ((width - image.width) // 2, (height - image.height) // 2))
    canvas.save(destination, format="PNG", optimize=True)
'@
    # Windows PowerShell 5.1 は -c に渡した文字列内の引用符を失うことがあるため、
    # Python コードは一時ファイルとして実行する。
    $scriptPath = Join-Path $ProjectRoot "build\msix-store-asset.py"
    Set-Content -LiteralPath $scriptPath -Value $script -Encoding UTF8
    & $Python $scriptPath (Join-Path $ProjectRoot "assets\hanko-icon.png") $Destination $Width $Height
    if ($LASTEXITCODE -ne 0) { throw "Store 用アイコンの生成に失敗しました: $Destination" }
}

if ([bool]$CertificatePath -ne [bool]$CertificatePassword) {
    throw "ローカル試験用の署名には -CertificatePath と -CertificatePassword を両方指定してください。Store提出用はどちらも指定しません。"
}

if (-not $SkipAppBuild) {
    & (Join-Path $ProjectRoot "packaging\windows\build.ps1") -Python $Python
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller ビルドに失敗しました。" }
}

if (-not (Test-Path -LiteralPath (Join-Path $AppDistribution "Hanko PDF.exe"))) {
    throw "PyInstaller の出力がありません: $AppDistribution"
}

$MakeAppx = Get-WindowsSdkTool "MakeAppx.exe"
$SignTool = if ($CertificatePath) { Get-WindowsSdkTool "SignTool.exe" }

Remove-Item -LiteralPath $StagingDirectory -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $StagingDirectory, $OutputDirectory -Force | Out-Null
Get-ChildItem -LiteralPath $AppDistribution -Force | Copy-Item -Destination $StagingDirectory -Recurse -Force

$assetsDirectory = Join-Path $StagingDirectory "Assets"
New-Item -ItemType Directory -Path $assetsDirectory -Force | Out-Null
New-StoreAsset (Join-Path $assetsDirectory "StoreLogo.png") 50 50
New-StoreAsset (Join-Path $assetsDirectory "Square44x44Logo.png") 44 44
New-StoreAsset (Join-Path $assetsDirectory "Square71x71Logo.png") 71 71
New-StoreAsset (Join-Path $assetsDirectory "Square150x150Logo.png") 150 150
New-StoreAsset (Join-Path $assetsDirectory "Square310x310Logo.png") 310 310
New-StoreAsset (Join-Path $assetsDirectory "Wide310x150Logo.png") 310 150

$manifest = (Get-Content -LiteralPath $ManifestTemplate -Raw).Replace("{{VERSION}}", $Version)
Set-Content -LiteralPath (Join-Path $StagingDirectory "AppxManifest.xml") -Value $manifest -Encoding utf8

$packageBaseName = "HankoPDF_$Version`_x64"
$msixPath = Join-Path $OutputDirectory "$packageBaseName.msix"
$uploadPath = Join-Path $OutputDirectory "$packageBaseName.msixupload"
Remove-Item -LiteralPath $msixPath, $uploadPath -Force -ErrorAction SilentlyContinue

$packOutput = & $MakeAppx pack /d $StagingDirectory /p $msixPath /o 2>&1
if ($LASTEXITCODE -ne 0) {
    $packOutput | Write-Host
    throw "MSIX パッケージ作成に失敗しました。"
}

# 古い SDK の MakeAppx には validate サブコマンドがないため、展開できることと
# manifest が含まれることを確認して、同等のパッケージ整合性検証を行う。
Remove-Item -LiteralPath $ValidationDirectory -Recurse -Force -ErrorAction SilentlyContinue
$unpackOutput = & $MakeAppx unpack /p $msixPath /d $ValidationDirectory /o 2>&1
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath (Join-Path $ValidationDirectory "AppxManifest.xml"))) {
    $unpackOutput | Write-Host
    throw "MSIX パッケージ検証に失敗しました。"
}

if ($CertificatePath) {
    if (-not (Test-Path -LiteralPath $CertificatePath)) {
        throw "証明書ファイルが見つかりません: $CertificatePath"
    }
    $password = [System.Net.NetworkCredential]::new("", $CertificatePassword).Password
    & $SignTool sign /fd SHA256 /f $CertificatePath /p $password $msixPath
    if ($LASTEXITCODE -ne 0) { throw "MSIX のローカル試験用署名に失敗しました。" }
}

$uploadZip = "$uploadPath.zip"
Remove-Item -LiteralPath $uploadZip -Force -ErrorAction SilentlyContinue
Compress-Archive -LiteralPath $msixPath -DestinationPath $uploadZip -CompressionLevel Optimal
Move-Item -LiteralPath $uploadZip -Destination $uploadPath -Force

Write-Host "MSIX: $msixPath"
Write-Host "Store upload: $uploadPath"
if ($CertificatePath) {
    Write-Host "ローカル試験用に署名しました。Storeへ提出する場合は、署名なしで再ビルドした .msixupload を使用してください。"
} else {
    Write-Host "Store提出用の未署名パッケージです。Microsoft Store が審査後に署名します。"
}
