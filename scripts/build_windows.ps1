$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not $env:SSL_CERT_FILE) {
    $Candidates = @(
        "C:\Program Files\Common Files\SSL\cert.pem",
        "C:\Program Files\Git\mingw64\ssl\certs\ca-bundle.crt"
    )
    foreach ($Candidate in $Candidates) {
        if (Test-Path $Candidate) {
            $env:SSL_CERT_FILE = $Candidate
            break
        }
    }
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 -m venv .venv-build
} else {
    python -m venv .venv-build
}

$Python = Join-Path $Root ".venv-build\Scripts\python.exe"
& $Python -m pip install --upgrade pip
& $Python -m pip install pyinstaller
& $Python -m PyInstaller --clean --noconfirm LogVault.spec

Write-Host "Built: $Root\dist\LogVault.exe"

$Inno = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (Test-Path $Inno) {
    $Version = & $Python -c "import tomllib; print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])"
    & $Inno "/DAppVersion=$Version" "packaging\windows\LogVault.iss"
    Write-Host "Built installer: $Root\installer\LogVault-Setup-$Version-x64.exe"
} else {
    Write-Host "Inno Setup not found; skipped installer build."
}
