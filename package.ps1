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
# route.json, derived.json and quest_graph.json are what the app reads; cutoffs.json,
# prereqs_review.json and route_disputes.json are the reviewed inputs behind them and ship as
# evidence. The wiki-era audit_*.json / guide_*.json stay in the checkout for comparison and are
# deliberately not packaged: the app never loads them.
# 1.0 reads the reviewed targets, the extracted branch graph, the card index, coverage and the
# exclusivity rows as well; a build without them would start with the 1.0 screen but none of its data.
foreach ($f in 'route.json', 'derived.json', 'quest_graph.json', 'cutoffs.json', 'cutoff_windows.json', 'route_disputes.json', 'prereqs_review.json', 'prereq_relations.json', 'endings.json', 'outcomes.json', 'branches.json', 'gwent_cards.json', 'card_windows.json', 'card_window_review.json', 'coverage.json', 'exclusive.json') {
    if (Test-Path "data\$f") { Copy-Item "data\$f" (Join-Path $dist 'data') } else { Write-Warning "missing data\$f" }
}
foreach ($f in 'LICENSE', 'LICENSE-DATA.md', 'NOTICE.txt', 'THIRD-PARTY-LICENSES.txt') { Copy-Item $f $dist }
$readme = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'packaging\README.md')).Replace('{{VERSION}}', $version).Replace('{{SOURCE_URL}}', $SourceUrl)
[IO.File]::WriteAllText((Join-Path (Resolve-Path $dist) 'README.md'), $readme, $utf8)

$zip = "dist\$name.zip"
Compress-Archive -Path $dist -DestinationPath $zip
Write-Host "built $dist and $zip"

# the one you actually run: it sits next to this folder's own data/ (the live copy the tools write),
# so the newest build is always a double-click here - dist/ stays the archive and the thing to hand out
Copy-Item (Join-Path $dist 'Witcher3MissablesTracker.exe') (Join-Path $PSScriptRoot 'Witcher3MissablesTracker.exe') -Force
Write-Host "updated $PSScriptRoot\Witcher3MissablesTracker.exe"
