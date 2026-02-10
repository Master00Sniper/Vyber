# Nuitka Build Script for Vyber
# This compiles Vyber to a native Windows executable
# Run with: .\build_nuitka.ps1

Write-Host "==========================================" -ForegroundColor Cyan
Write-Host "Vyber Nuitka Build Script" -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

# Extract version from vyber/__init__.py (single source of truth)
Write-Host "Extracting version from vyber/__init__.py..."
$versionLine = Select-String -Path "vyber\__init__.py" -Pattern '__version__ = "([^"]+)"'
if ($versionLine) {
    $VERSION = $versionLine.Matches[0].Groups[1].Value
    Write-Host "Detected version: $VERSION" -ForegroundColor Green
} else {
    Write-Host "ERROR: Could not extract version from vyber/__init__.py" -ForegroundColor Red
    exit 1
}

# Metadata
$COMPANY = "Morton Apps"
$PRODUCT = "Vyber"
$COPYRIGHT = "Copyright (c) 2026 Greg Morton. All rights reserved."

Write-Host ""

# Check if Nuitka is installed
Write-Host "Checking for Nuitka..."
$nuitkaCheck = python -m nuitka --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "Nuitka not found. Installing..." -ForegroundColor Yellow
    pip install nuitka ordered-set zstandard
    Write-Host ""
}

Write-Host "Starting Nuitka compilation..." -ForegroundColor Cyan
Write-Host "This will take 10-30 minutes on first build."
Write-Host ""

# Build the Nuitka command
$nuitkaArgs = @(
    "-m", "nuitka",
    "--standalone",
    "--onefile",
    "--assume-yes-for-downloads",
    "--msvc=latest",
    "--windows-console-mode=disable",
    "--windows-icon-from-ico=images/vyber.ico",
    "--output-filename=Vyber.exe",
    "--output-dir=dist",
    "--company-name=$COMPANY",
    "--product-name=$PRODUCT",
    "--file-version=$VERSION",
    "--product-version=$VERSION",
    "--file-description=Vyber - Soundboard with Virtual Mic Routing",
    "--copyright=$COPYRIGHT",
    "--enable-plugin=tk-inter",
    "--include-data-dir=images=images",
    "--include-data-dir=sounds=sounds",
    "--include-module=vyber",
    "--include-module=vyber.app",
    "--include-module=vyber.audio_engine",
    "--include-module=vyber.config",
    "--include-module=vyber.hotkey_manager",
    "--include-module=vyber.sound_manager",
    "--include-module=vyber.virtual_cable",
    "--include-module=vyber.vb_cable_installer",
    "--include-module=vyber.tray_manager",
    "--include-module=vyber.ui",
    "--include-module=vyber.ui.main_window",
    "--include-module=vyber.ui.settings_dialog",
    "--include-module=vyber.ui.sound_grid",
    "--include-module=vyber.ui.widgets",
    "--include-module=customtkinter",
    "--include-package-data=customtkinter",
    "--include-module=PIL",
    "--include-module=PIL.Image",
    "--include-module=PIL.ImageTk",
    "--include-module=sounddevice",
    "--include-module=soundfile",
    "--include-module=numpy",
    "--include-module=keyboard",
    "--include-module=pystray",
    "--include-module=pydub",
    "run.py"
)

# Run Nuitka
& python $nuitkaArgs

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "BUILD FAILED" -ForegroundColor Red
    Write-Host "==========================================" -ForegroundColor Red
    Write-Host "Check the error messages above."
    exit 1
}

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "BUILD SUCCESSFUL" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host "Output: dist\Vyber.exe"
Write-Host "Version: $VERSION"
Write-Host ""
