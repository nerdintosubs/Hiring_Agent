# Hiring Agent Runbook (Bangalore Pilot)

## 1) Prerequisites (once per machine)
```powershell
$env:CLOUDSDK_CONFIG="$PWD\.gcloud"
gcloud auth login
gcloud config set project meetsync-ai
```

## 2) Set runtime variables (each session)
```powershell
$env:PROJECT_ID="meetsync-ai"
$env:REGION="asia-south1"
$env:WA_NUMBER="+919187351205"
$env:API_URL=(gcloud run services describe hiring-agent-api --region $env:REGION --project $env:PROJECT_ID --format='value(status.url)').Trim()
$env:JWT_SECRET=((gcloud secrets versions access latest --secret=hiring-agent-jwt-secret --project=$env:PROJECT_ID) -join '').Trim()
$env:RECRUITER_JWT=(python scripts/generate_jwt.py --secret $env:JWT_SECRET --subject recruiter-1 --roles recruiter --hours 24).Trim()
```

## 3) Health checks
```powershell
curl.exe -sS "$env:API_URL/health"
curl.exe -sS "$env:API_URL/health/ready"
curl.exe -sS "$env:API_URL/metrics" | Select-Object -First 10
```

## 4) Day-1 operations

### Create employer intake
```powershell
$body='{"employer_name":"Pilot Spa","contact_phone":"9999988888","role":"Spa Therapist","required_therapies":["swedish"],"shift_start":"10:00","shift_end":"19:00","pay_min":22000,"pay_max":30000,"location_name":"HSR","location":{"lat":12.91,"lon":77.64},"languages":["kn","en"],"urgency_hours":48}'
curl.exe -sS -X POST "$env:API_URL/employers/intake" -H "Authorization: Bearer $env:RECRUITER_JWT" -H "Content-Type: application/json" -d $body
```

### Add manual lead (walk-in/referral/call)
```powershell
$body='{"source_channel":"walk_in","name":"Ananya","phone":"9000012345","languages":["kn","en"],"notes":"pilot day-1 walk-in","created_by":"recruiter-1"}'
curl.exe -sS -X POST "$env:API_URL/leads/manual" -H "Authorization: Bearer $env:RECRUITER_JWT" -H "Content-Type: application/json" -d $body
```

### Bootstrap first-10 campaign
```powershell
$body="{\"employer_name\":\"Pilot Spa\",\"neighborhood_focus\":[\"HSR\",\"BTM\"],\"whatsapp_business_number\":\"$env:WA_NUMBER\",\"target_joiners\":10,\"fresher_preferred\":true}"
curl.exe -sS -X POST "$env:API_URL/campaigns/first-10/bootstrap" -H "Authorization: Bearer $env:RECRUITER_JWT" -H "Content-Type: application/json" -d $body
```

## 5) Pipeline tracking
```powershell
curl.exe -sS -H "Authorization: Bearer $env:RECRUITER_JWT" "$env:API_URL/leads/manual?limit=20"
```

## 6) Daily shift check-in (repeatable)
```powershell
# Bootstrap a new first-10 campaign
.\scripts\pilot_shift_checkin.ps1 -Mode bootstrap

# Log shift metrics
.\scripts\pilot_shift_checkin.ps1 -Mode checkin -CampaignId <campaign_id> -ShiftLabel "Shift-1" -Leads 15 -Screened 7
.\scripts\pilot_shift_checkin.ps1 -Mode checkin -CampaignId <campaign_id> -ShiftLabel "Shift-2" -Trials 3 -Offers 2 -Joined 1

# Read latest campaign status
.\scripts\pilot_shift_checkin.ps1 -Mode status -CampaignId <campaign_id>

# Send status update to WhatsApp (fallback link if no provider creds)
.\scripts\pilot_shift_checkin.ps1 -Mode status -CampaignId <campaign_id> -SendWhatsApp -UpdateTo "+919187351205"

# Direct send via Meta Cloud API
$env:WHATSAPP_PHONE_NUMBER_ID="<meta-phone-number-id>"
$env:WHATSAPP_ACCESS_TOKEN="<meta-access-token>"
.\scripts\pilot_shift_checkin.ps1 -Mode status -CampaignId <campaign_id> -SendWhatsApp -UpdateTo "+919187351205"
```

## 7) Common failures
- `401 Unauthorized`: regenerate JWT from latest `hiring-agent-jwt-secret`.
- `500` on startup: confirm Cloud Run has Cloud SQL attachment and latest `hiring-agent-database-url`.
- No new leads: verify recruiter used valid `source_channel` and unique phone.
