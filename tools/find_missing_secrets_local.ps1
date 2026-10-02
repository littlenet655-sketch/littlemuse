param(
    [string]$OutputDir = "$env:USERPROFILE\LittleNet-New-Modal-Secrets"
)

$ErrorActionPreference = "Stop"

$Wanted = @(
    "R2_ACCOUNT_ID",
    "R2_ACCESS_KEY_ID",
    "R2_SECRET_ACCESS_KEY",
    "R2_BUCKET",
    "QSTASH_TOKEN",
    "QSTASH_CURRENT_SIGNING_KEY",
    "QSTASH_NEXT_SIGNING_KEY",
    "RESEND_API_KEY",
    "SMTP_USER",
    "SMTP_PASSWORD"
)

$Found = @{}
$Sources = @{}

function Add-FoundValue {
    param(
        [string]$Key,
        [string]$Value,
        [string]$Source
    )
    if (-not $Key -or -not $Value) { return }
    if ($Wanted -notcontains $Key) { return }
    if ($Found.ContainsKey($Key)) { return }

    $trimmed = $Value.Trim()
    if ($trimmed.Length -ge 2) {
        $first = $trimmed.Substring(0, 1)
        $last = $trimmed.Substring($trimmed.Length - 1, 1)
        if (($first -eq '"' -and $last -eq '"') -or ($first -eq "'" -and $last -eq "'")) {
            $trimmed = $trimmed.Substring(1, $trimmed.Length - 2)
        }
    }

    $trimmed = $trimmed.Trim()
    if ([string]::IsNullOrWhiteSpace($trimmed)) { return }
    if ($trimmed -match '^(PASTE_|replace-|changeme|your_|<|\$\{|\*\*\*)') { return }

    $Found[$Key] = $trimmed
    $Sources[$Key] = $Source
}

function Inspect-Line {
    param(
        [string]$Line,
        [string]$Source
    )

    if ($null -eq $Line) { return }
    $text = $Line.TrimStart([char]0xFEFF).Trim()
    if (-not $text -or $text.StartsWith('#') -or $text.StartsWith('//')) { return }

    # PowerShell: $env:KEY = value
    if ($text.StartsWith('$env:', [System.StringComparison]::OrdinalIgnoreCase)) {
        $body = $text.Substring(5)
        $eq = $body.IndexOf('=')
        if ($eq -gt 0) {
            $key = $body.Substring(0, $eq).Trim()
            $value = $body.Substring($eq + 1).Trim()
            Add-FoundValue $key $value $Source
        }
        return
    }

    # cmd.exe: set KEY=value
    if ($text.StartsWith('set ', [System.StringComparison]::OrdinalIgnoreCase)) {
        $text = $text.Substring(4).Trim()
    }

    # dotenv / shell / config: KEY=value
    $eqPos = $text.IndexOf('=')
    if ($eqPos -gt 0) {
        $key = $text.Substring(0, $eqPos).Trim().Trim('"').Trim("'")
        $value = $text.Substring($eqPos + 1).Trim()
        Add-FoundValue $key $value $Source
        return
    }

    # JSON/TOML/YAML-ish single-line forms: "KEY": "value" or KEY: value
    $colonPos = $text.IndexOf(':')
    if ($colonPos -gt 0) {
        $key = $text.Substring(0, $colonPos).Trim().Trim('"').Trim("'")
        $value = $text.Substring($colonPos + 1).Trim().TrimEnd(',')
        Add-FoundValue $key $value $Source
    }
}

Write-Host "LittleNet targeted local secret search" -ForegroundColor Cyan
Write-Host "Secret VALUES will NOT be printed." -ForegroundColor Yellow

# 1) Process/User/Machine environment variables
foreach ($key in $Wanted) {
    foreach ($scope in @('Process','User','Machine')) {
        try {
            $val = [Environment]::GetEnvironmentVariable($key, $scope)
            if ($val) { Add-FoundValue $key $val "environment:$scope" }
        } catch {}
    }
}

# 2) Bounded search of likely LittleNet/config locations.
$roots = @(
    "D:\aitprojects",
    "$env:USERPROFILE\Documents",
    "$env:USERPROFILE\Desktop",
    "$env:USERPROFILE\Downloads",
    "$env:USERPROFILE\.config",
    "$env:USERPROFILE\.cloudflared",
    "$env:USERPROFILE\.wrangler",
    "$env:APPDATA\Microsoft\Windows\PowerShell\PSReadLine",
    "$env:APPDATA\Microsoft\PowerShell\PSReadLine"
) | Where-Object { $_ -and (Test-Path $_) }

