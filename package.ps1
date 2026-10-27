# Builds a release under a NEW version and assembles dist\Witcher3MissablesTracker-<version>\ and .zip.
# Every run bumps the version (default: patch, 0.1.2 -> 0.1.3) in Cargo.toml and tauri.conf.json.
# Older builds in dist\ are never touched; if the next version already exists, the next free one is used.
#   .\package.ps1                  # next patch version
#   .\package.ps1 -Bump minor      # 0.1.3 -> 0.2.0
#   .\package.ps1 -SourceUrl https://github.com/<you>/<repo>   # default: the git origin of this folder
# Local paths (your user profile and this folder) are remapped so they are not embedded in the exe.
param(
    [string]$SourceUrl,
    [ValidateSet('major', 'minor', 'patch')][string]$Bump = 'patch'
)

$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$utf8 = New-Object Text.UTF8Encoding $false

# the README links the source: the git origin of this folder unless one is given
if (-not $SourceUrl) {
    $prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'
    $origin = git remote get-url origin 2>$null
    $ErrorActionPreference = $prevEap
    if (-not $origin) { throw 'no git origin found: pass -SourceUrl https://github.com/<you>/<repo>' }
    $SourceUrl = ($origin.Trim()) -replace '\.git$', ''
}

# original text of every file this script edits, so a failed build can put them back
$cargoFile = Join-Path $PSScriptRoot 'Cargo.toml'
$tauriFile = Join-Path $PSScriptRoot 'tauri.conf.json'
$lockFile = Join-Path $PSScriptRoot 'Cargo.lock'
$originals = @{}
foreach ($f in $cargoFile, $tauriFile, $lockFile) { $originals[$f] = [IO.File]::ReadAllText($f) }

# next version that is not in dist\ yet
$cur = [regex]::Match($originals[$cargoFile], '(?m)^version = "(\d+)\.(\d+)\.(\d+)"')
if (-not $cur.Success) { throw 'package version not found in Cargo.toml' }
$ma = [int]$cur.Groups[1].Value; $mi = [int]$cur.Groups[2].Value; $pa = [int]$cur.Groups[3].Value
do {
    switch ($Bump) {
        'major' { $ma++; $mi = 0; $pa = 0 }
        'minor' { $mi++; $pa = 0 }
        default { $pa++ }
    }
    $version = "$ma.$mi.$pa"
    $name = "Witcher3MissablesTracker-$version"
} while ((Test-Path (Join-Path 'dist' $name)) -or (Test-Path (Join-Path 'dist' "$name.zip")))
Write-Host "new version: $version"

# write the version into the files (only the package's own version lines)
$newCargo = [regex]::Replace($originals[$cargoFile], '(?m)^version = "[^"]+"', ('version = "' + $version + '"'), 1)
$newTauri = [regex]::Replace($originals[$tauriFile], '"version": "[^"]+"', ('"version": "' + $version + '"'), 1)
[IO.File]::WriteAllText($cargoFile, $newCargo, $utf8)
[IO.File]::WriteAllText($tauriFile, $newTauri, $utf8)

# CARGO_ENCODED_RUSTFLAGS (separator 0x1f) copes with spaces in these paths
$env:RUSTFLAGS = $null
$env:CARGO_ENCODED_RUSTFLAGS = "--remap-path-prefix=$env:USERPROFILE=USER" + [char]0x1f + "--remap-path-prefix=$PSScriptRoot=SRC"
$prevEap = $ErrorActionPreference; $ErrorActionPreference = 'Continue'   # cargo prints progress on stderr
cargo build --release 2>&1 | ForEach-Object { "$_" }
$buildOk = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = $prevEap
if (-not $buildOk) {
    foreach ($f in $originals.Keys) { [IO.File]::WriteAllText($f, $originals[$f], $utf8) }
    throw 'build failed; version numbers were put back'
}
$targetDir = if ($env:CARGO_TARGET_DIR) { $env:CARGO_TARGET_DIR } else { Join-Path $PSScriptRoot 'target' }

$dist = Join-Path 'dist' $name
New-Item -ItemType Directory -Force (Join-Path $dist 'data') | Out-Null
Copy-Item (Join-Path $targetDir 'release\witcher3-missables-tracker.exe') (Join-Path $dist 'Witcher3MissablesTracker.exe')
foreach ($f in 'route.json', 'guide_alias.json', 'feed.json') { Copy-Item "data\$f" (Join-Path $dist 'data') }
Copy-Item data\audit_*.json, data\guide_*.json (Join-Path $dist 'data') -Force
foreach ($f in 'LICENSE', 'LICENSE-DATA.md', 'NOTICE.txt', 'THIRD-PARTY-LICENSES.txt') { Copy-Item $f $dist }
$readme = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'packaging\README.md')).Replace('{{VERSION}}', $version).Replace('{{SOURCE_URL}}', $SourceUrl)
[IO.File]::WriteAllText((Join-Path (Resolve-Path $dist) 'README.md'), $readme, $utf8)

$zip = "dist\$name.zip"
Compress-Archive -Path $dist -DestinationPath $zip
Write-Host "built $dist and $zip"
