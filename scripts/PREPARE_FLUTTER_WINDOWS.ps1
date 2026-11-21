# Requires Flutter SDK in PATH. Run this PowerShell file from VS Code.
$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $root
flutter doctor
if (-not (Test-Path "homecue_flutter_app")) {
  flutter create --platforms=android homecue_flutter_app
}
Copy-Item -Force (Join-Path $root "mobile_flutter\lib\main.dart") (Join-Path $root "homecue_flutter_app\lib\main.dart")
Copy-Item -Force (Join-Path $root "mobile_flutter\pubspec.yaml") (Join-Path $root "homecue_flutter_app\pubspec.yaml")
Set-Location (Join-Path $root "homecue_flutter_app")
flutter pub get
Write-Host "Next steps: add Android internet + debug cleartext manifest permissions (see mobile_flutter/README.md), then flutter run." -ForegroundColor Green