$includeNames = @(
    '.env','.env.local','.env.production','.env.development','.env.backup',
    'wrangler.toml','wrangler.json','wrangler.jsonc','config.toml','config.json',
    'settings.json','secrets.env','recovered.env','web.env','r2.env','email.env',
    'PowerShell_history.txt','ConsoleHost_history.txt'
)

$extensions = @('.env','.txt','.json','.jsonc','.toml','.yaml','.yml','.ini','.cfg','.conf','.ps1','.cmd','.bat')
$skipParts = @('node_modules','.git','dist','build','.expo','.gradle','venv','.venv','__pycache__','Temp','Cache','Code Cache','GPUCache')

function Should-SkipPath {
    param([string]$Path)
    foreach ($part in $skipParts) {
        $needle = "\$part\"
        if ($Path.IndexOf($needle, [System.StringComparison]::OrdinalIgnoreCase) -ge 0) { return $true }
    }
    return $false
}

$files = New-Object System.Collections.Generic.List[string]
foreach ($root in $roots) {
    try {
        Get-ChildItem -LiteralPath $root -File -Recurse -Force -ErrorAction SilentlyContinue |
            Where-Object {
                -not (Should-SkipPath $_.FullName) -and
                ($includeNames -contains $_.Name -or $extensions -contains $_.Extension.ToLowerInvariant()) -and
                $_.Length -lt 5MB
            } |
            Select-Object -First 20000 |
            ForEach-Object { $files.Add($_.FullName) }
    } catch {}
}

foreach ($file in ($files | Select-Object -Unique)) {
    if ($Found.Count -eq $Wanted.Count) { break }
    try {
        foreach ($line in [IO.File]::ReadLines($file)) {
            Inspect-Line $line $file
            if ($Found.Count -eq $Wanted.Count) { break }
        }
    } catch {}
}

New-Item -ItemType Directory -Force $OutputDir | Out-Null
$outFile = Join-Path $OutputDir 'recovered.env'
$lines = @()
foreach ($key in $Wanted) {
    if ($Found.ContainsKey($key)) {
        # JSON string syntax is accepted by dotenv readers and safely quotes special characters.
        $jsonValue = ConvertTo-Json ([string]$Found[$key]) -Compress
        $lines += ($key + '=' + $jsonValue)
    }
}
[System.IO.File]::WriteAllLines($outFile, $lines, [System.Text.UTF8Encoding]::new($false))

Write-Host "`nRecovered key names:" -ForegroundColor Green
if ($Found.Count -eq 0) {
    Write-Host "  (none)"
} else {
    foreach ($key in $Wanted) {
        if ($Found.ContainsKey($key)) {
            Write-Host "  + $key" -ForegroundColor Green
            Write-Host "    source: $($Sources[$key])" -ForegroundColor DarkGray
        }
    }
}

$missing = @($Wanted | Where-Object { -not $Found.ContainsKey($_) })
Write-Host "`nStill missing key names:" -ForegroundColor Yellow
if ($missing.Count -eq 0) {
    Write-Host "  (none)" -ForegroundColor Green
} else {
    foreach ($key in $missing) { Write-Host "  - $key" -ForegroundColor Yellow }
}

Write-Host "`nRecovered values were written to:" -ForegroundColor Cyan
Write-Host "  $outFile" -ForegroundColor Cyan
Write-Host "Do not upload, commit, or paste that file." -ForegroundColor Yellow

$requiredCore = @(
    'R2_ACCOUNT_ID','R2_ACCESS_KEY_ID','R2_SECRET_ACCESS_KEY','R2_BUCKET',
    'QSTASH_TOKEN','QSTASH_CURRENT_SIGNING_KEY','QSTASH_NEXT_SIGNING_KEY'
)
$coreMissing = @($requiredCore | Where-Object { -not $Found.ContainsKey($_) })
$mailOk = $Found.ContainsKey('RESEND_API_KEY') -or ($Found.ContainsKey('SMTP_USER') -and $Found.ContainsKey('SMTP_PASSWORD'))
if ($coreMissing.Count -eq 0 -and $mailOk) {
    Write-Host "`nSEARCH_READY=True" -ForegroundColor Green
    exit 0
}

Write-Host "`nSEARCH_READY=False" -ForegroundColor Yellow
exit 2
