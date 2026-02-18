const API_BASE = window.HIRING_AGENT_API_BASE || "http://127.0.0.1:8000";

const healthButton = document.getElementById("health-check");
const healthResult = document.getElementById("health-result");
const pipelineButton = document.getElementById("fetch-pipeline");
const pipelineOutput = document.getElementById("pipeline-output");
const jobIdInput = document.getElementById("job-id");
const employerNameInput = document.getElementById("employer-name");
const neighborhoodFocusInput = document.getElementById("neighborhood-focus");
const whatsappNumberInput = document.getElementById("whatsapp-number");
const targetJoinersInput = document.getElementById("target-joiners");
const bootstrapCampaignButton = document.getElementById("bootstrap-campaign");
const campaignBootstrapResult = document.getElementById("campaign-bootstrap-result");
const campaignIdInput = document.getElementById("campaign-id");
const eventTypeInput = document.getElementById("event-type");
const eventCountInput = document.getElementById("event-count");
const logEventButton = document.getElementById("log-event");
const fetchCampaignProgressButton = document.getElementById("fetch-campaign-progress");
const campaignKpis = document.getElementById("campaign-kpis");
const campaignActions = document.getElementById("campaign-actions");
const campaignOutput = document.getElementById("campaign-output");
const leadNameInput = document.getElementById("lead-name");
const leadPhoneInput = document.getElementById("lead-phone");
const leadSourceInput = document.getElementById("lead-source");
const leadLanguagesInput = document.getElementById("lead-languages");
const leadJobIdInput = document.getElementById("lead-job-id");
const leadNeighborhoodInput = document.getElementById("lead-neighborhood");
const leadCreatedByInput = document.getElementById("lead-created-by");
const leadNotesInput = document.getElementById("lead-notes");
const createManualLeadButton = document.getElementById("create-manual-lead");
const refreshManualLeadsButton = document.getElementById("refresh-manual-leads");
const manualLeadStatus = document.getElementById("manual-lead-status");
const manualLeadsBody = document.getElementById("manual-leads-body");
const manualLeadOutput = document.getElementById("manual-lead-output");
const leadFilterSourceInput = document.getElementById("lead-filter-source");
const leadFilterNeighborhoodInput = document.getElementById("lead-filter-neighborhood");
const leadFilterCreatedByInput = document.getElementById("lead-filter-created-by");
const leadFilterDateFromInput = document.getElementById("lead-filter-date-from");
const leadFilterDateToInput = document.getElementById("lead-filter-date-to");
const leadFilterSearchInput = document.getElementById("lead-filter-search");
const applyManualLeadFiltersButton = document.getElementById("apply-manual-lead-filters");

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) {
    const detail = data.detail || JSON.stringify(data);
    throw new Error(detail);
  }
  return data;
}

function clearCampaignView() {
  campaignKpis.innerHTML = "";
  campaignActions.innerHTML = "";
}

function renderCampaignProgress(data) {
  if (!data || !data.conversion_rates || !data.counts) {
    clearCampaignView();
    return;
  }
  const kpiItems = [
    ["Health Status", data.health_status],
    ["Joined", `${data.counts.joined || 0} / ${data.target_joiners || 0}`],
    ["Lead -> Screened", `${data.conversion_rates.lead_to_screened || 0}%`],
    ["Screened -> Trial", `${data.conversion_rates.screened_to_trial || 0}%`],
    ["Trial -> Offer", `${data.conversion_rates.trial_to_offer || 0}%`],
    ["Offer -> Joined", `${data.conversion_rates.offer_to_joined || 0}%`]
  ];

  campaignKpis.innerHTML = kpiItems
    .map(
      ([label, value]) =>
        `<div class="kpi-card"><span class="kpi-label">${label}</span><span class="kpi-value">${value}</span></div>`
    )
    .join("");

  const actions = Array.isArray(data.recommended_actions)
    ? data.recommended_actions
    : [];
  campaignActions.innerHTML = actions
    .map((action) => `<li>${action}</li>`)
    .join("");
}

function parseCsvValues(raw) {
  return raw
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
}

