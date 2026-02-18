[CmdletBinding()]
param(
    [ValidateSet("bootstrap", "checkin", "status")]
    [string]$Mode = "status",
    [string]$ProjectId = "meetsync-ai",
    [string]$Region = "asia-south1",
    [string]$ServiceName = "hiring-agent-api",
    [string]$JwtSecretName = "hiring-agent-jwt-secret",
    [string]$RecruiterSubject = "recruiter-1",
    [string]$RecruiterJwt = "",
    [string]$CampaignId = "",
    [string]$EmployerName = "Pilot Spa Ops Cadence",
    [string[]]$NeighborhoodFocus = @("HSR", "BTM"),
    [string]$WhatsAppBusinessNumber = "+919187351205",
    [int]$TargetJoiners = 10,
    [bool]$FresherPreferred = $true,
    [string]$ShiftLabel = "",
    [int]$Leads = 0,
    [int]$Screened = 0,
    [int]$Trials = 0,
    [int]$Offers = 0,
    [int]$Joined = 0
)

$ErrorActionPreference = "Stop"

if (-not $env:CLOUDSDK_CONFIG) {
    $env:CLOUDSDK_CONFIG = "$PWD\.gcloud"
}

function Resolve-RecruiterToken {
    param(
        [string]$ProjectIdArg,
        [string]$JwtSecretNameArg,
        [string]$RecruiterSubjectArg,
        [string]$RecruiterJwtArg
    )
    if ($RecruiterJwtArg) {
        return $RecruiterJwtArg.Trim()
    }
    $jwtSecret = ((gcloud secrets versions access latest --secret=$JwtSecretNameArg --project=$ProjectIdArg) -join "").Trim()
    if (-not $jwtSecret) {
        throw "Failed to resolve JWT secret from Secret Manager."
    }
    $token = (python scripts/generate_jwt.py --secret $jwtSecret --subject $RecruiterSubjectArg --roles recruiter --hours 24).Trim()
    if (-not $token) {
        throw "Failed to generate recruiter JWT."
    }
    return $token
}

function Resolve-ApiUrl {
    param(
        [string]$ProjectIdArg,
        [string]$RegionArg,
        [string]$ServiceNameArg
    )
    $url = (gcloud run services describe $ServiceNameArg --region $RegionArg --project $ProjectIdArg --format="value(status.url)").Trim()
    if (-not $url) {
        throw "Failed to resolve Cloud Run URL for service '$ServiceNameArg'."
    }
    return $url
}

function Post-Json {
    param(
        [string]$Url,
        [hashtable]$Headers,
        [hashtable]$Payload
    )
    return Invoke-RestMethod -Method Post -Uri $Url -Headers $Headers -ContentType "application/json" -Body ($Payload | ConvertTo-Json -Compress)
}

$apiUrl = Resolve-ApiUrl -ProjectIdArg $ProjectId -RegionArg $Region -ServiceNameArg $ServiceName
$token = Resolve-RecruiterToken -ProjectIdArg $ProjectId -JwtSecretNameArg $JwtSecretName -RecruiterSubjectArg $RecruiterSubject -RecruiterJwtArg $RecruiterJwt
$headers = @{ Authorization = "Bearer $token" }

switch ($Mode) {
    "bootstrap" {
        $payload = @{
            employer_name = $EmployerName
            neighborhood_focus = $NeighborhoodFocus
            whatsapp_business_number = $WhatsAppBusinessNumber
            target_joiners = $TargetJoiners
            fresher_preferred = $FresherPreferred
        }
        $response = Post-Json -Url "$apiUrl/campaigns/first-10/bootstrap" -Headers $headers -Payload $payload
        Write-Output ("campaign_id=" + $response.campaign_id)
        Write-Output ("bootstrap=" + ($response | ConvertTo-Json -Compress))
    }
    "checkin" {
        if (-not $CampaignId) {
            throw "CampaignId is required for checkin mode."
        }
        $events = @()
        if ($Leads -gt 0) { $events += @{ event_type = "leads"; count = $Leads } }
        if ($Screened -gt 0) { $events += @{ event_type = "screened"; count = $Screened } }
        if ($Trials -gt 0) { $events += @{ event_type = "trials"; count = $Trials } }
        if ($Offers -gt 0) { $events += @{ event_type = "offers"; count = $Offers } }
        if ($Joined -gt 0) { $events += @{ event_type = "joined"; count = $Joined } }

        if ($events.Count -eq 0) {
            throw "Provide at least one non-zero count: Leads/Screened/Trials/Offers/Joined."
        }

        $today = Get-Date -Format "yyyy-MM-dd"
        $notePrefix = if ($ShiftLabel) { "$ShiftLabel $today" } else { "Shift check-in $today" }
        $latest = $null
        foreach ($event in $events) {
            $eventPayload = @{
                event_type = $event.event_type
                count = $event.count
                note = "$notePrefix - $($event.event_type)"
            }
            $latest = Post-Json -Url "$apiUrl/campaigns/$CampaignId/events" -Headers $headers -Payload $eventPayload
            Write-Output ("logged_$($event.event_type)=$($event.count)")
        }
        Write-Output ("progress=" + ($latest | ConvertTo-Json -Compress))
    }
    "status" {
        if (-not $CampaignId) {
            throw "CampaignId is required for status mode."
        }
        $response = Invoke-RestMethod -Method Get -Uri "$apiUrl/campaigns/$CampaignId/progress" -Headers $headers
        Write-Output ("progress=" + ($response | ConvertTo-Json -Compress))
    }
}
