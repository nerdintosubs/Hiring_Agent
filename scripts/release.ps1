param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectId,
  [string]$Region = "asia-south1",
  [string]$ServiceName = "hiring-agent-api",
  [ValidateSet("enabled", "disabled")]
  [string]$AuthMode = "enabled",
  [string]$ReleaseToken = ""
)

$ErrorActionPreference = "Stop"

$env:PROJECT_ID = $ProjectId
$env:REGION = $Region
$env:SERVICE_NAME = $ServiceName
$env:AUTH_MODE = $AuthMode
$env:RELEASE_TOKEN = $ReleaseToken

bash scripts/release.sh
