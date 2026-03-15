# Sign-Release.ps1
# Downloads the latest release exe, signs it with Certum, and re-uploads it.
# Usage: .\sign-release.ps1 -App Vapor
#        .\sign-release.ps1 -App Vyber

param(
    [Parameter(Mandatory=$true)]
    [ValidateSet("Vapor", "Vyber")]
    [string]$App
)

$repo = "Master00Sniper/$App"
$exe = "$App.exe"
$tempDir = "$env:TEMP\sign-release"

# Clean up and create temp dir
if (Test-Path $tempDir) { Remove-Item $tempDir -Recurse -Force }
New-Item -ItemType Directory -Path $tempDir | Out-Null

Write-Host "`nSigning $App release..." -ForegroundColor Cyan

# Get latest release tag
Write-Host "Getting latest release..." -ForegroundColor Yellow
$tag = gh release view --repo $repo --json tagName -q .tagName
if (-not $tag) {
    Write-Host "ERROR: Could not find latest release for $repo" -ForegroundColor Red
    exit 1
}
Write-Host "Latest release: $tag" -ForegroundColor Green

# Download the exe
Write-Host "Downloading $exe..." -ForegroundColor Yellow
gh release download $tag --repo $repo --pattern $exe --dir $tempDir
if (-not (Test-Path "$tempDir\$exe")) {
    Write-Host "ERROR: Failed to download $exe" -ForegroundColor Red
    exit 1
}
Write-Host "Downloaded to $tempDir\$exe" -ForegroundColor Green

# Sign the exe
Write-Host "`nSigning $exe (you may be prompted for your card PIN)..." -ForegroundColor Yellow
signtool sign /a /tr http://time.certum.pl /td sha256 /fd sha256 "$tempDir\$exe"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Signing failed" -ForegroundColor Red
    exit 1
}
Write-Host "Signed successfully!" -ForegroundColor Green

# Verify signature
Write-Host "`nVerifying signature..." -ForegroundColor Yellow
signtool verify /pa "$tempDir\$exe"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Signature verification failed" -ForegroundColor Red
    exit 1
}
Write-Host "Signature verified!" -ForegroundColor Green

# Re-upload to release
Write-Host "`nUploading signed $exe to release $tag..." -ForegroundColor Yellow
gh release upload $tag "$tempDir\$exe" --repo $repo --clobber
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: Upload failed" -ForegroundColor Red
    exit 1
}
Write-Host "Uploaded signed $exe to $tag!" -ForegroundColor Green

# Cleanup
Remove-Item $tempDir -Recurse -Force

Write-Host "`nDone! $App $tag is now signed." -ForegroundColor Cyan
