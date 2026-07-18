param(
    [Parameter(Mandatory)]
    [SecureString]$Password,
    [string]$OutputDirectory = "build\msix-test-certificate"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..")).Path
$OutputDirectory = Join-Path $ProjectRoot $OutputDirectory
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

# Store の Package/Identity/Publisher と完全に一致する subject を使う。
$publisher = "CN=7927EB7F-72E2-4822-A979-3ADE223146BE"
$certificate = New-SelfSignedCertificate `
    -Type Custom `
    -Subject $publisher `
    -KeyUsage DigitalSignature `
    -KeyExportPolicy Exportable `
    -CertStoreLocation "Cert:\CurrentUser\My" `
    -TextExtension @("2.5.29.37={text}1.3.6.1.5.5.7.3.3") `
    -FriendlyName "Hanko PDF local MSIX test"

$pfxPath = Join-Path $OutputDirectory "HankoPDF-local-test.pfx"
$cerPath = Join-Path $OutputDirectory "HankoPDF-local-test.cer"
Export-PfxCertificate -Cert $certificate -FilePath $pfxPath -Password $Password | Out-Null
Export-Certificate -Cert $certificate -FilePath $cerPath | Out-Null

Write-Host "PFX: $pfxPath"
Write-Host "CER: $cerPath"
Write-Host "この CER をテスト端末の Cert:\CurrentUser\TrustedPeople へインポートしてから Add-AppxPackage を実行してください。"