function formatDate(iso) {
  if (!iso) {
    return "-";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString();
}

function renderManualLeads(leads) {
  if (!Array.isArray(leads) || leads.length === 0) {
    manualLeadsBody.innerHTML = `
      <tr><td colspan="7">No leads yet. Create one using the form above.</td></tr>
    `;
    return;
  }
  manualLeadsBody.innerHTML = leads
    .map(
      (lead) => `
      <tr>
        <td>${formatDate(lead.created_at_utc)}</td>
        <td>${lead.name || "-"}</td>
        <td>${lead.phone || "-"}</td>
        <td>${lead.source_channel || "-"}</td>
        <td>${lead.lead_id || "-"}</td>
        <td>${lead.candidate_id || "-"}</td>
        <td>${lead.job_id || "-"}</td>
      </tr>
    `
    )
    .join("");
}

async function refreshManualLeads(limit = 50) {
  const params = new URLSearchParams({ limit: String(limit) });
  const source = leadFilterSourceInput.value.trim();
  const neighborhood = leadFilterNeighborhoodInput.value.trim();
  const createdBy = leadFilterCreatedByInput.value.trim();
  const dateFrom = leadFilterDateFromInput.value.trim();
  const dateTo = leadFilterDateToInput.value.trim();
  const search = leadFilterSearchInput.value.trim();
  if (source) {
    params.set("source_channel", source);
  }
  if (neighborhood) {
    params.set("neighborhood", neighborhood);
  }
  if (createdBy) {
    params.set("created_by", createdBy);
  }
  if (dateFrom) {
    params.set("created_from", dateFrom);
  }
  if (dateTo) {
    params.set("created_to", dateTo);
  }
  if (search) {
    params.set("search", search);
  }
  const data = await fetchJson(`${API_BASE}/leads/manual?${params.toString()}`);
  renderManualLeads(data);
  return data;
}

healthButton.addEventListener("click", async () => {
  healthResult.textContent = "Checking...";
  try {
    const data = await fetchJson(`${API_BASE}/health`);
    healthResult.textContent = `Status: ${data.status}`;
  } catch (error) {
    healthResult.textContent = `Error: ${error.message}`;
  }
});

pipelineButton.addEventListener("click", async () => {
  const jobId = jobIdInput.value.trim();
  if (!jobId) {
    pipelineOutput.textContent = "Enter a job id.";
    return;
  }
  pipelineOutput.textContent = "Loading...";
  try {
    const data = await fetchJson(`${API_BASE}/jobs/${jobId}/pipeline`);
    pipelineOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    pipelineOutput.textContent = `Error: ${error.message}`;
  }
});

bootstrapCampaignButton.addEventListener("click", async () => {
  const employerName = employerNameInput.value.trim();
  if (!employerName) {
    campaignBootstrapResult.textContent = "Employer name is required.";
    return;
  }
  const neighborhoods = neighborhoodFocusInput.value
    .split(",")
    .map((value) => value.trim())
    .filter((value) => value.length > 0);
  const targetJoiners = parseInt(targetJoinersInput.value, 10);

  campaignBootstrapResult.textContent = "Creating campaign...";
  clearCampaignView();
  try {
    const data = await fetchJson(`${API_BASE}/campaigns/first-10/bootstrap`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        employer_name: employerName,
        neighborhood_focus: neighborhoods,
        whatsapp_business_number: whatsappNumberInput.value.trim(),
        target_joiners: Number.isNaN(targetJoiners) ? 10 : targetJoiners,
        fresher_preferred: true
      })
    });
    campaignIdInput.value = data.campaign_id;
    campaignBootstrapResult.textContent = `Campaign created: ${data.campaign_id}`;
    campaignOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    campaignBootstrapResult.textContent = `Error: ${error.message}`;
  }
});

logEventButton.addEventListener("click", async () => {
  const campaignId = campaignIdInput.value.trim();
  if (!campaignId) {
    campaignOutput.textContent = "Enter or bootstrap a campaign id first.";
    return;
  }
  campaignOutput.textContent = "Logging event...";
  try {
    const data = await fetchJson(`${API_BASE}/campaigns/${campaignId}/events`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type: eventTypeInput.value,
        count: parseInt(eventCountInput.value, 10) || 1
      })
    });
    renderCampaignProgress(data);
    campaignOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    campaignOutput.textContent = `Error: ${error.message}`;
  }
});

fetchCampaignProgressButton.addEventListener("click", async () => {
  const campaignId = campaignIdInput.value.trim();
  if (!campaignId) {
    campaignOutput.textContent = "Enter a campaign id first.";
    return;
  }
  campaignOutput.textContent = "Loading progress...";
  try {
    const data = await fetchJson(`${API_BASE}/campaigns/${campaignId}/progress`);
    renderCampaignProgress(data);
    campaignOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    campaignOutput.textContent = `Error: ${error.message}`;
  }
});

createManualLeadButton.addEventListener("click", async () => {
  const name = leadNameInput.value.trim();
  const phone = leadPhoneInput.value.trim();
  if (!name || !phone) {
    manualLeadStatus.textContent = "Name and phone are required.";
    return;
  }
  manualLeadStatus.textContent = "Creating lead...";
  try {
    const payload = {
      source_channel: leadSourceInput.value,
      name,
      phone,
      languages: parseCsvValues(leadLanguagesInput.value),
      neighborhood: leadNeighborhoodInput.value.trim() || null,
      notes: leadNotesInput.value.trim() || null,
      created_by: leadCreatedByInput.value.trim() || null,
      job_id: leadJobIdInput.value.trim() || null
    };
    const result = await fetchJson(`${API_BASE}/leads/manual`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    manualLeadStatus.textContent = `Lead created: ${result.lead_id}`;
    manualLeadOutput.textContent = JSON.stringify(result, null, 2);
    await refreshManualLeads(50);
  } catch (error) {
    manualLeadStatus.textContent = `Error: ${error.message}`;
  }
});

refreshManualLeadsButton.addEventListener("click", async () => {
  manualLeadStatus.textContent = "Loading leads...";
  try {
    const data = await refreshManualLeads(50);
    manualLeadStatus.textContent = `Loaded ${data.length} leads.`;
    manualLeadOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    manualLeadStatus.textContent = `Error: ${error.message}`;
  }
});

applyManualLeadFiltersButton.addEventListener("click", async () => {
  manualLeadStatus.textContent = "Applying filters...";
  try {
    const data = await refreshManualLeads(50);
    manualLeadStatus.textContent = `Filtered results: ${data.length} leads.`;
    manualLeadOutput.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    manualLeadStatus.textContent = `Error: ${error.message}`;
  }
});

refreshManualLeads(20).catch(() => {
  manualLeadsBody.innerHTML = `<tr><td colspan="7">Unable to load inbox.</td></tr>`;
});
