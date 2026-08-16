[CmdletBinding()]
param(
    [string]$EnvironmentFile,
    [switch]$NonInteractive,
    [switch]$SkipDocker
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$TemplatePath = Join-Path $ProjectRoot '.env.example'

if ([string]::IsNullOrWhiteSpace($EnvironmentFile)) {
    $EnvironmentFile = Join-Path $ProjectRoot '.env'
} elseif (-not [System.IO.Path]::IsPathRooted($EnvironmentFile)) {
    $EnvironmentFile = Join-Path (Get-Location) $EnvironmentFile
}

function Get-EnvValue {
    param([string]$Path, [string]$Name)

    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line.StartsWith("$Name=", [System.StringComparison]::Ordinal)) {
            return $line.Substring($Name.Length + 1)
        }
    }
    return $null
}

function Set-EnvValue {
    param([string]$Path, [string]$Name, [string]$Value)

    if ($Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Environment values cannot contain newlines."
    }

    $lines = [System.Collections.Generic.List[string]]::new()
    $found = $false
    foreach ($line in [System.IO.File]::ReadAllLines($Path)) {
        if ($line.StartsWith("$Name=", [System.StringComparison]::Ordinal)) {
            $lines.Add("$Name=$Value")
            $found = $true
        } else {
            $lines.Add($line)
        }
    }
    if (-not $found) {
        $lines.Add("$Name=$Value")
    }
    [System.IO.File]::WriteAllLines($Path, $lines, [System.Text.UTF8Encoding]::new($false))
}

function ConvertTo-EnvLiteral {
    param([string]$Value)

    if ($Value.Contains("`r") -or $Value.Contains("`n")) {
        throw "Environment values cannot contain newlines."
    }
    $escaped = $Value.Replace('\', '\\').Replace('"', '\"').Replace('$', '$$')
    return '"' + $escaped + '"'
}

function New-InternalSecret {
    $bytes = [byte[]]::new(48)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($bytes)
    return [Convert]::ToHexString($bytes).ToLowerInvariant()
}

function ConvertFrom-SecureInput {
    param([Security.SecureString]$Value)

    return [System.Net.NetworkCredential]::new('', $Value).Password
}

$environmentParent = Split-Path -Parent $EnvironmentFile
if (-not [string]::IsNullOrWhiteSpace($environmentParent)) {
    New-Item -ItemType Directory -Force -Path $environmentParent | Out-Null
}

if (-not (Test-Path -LiteralPath $EnvironmentFile)) {
    Copy-Item -LiteralPath $TemplatePath -Destination $EnvironmentFile
}

$appSecret = Get-EnvValue -Path $EnvironmentFile -Name 'APP_SECRET_KEY'
if ([string]::IsNullOrWhiteSpace($appSecret) -or $appSecret -eq 'CHANGE_ME') {
    Set-EnvValue -Path $EnvironmentFile -Name 'APP_SECRET_KEY' -Value (New-InternalSecret)
}

$postgresPassword = Get-EnvValue -Path $EnvironmentFile -Name 'POSTGRES_PASSWORD'
if ([string]::IsNullOrWhiteSpace($postgresPassword) -or $postgresPassword -eq 'CHANGE_ME') {
    $postgresPassword = New-InternalSecret
    Set-EnvValue -Path $EnvironmentFile -Name 'POSTGRES_PASSWORD' -Value $postgresPassword
}

$databaseUrl = Get-EnvValue -Path $EnvironmentFile -Name 'DATABASE_URL'
if ([string]::IsNullOrWhiteSpace($databaseUrl) -or $databaseUrl.Contains('CHANGE_ME')) {
    $databaseUrl = "postgresql+psycopg://invoice_auditor:$postgresPassword@postgres:5432/invoice_auditor"
    Set-EnvValue -Path $EnvironmentFile -Name 'DATABASE_URL' -Value $databaseUrl
}

$externalValues = @{
    IMAP_HOST = $env:INVOICE_AUDITOR_SETUP_IMAP_HOST
    IMAP_USER = $env:INVOICE_AUDITOR_SETUP_IMAP_USER
    IMAP_PASSWORD = $env:INVOICE_AUDITOR_SETUP_IMAP_PASSWORD
    OPENAI_API_KEY = $env:INVOICE_AUDITOR_SETUP_OPENAI_API_KEY
}

if (-not $NonInteractive) {
    if ([string]::IsNullOrWhiteSpace($externalValues.IMAP_HOST)) {
        $externalValues.IMAP_HOST = Read-Host 'IMAP host (leave blank to configure later)'
    }
    if ([string]::IsNullOrWhiteSpace($externalValues.IMAP_USER)) {
        $externalValues.IMAP_USER = Read-Host 'IMAP user/e-mail (leave blank to configure later)'
    }
    if ([string]::IsNullOrWhiteSpace($externalValues.IMAP_PASSWORD)) {
        $secureValue = Read-Host 'IMAP password (leave blank to configure later)' -AsSecureString
        $externalValues.IMAP_PASSWORD = ConvertFrom-SecureInput $secureValue
    }
    if ([string]::IsNullOrWhiteSpace($externalValues.OPENAI_API_KEY)) {
        $secureValue = Read-Host 'OpenAI API key (leave blank to configure later)' -AsSecureString
        $externalValues.OPENAI_API_KEY = ConvertFrom-SecureInput $secureValue
    }
}

foreach ($item in $externalValues.GetEnumerator()) {
    if (-not [string]::IsNullOrWhiteSpace($item.Value)) {
        Set-EnvValue -Path $EnvironmentFile -Name $item.Key -Value (ConvertTo-EnvLiteral $item.Value)
    }
}

foreach ($directory in 'tariffs', 'invoices', 'reports', 'temp', 'backups') {
    New-Item -ItemType Directory -Force -Path (Join-Path $ProjectRoot "data/$directory") | Out-Null
}

Write-Output "Configuration is ready at $EnvironmentFile. Internal secrets were generated or preserved."

if (-not $SkipDocker) {
    Push-Location $ProjectRoot
    try {
        docker version --format '{{.Server.Version}}' | Out-Null
        docker compose version | Out-Null
        docker compose up -d --build --wait --wait-timeout 120
    } finally {
        Pop-Location
    }
    Write-Output 'InvoiceAuditor services are running.'
}
