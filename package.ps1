# Builds a release and assembles dist\Witcher3MissablesTracker-<version>.zip
#   .\package.ps1 -SourceUrl https://github.com/<you>/<repo>
# Local paths (your user profile and this folder) are remapped so they are not embedded in the exe.
param([string]$SourceUrl = 'the source link on the download page')

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$version = ((Get-Content Cargo.toml -Raw) | Select-String 'version = "([^"]+)"').Matches[0].Groups[1].Value
$name = "Witcher3MissablesTracker-$version"

# CARGO_ENCODED_RUSTFLAGS (separator 0x1f) copes with spaces in these paths
$env:RUSTFLAGS = $null
$env:CARGO_ENCODED_RUSTFLAGS = "--remap-path-prefix=$env:USERPROFILE=USER" + [char]0x1f + "--remap-path-prefix=$PSScriptRoot=SRC"
$ErrorActionPreference = 'Continue'   # cargo prints progress on stderr
cargo build --release 2>&1 | ForEach-Object { "$_" }
if ($LASTEXITCODE -ne 0) { throw 'build failed' }
$ErrorActionPreference = 'Stop'
$targetDir = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path $PSScriptRoot 'target' }

$dist = Join-Path 'dist' $name
if (Test-Path $dist) { Get-ChildItem $dist -Recurse | Remove-Item -Recurse -Force }
New-Item -ItemType Directory -Force (Join-Path $dist 'data') | Out-Null
Copy-Item (Join-Path $targetDir 'release\witcher3-missables-tracker.exe') (Join-Path $dist 'Witcher3MissablesTracker.exe')
foreach ($f in 'route.json', 'guide_alias.json') { Copy-Item "data\$f" (Join-Path $dist 'data') }
Copy-Item data\audit_*.json, data\guide_*.json (Join-Path $dist 'data') -Force
foreach ($f in 'LICENSE', 'LICENSE-DATA.md', 'NOTICE.txt', 'THIRD-PARTY-LICENSES.txt') { Copy-Item $f $dist }
$readme = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'packaging\README.md')).Replace('{{VERSION}}', $version).Replace('{{SOURCE_URL}}', $SourceUrl)
[IO.File]::WriteAllText((Join-Path (Resolve-Path $dist) 'README.md'), $readme, (New-Object Text.UTF8Encoding $false))

$zip = "dist\$name.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path $dist -DestinationPath $zip
Write-Host "built $zip"
