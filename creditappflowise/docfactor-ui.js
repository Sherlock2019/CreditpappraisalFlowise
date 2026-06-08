function serviceBase(storageKey, port, fallbackHost = "127.0.0.1") {
  const stored = localStorage.getItem(storageKey);
  if (stored && !stored.includes("backend") && !stored.includes("flowise")) return stored.replace(/\/$/, "");
  const host = window.location.hostname && window.location.hostname !== "0.0.0.0" ? window.location.hostname : fallbackHost;
  return `http://${host}:${port}`;
}

localStorage.removeItem("docfactor_api_base");
localStorage.removeItem("docfactor_flowise_base");

let API_BASE = serviceBase("hyperspeed_api_base", 8000);
const FLOWISE_BASE = serviceBase("hyperspeed_flowise_base", 3001);
const FLOWISE_CHATFLOW_ID = "6f946e8b-2d35-4fd4-9ff9-158db1f0b820";

const state = {
  customers: [],
  documents: [],
  sessionId: null,
  selectedDocumentId: null,
  selectedDocumentIds: [],
  lastAssistantByLog: {},
  loanPolicyScore: null,
  committeeCase: null,
  finalDecision: null,
  emailDraft: null,
  connectorOptions: [],
  connectorDocuments: [],
};

const PROVIDERS = [
  ["local_mistral_ollama", "Local Ollama"],
  ["ollama", "Ollama"],
  ["openai", "OpenAI"],
  ["deepseek", "DeepSeek"],
  ["custom_public_api", "Custom Public API"],
];

const LOCAL_LLM_MODELS = [
  ["gemma2:9b", "Gemma 2 9B"],
  ["mistral", "Mistral"],
];

const SUPPORTED_UPLOAD_SUFFIXES = [".pdf", ".txt", ".csv", ".xlsx", ".xls", ".docx"];
const DOCUMENT_EXTENSION_ORDER = { ".docx": 0, ".pdf": 1, ".xlsx": 2, ".xls": 3, ".csv": 4, ".txt": 5 };
const DOCUMENT_STATUS_ORDER = { ingested: 0, uploaded: 1, processing: 2, error: 3 };
const CREDIT_QUESTION_HISTORY_KEY = "docfactor_credit_appraisal_question_history";
const ALL_CUSTOMERS_VALUE = "__all_customers__";
const CREDIT_READY_QUESTIONS = [
  "Summarize credit risk with citations",
  "Calculate DTI/LTV policy result",
  "Review collateral coverage",
  "List missing documents",
  "Prepare committee summary",
  "Draft customer follow-up email",
  "Identify overdue debt, repayment stress, and cash-flow warning signs",
  "Compare this case against retail bank policy and list approval conditions",
  "Flag fraud, document inconsistency, or valuation exception signals",
  "Recommend next credit officer actions before human decision",
];
const CONNECTOR_METHODS = {
  s3: {
    title: "S3 object import",
    hint: "List and import supported documents from an S3 bucket or S3-compatible storage prefix.",
    fields: [
      ["bucket", "Bucket", "credit-documents"],
      ["prefix", "Prefix / folder", "customers/customer-a/"],
      ["region", "Region", "us-east-1"],
      ["endpoint_url", "Endpoint URL", "http://127.0.0.1:9000"],
      ["access_key_id", "Access key ID", ""],
      ["secret_access_key", "Secret access key", "", "password"],
    ],
  },
  sharepoint: {
    title: "SharePoint drive import",
    hint: "Uses the SharePoint connector path. The backend currently marks this connector as a placeholder until Graph API download is implemented.",
    fields: [
      ["tenant_id", "Tenant ID", ""],
      ["client_id", "Client ID", ""],
      ["client_secret", "Client secret", "", "password"],
      ["site_id", "Site ID", ""],
      ["drive_id", "Drive ID", ""],
      ["folder_path", "Folder path", "/Shared Documents/Credit"],
    ],
  },
  opentext: {
    title: "OpenText repository import",
    hint: "Uses the OpenText connector path. Backend download is currently a placeholder.",
    fields: [["base_url", "Base URL", ""], ["client_id", "Client ID", ""], ["client_secret", "Client secret", "", "password"], ["repository_id", "Repository ID", ""]],
  },
  hyland: {
    title: "Hyland OnBase import",
    hint: "Uses the Hyland connector path. Backend download is currently a placeholder.",
    fields: [["base_url", "Base URL", ""], ["client_id", "Client ID", ""], ["client_secret", "Client secret", "", "password"], ["repository_id", "Repository ID", ""]],
  },
  filenet: {
    title: "IBM FileNet import",
    hint: "Uses the FileNet connector path. Backend download is currently a placeholder.",
    fields: [["base_url", "Base URL", ""], ["username", "Username", ""], ["password", "Password", "", "password"], ["object_store", "Object store", ""]],
  },
  servicenow: {
    title: "ServiceNow attachment import",
    hint: "Uses the ServiceNow connector path. Backend download is currently a placeholder.",
    fields: [["instance_url", "Instance URL", ""], ["username", "Username", ""], ["password", "Password", "", "password"], ["table", "Table", "incident"]],
  },
  salesforce: {
    title: "Salesforce content import",
    hint: "Uses the Salesforce connector path. Backend download is currently a placeholder.",
    fields: [
      ["instance_url", "Instance URL", ""],
      ["client_id", "Client ID", ""],
      ["client_secret", "Client secret", "", "password"],
      ["username", "Username", ""],
      ["password", "Password", "", "password"],
      ["security_token", "Security token", "", "password"],
    ],
  },
  cloud_storage: {
    title: "Generic cloud storage import",
    hint: "Uses the generic cloud-storage connector path. Backend download is currently a placeholder.",
    fields: [["provider", "Provider", "minio"], ["endpoint", "Endpoint", ""], ["access_key", "Access key", ""], ["secret_key", "Secret key", "", "password"], ["bucket", "Bucket", ""], ["prefix", "Prefix", ""]],
  },
};

const $ = (id) => document.getElementById(id);

function selectedUploadFiles() {
  return [
    ...Array.from($("fileInput")?.files || []),
    ...Array.from($("folderInput")?.files || []),
  ];
}

function clearUploadInputs() {
  for (const id of ["fileInput", "folderInput", "documentFileInput"]) {
    const input = $(id);
    if (input) input.value = "";
  }
}

function uploadDisplayName(file) {
  return file.webkitRelativePath || file.name;
}

function uploadServerFilename(file) {
  return uploadDisplayName(file).replace(/^[./\\]+/, "").replace(/[\\/:*?"<>|]+/g, "__");
}

function syntheticCustomerCode(value) {
  return String(value || "").match(/\bCUST-\d{3,}\b/i)?.[0]?.toUpperCase() || "";
}

function syntheticCustomerId(value) {
  const match = String(value || "").match(/\bCUST-(\d{3,})\b/i);
  return match ? Number(match[1]) : null;
}

function uploadRouteForFile(file, fallbackCustomerId = selectedCustomerId()) {
  const parsedCustomerCode = syntheticCustomerCode(uploadDisplayName(file));
  return parsedCustomerCode || fallbackCustomerId || null;
}

function scanUploadFiles(files = selectedUploadFiles(), fallbackCustomerId = selectedCustomerId()) {
  const groups = new Map();
  const unsupported = [];
  const unrouted = [];
  const parsedCustomerCodes = new Set();

  for (const file of files) {
    const displayName = uploadDisplayName(file);
    const parsedCustomerCode = syntheticCustomerCode(displayName);
    const customerId = parsedCustomerCode || fallbackCustomerId || null;
    const supported = SUPPORTED_UPLOAD_SUFFIXES.some((suffix) => file.name.toLowerCase().endsWith(suffix));

    if (parsedCustomerCode) parsedCustomerCodes.add(parsedCustomerCode);
    if (!supported) unsupported.push(displayName);
    if (!customerId) unrouted.push(displayName);
    if (customerId) groups.set(customerId, (groups.get(customerId) || 0) + 1);
  }

  return {
    files,
    groups,
    unsupported,
    unrouted,
    parsedCustomerCodes,
  };
}

function uploadScanSummary(scan = scanUploadFiles()) {
  if (!scan.files.length) return "Choose files or a folder to scan before upload.";
  const routeSummary = [...scan.groups.entries()]
    .sort(([left], [right]) => String(left).localeCompare(String(right), undefined, { numeric: true }))
    .map(([customerId, count]) => `customer ${customerId}: ${count}`)
    .join(", ");
  const pieces = [
    `Dry-run scan: ${scan.files.length} file${scan.files.length === 1 ? "" : "s"}`,
    routeSummary ? `routes ${routeSummary}` : "no customer route found",
  ];
  if (scan.parsedCustomerCodes.size) pieces.push(`${scan.parsedCustomerCodes.size} customer code${scan.parsedCustomerCodes.size === 1 ? "" : "s"} parsed from file/folder names`);
  if (scan.unsupported.length) pieces.push(`unsupported: ${scan.unsupported.slice(0, 4).join(", ")}${scan.unsupported.length > 4 ? "..." : ""}`);
  if (scan.unrouted.length) pieces.push(`missing customer code: ${scan.unrouted.slice(0, 4).join(", ")}${scan.unrouted.length > 4 ? "..." : ""}`);
  return `${pieces.join(". ")}.`;
}

function showUploadScan() {
  const status = $("documentStatus");
  if (!status) return;
  status.textContent = uploadScanSummary(scanUploadFiles());
}

function activeSource() {
  return $("sourceSelect")?.value || "manual_upload";
}

function connectorMethod(source = activeSource()) {
  return CONNECTOR_METHODS[source] || {
    title: "Connector import",
    hint: "Configure this data source, then list or import documents through the backend connector.",
    fields: [["folder_path", "Folder / prefix", ""]],
  };
}

function connectorConfig(source = activeSource()) {
  const config = {};
  for (const [key] of connectorMethod(source).fields) {
    const value = $(`connector_${key}`)?.value.trim();
    if (value) config[key] = value;
  }
  return config;
}

function selectedConnectorDocuments() {
  const checked = Array.from(document.querySelectorAll(".connector-doc-checkbox:checked")).map((input) => Number(input.value));
  if (!checked.length) return state.connectorDocuments;
  return checked.map((index) => state.connectorDocuments[index]).filter(Boolean);
}

function renderConnectorDocuments() {
  const container = $("connectorDocsList");
  if (!container) return;
  if (!state.connectorDocuments.length) {
    container.textContent = "No source documents listed yet.";
    return;
  }
  container.innerHTML = state.connectorDocuments
    .map(
      (doc, index) => `
        <label>
          <input class="connector-doc-checkbox" type="checkbox" value="${index}" checked />
          <span>${htmlEscape(doc.filename || doc.external_document_id || doc.source_uri)}${doc.size_bytes ? ` (${Math.ceil(doc.size_bytes / 1024)} KB)` : ""}</span>
        </label>
      `
    )
    .join("");
}

function renderSourceMethod() {
  const source = activeSource();
  const isManual = source === "manual_upload";
  $("manualUploadMethod")?.classList.toggle("hidden", !isManual);
  $("connectorUploadMethod")?.classList.toggle("hidden", isManual);
  const uploadButton = $("uploadBtn");
  if (uploadButton) uploadButton.textContent = isManual ? "Upload" : "Import source";
  const ingestButton = $("ingestSelectedBtn");
  if (ingestButton) ingestButton.disabled = !isManual;
  if (isManual) return;

  const method = connectorMethod(source);
  if ($("connectorMethodTitle")) $("connectorMethodTitle").textContent = method.title;
  if ($("connectorMethodHint")) $("connectorMethodHint").textContent = method.hint;
  const fields = $("connectorFields");
  if (fields) {
    fields.innerHTML = method.fields
      .map(([key, label, placeholder, type]) => `<label>${htmlEscape(label)}<input id="connector_${htmlEscape(key)}" type="${type || "text"}" placeholder="${htmlEscape(placeholder || "")}" /></label>`)
      .join("");
  }
  state.connectorDocuments = [];
  renderConnectorDocuments();
}

function apiCandidates() {
  const sameOriginApi = window.location.origin && window.location.origin !== "null" ? `${window.location.origin}/api` : "";
  return [...new Set([sameOriginApi, API_BASE, serviceBase("hyperspeed_api_base", 8000), "http://127.0.0.1:8000", "http://localhost:8000"].filter(Boolean))];
}

function htmlEscape(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function setTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("creditappflowise_theme", theme);
  const button = $("themeToggle");
  if (button) button.textContent = theme === "dark" ? "Light" : "Dark";
}

function initTheme() {
  setTheme(localStorage.getItem("creditappflowise_theme") || "light");
  $("themeToggle")?.addEventListener("click", () => {
    setTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
  });
}

function setDot(id, status) {
  const el = $(id);
  if (!el) return;
  el.className = `dot ${status}`;
}

async function ping(url) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 2200);
  try {
    await fetch(url, { signal: controller.signal, mode: "cors" });
    return true;
  } catch {
    return false;
  } finally {
    clearTimeout(timeout);
  }
}

async function refreshStatus() {
  let backend = false;
  for (const base of apiCandidates()) {
    backend = await ping(`${base}/health`);
    if (backend) {
      API_BASE = base;
      localStorage.setItem("hyperspeed_api_base", base);
      break;
    }
  }
  const streamlit = await ping("http://127.0.0.1:8501");
  const flowise = await ping(FLOWISE_BASE);
  setDot("apiStatus", backend ? "ok" : "bad");
  setDot("uiStatus", streamlit ? "ok" : "bad");
  setDot("flowiseStatus", flowise ? "ok" : "bad");
  if ($("metricBackend")) $("metricBackend").textContent = backend ? "Online" : "Offline";
  if ($("metricFlowise")) $("metricFlowise").textContent = flowise ? "Online" : "Offline";
  if ($("documentStatus")) {
    $("documentStatus").textContent = backend ? `Backend online at ${API_BASE}. Select a customer, then upload.` : `Backend offline. Tried ${apiCandidates().join(", ")}.`;
  }
}

async function api(path, options = {}) {
  const requestOptions = {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
      ...(options.headers || {}),
    },
  };
  const networkErrors = [];
  for (const base of apiCandidates()) {
    let response;
    try {
      response = await fetch(`${base}${path}`, requestOptions);
    } catch (error) {
      networkErrors.push(`${base}: ${error.message}`);
      continue;
    }
    API_BASE = base;
    localStorage.setItem("hyperspeed_api_base", base);
    if (!response.ok) {
      let detail = response.statusText;
      const raw = await response.text();
      try {
        const payload = raw ? JSON.parse(raw) : null;
        detail = payload?.detail || JSON.stringify(payload);
      } catch {
        detail = raw || detail || `HTTP ${response.status}`;
      }
      throw new Error(detail || `HTTP ${response.status}`);
    }
    return response.json();
  }
  throw new Error(`Failed to fetch backend. Tried: ${networkErrors.join("; ")}`);
}

function selectedCustomerId(selectId = "customerSelect") {
  const select = $(selectId);
  if (select?.value === ALL_CUSTOMERS_VALUE) return null;
  return select?.value ? Number(select.value) : null;
}

function selectedCustomerLabel(selectId = "customerSelect") {
  const select = $(selectId);
  if (!select?.value) return "no customer selected";
  if (select.value === ALL_CUSTOMERS_VALUE) return "All customers";
  const label = select.selectedOptions?.[0]?.textContent || `Customer ${select.value}`;
  return label.replace(/^\s*\d+\s*-\s*/, "").trim() || `Customer ${select.value}`;
}

function selectedCustomerScope(selectId = "customerSelect") {
  return $(selectId)?.value === ALL_CUSTOMERS_VALUE ? "all" : "selected";
}

function selectedCustomer(selectId = "customerSelect") {
  const id = selectedCustomerId(selectId);
  return state.customers.find((customer) => String(customer.id) === String(id)) || null;
}

function stageMoney(value) {
  return Number(value || 0).toLocaleString(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
}

function checklistHtml(items) {
  return items
    .map(
      ([label, done]) => `
        <div class="check-item">
          <span class="dot ${done ? "ok" : "wait"}"></span>
          <strong>${htmlEscape(label)}</strong>
        </div>`
    )
    .join("");
}

function filenameStem(filename) {
  return String(filename || "").replace(/\.[^.]+$/, "").toLowerCase();
}

function filenameExtension(filename) {
  const match = String(filename || "").toLowerCase().match(/\.[^.]+$/);
  return match ? match[0] : "";
}

function sortDocumentsByCustomerName(documents) {
  return [...documents].sort((left, right) => {
    const stemCompare = filenameStem(left.filename).localeCompare(filenameStem(right.filename), undefined, { numeric: true });
    if (stemCompare) return stemCompare;

    const leftExtension = DOCUMENT_EXTENSION_ORDER[filenameExtension(left.filename)] ?? 99;
    const rightExtension = DOCUMENT_EXTENSION_ORDER[filenameExtension(right.filename)] ?? 99;
    if (leftExtension !== rightExtension) return leftExtension - rightExtension;

    const leftStatus = DOCUMENT_STATUS_ORDER[String(left.status || "").toLowerCase()] ?? 50;
    const rightStatus = DOCUMENT_STATUS_ORDER[String(right.status || "").toLowerCase()] ?? 50;
    if (leftStatus !== rightStatus) return leftStatus - rightStatus;

    return Number(left.id || 0) - Number(right.id || 0);
  });
}

function updateSelectedDocumentIds() {
  state.selectedDocumentIds = Array.from(document.querySelectorAll("input[name=documentPick]:checked")).map((input) => Number(input.value));
  state.selectedDocumentId = state.selectedDocumentIds[0] || null;
  const selectAll = $("docsSelectAll");
  if (selectAll) {
    const checkboxes = Array.from(document.querySelectorAll("input[name=documentPick]"));
    selectAll.checked = checkboxes.length > 0 && checkboxes.every((input) => input.checked);
    selectAll.indeterminate = checkboxes.some((input) => input.checked) && !selectAll.checked;
  }
}

async function loadCustomers() {
  try {
    state.customers = await api("/customers");
  } catch (error) {
    const message = `Backend unreachable: ${error.message}`;
    const selects = [$("customerSelect"), $("mainCustomerSelect")].filter(Boolean);
    for (const select of selects) select.innerHTML = `<option value="">${htmlEscape(message)}</option>`;
    if ($("documentStatus")) $("documentStatus").textContent = message;
    if ($("metricCustomers")) $("metricCustomers").textContent = "--";
    return;
  }
  const selects = [$("customerSelect"), $("mainCustomerSelect")].filter(Boolean);
  for (const select of selects) {
    const current = select.value;
    const allOption = `<option value="${ALL_CUSTOMERS_VALUE}">All customers - general questions</option>`;
    const customerOptions = state.customers.map((c) => `<option value="${c.id}">${htmlEscape(c.id)} - ${htmlEscape(c.name)}</option>`).join("");
    select.innerHTML = state.customers.length ? `${allOption}${customerOptions}` : `<option value="">No customers yet</option>`;
    if (current && state.customers.some((c) => String(c.id) === current)) select.value = current;
  }
  if ($("metricCustomers")) $("metricCustomers").textContent = String(state.customers.length);
  const mainCustomerSelect = $("mainCustomerSelect");
  const customerSelect = $("customerSelect");
  if (state.customers.length && mainCustomerSelect && !mainCustomerSelect.value) mainCustomerSelect.value = String(state.customers[0].id);
  if (state.customers.length && customerSelect && !customerSelect.value) customerSelect.value = String(state.customers[0].id);
  if ($("documentStatus") && state.customers.length) $("documentStatus").textContent = `Selected customer ${$("customerSelect")?.value || state.customers[0].id}. Ready for upload.`;
  renderStagePages();
}

async function refreshCustomersPreservingSelection(selectId = "customerSelect") {
  const select = $(selectId);
  const current = select?.value || "";
  await loadCustomers();
  const refreshedSelect = $(selectId);
  const stillExists = Array.from(refreshedSelect?.options || []).some((option) => option.value === current);
  if (current && stillExists) {
    refreshedSelect.value = current;
  }
}

async function loadDocuments(customerId = selectedCustomerId()) {
  const body = $("documentsBody");
  const summary = $("savedDocsSummary");
  const allCustomersSelected = $("customerSelect")?.value === ALL_CUSTOMERS_VALUE;
  if (!customerId && !allCustomersSelected) {
    if (body) body.innerHTML = `<tr><td colspan="5">No customer selected.</td></tr>`;
    if ($("metricDocuments")) $("metricDocuments").textContent = "--";
    if (summary) summary.textContent = "Select a customer to load saved documents.";
    renderStagePages();
    return;
  }
  const documentPath = allCustomersSelected ? "/documents" : `/documents?customer_id=${customerId}`;
  const scopeLabel = allCustomersSelected ? "all customers" : `customer ${customerId}`;
  state.documents = sortDocumentsByCustomerName(await api(documentPath));
  const ingestedCount = state.documents.filter((doc) => String(doc.status || "").toLowerCase() === "ingested").length;
  if ($("metricDocuments")) $("metricDocuments").textContent = String(state.documents.length);
  if ($("documentStatus")) {
    $("documentStatus").textContent = state.documents.length
      ? `Loaded ${state.documents.length} saved documents for ${scopeLabel}. ${ingestedCount} ingested.`
      : `No saved documents found for ${scopeLabel}. Upload a folder with CUST-### names or choose one customer.`;
  }
  if (summary) {
    summary.innerHTML = state.documents.length
      ? `<strong>${state.documents.length}</strong> saved documents loaded. <strong>${ingestedCount}</strong> ingested.`
      : `No saved documents loaded for ${scopeLabel}.`;
  }
  if (!body) return;
  body.innerHTML = state.documents.length
    ? state.documents
        .map(
          (doc) => `
          <tr>
            <td><input type="checkbox" name="documentPick" value="${doc.id}" ${state.selectedDocumentIds.includes(doc.id) ? "checked" : ""}></td>
            <td>${doc.id}</td>
            <td>${htmlEscape(doc.filename)}</td>
            <td>${htmlEscape(doc.document_type || "")}</td>
            <td>${htmlEscape(doc.status || "")}</td>
          </tr>`
        )
        .join("")
    : `<tr><td colspan="5">No documents uploaded for this customer.</td></tr>`;
  body.querySelectorAll("input[name=documentPick]").forEach((input) => input.addEventListener("change", updateSelectedDocumentIds));
  const selectAll = $("docsSelectAll");
  if (selectAll) {
    selectAll.checked = false;
    selectAll.indeterminate = false;
    selectAll.onchange = () => {
      body.querySelectorAll("input[name=documentPick]").forEach((input) => {
        input.checked = selectAll.checked;
      });
      updateSelectedDocumentIds();
    };
  }
  updateSelectedDocumentIds();
  renderStagePages();
}

async function recoverSavedDocuments() {
  const status = $("documentStatus");
  const button = $("recoverDocsBtn");
  if (button) button.disabled = true;
  if (status) status.textContent = "Scanning persistent upload storage for saved files...";
  try {
    const response = await api("/documents/recover-from-disk", { method: "POST" });
    const recovered = response.recovered_documents || 0;
    const existing = response.existing_documents || 0;
    if (status) {
      status.textContent = `Recovery complete. ${recovered} documents recovered, ${existing} existing files confirmed. Cache now has ${response.cache?.documents ?? "--"} documents.`;
    }
    await loadCustomers();
    await loadDocuments();
  } catch (error) {
    if (status) status.textContent = `Recovery failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

function providerPayload() {
  const provider = $("providerSelect")?.value || "local_mistral_ollama";
  const localModel = $("llmModelSelect")?.value || "gemma2:9b";
  return {
    llm_provider: provider,
    llm_model: provider === "local_mistral_ollama" || provider === "ollama" ? localModel : undefined,
    temperature: Number($("temperatureInput")?.value || 0.2),
    max_tokens: Number($("maxTokensInput")?.value || 1200),
  };
}

function numberValue(id, fallback = 0) {
  const value = Number($(id)?.value || fallback);
  return Number.isFinite(value) ? value : fallback;
}

function selectedValues(id) {
  const select = $(id);
  return select ? Array.from(select.selectedOptions).map((option) => option.value).filter(Boolean) : [];
}

function linesValue(id) {
  return String($(id)?.value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function loanPolicyWorkflowContext() {
  const context = {};
  const fieldMap = {
    loan_amount: "loanAmountInput",
    collateral_value: "collateralValueInput",
    monthly_income: "monthlyIncomeInput",
    monthly_debt_payments: "monthlyDebtInput",
    term_months: "termMonthsInput",
    customer_email: "customerEmailInput",
    approved_amount: "approvedAmountInput",
    approved_rate_pct: "approvedRateInput",
    decision: "finalDecisionInput",
    conditions: "decisionConditionsInput",
  };

  for (const [key, id] of Object.entries(fieldMap)) {
    const element = $(id);
    if (!element) continue;
    context[key] = id === "decisionConditionsInput" ? linesValue(id) : element.value;
  }

  if ($("fraudIndicatorsInput")) context.fraud_indicators = selectedValues("fraudIndicatorsInput");
  if ($("missingDocumentsInput")) context.missing_documents = selectedValues("missingDocumentsInput");

  if (state.loanPolicyScore) {
    Object.assign(context, {
      policy_score_id: state.loanPolicyScore.policy_score_id,
      dti_pct: state.loanPolicyScore.dti?.value_pct,
      dti_band: state.loanPolicyScore.dti?.band,
      ltv_pct: state.loanPolicyScore.ltv?.value_pct,
      ltv_band: state.loanPolicyScore.ltv?.band,
      estimated_annual_rate_pct: state.loanPolicyScore.interest?.estimated_annual_rate_pct,
      estimated_monthly_payment: state.loanPolicyScore.interest?.estimated_monthly_payment,
      policy_recommendation: state.loanPolicyScore.policy?.recommendation,
      committee_required: state.loanPolicyScore.policy?.committee_required,
      reason_codes: state.loanPolicyScore.policy?.reason_codes || [],
    });
  }

  if (state.committeeCase) {
    context.committee_case_id = state.committeeCase.committee_case_id;
    context.committee_status = state.committeeCase.status;
  }
  if (state.finalDecision) context.decision_id = state.finalDecision.decision_id;
  if (state.emailDraft) {
    context.email_draft_id = state.emailDraft.email_draft_id;
    context.email_subject = state.emailDraft.subject;
    context.customer_email_draft = state.emailDraft.body;
  }

  return context;
}

function addMessage(logId, role, text) {
  const log = $(logId);
  if (!log) return;
  const div = document.createElement("div");
  div.className = `message ${role}`;
  div.textContent = text;
  log.appendChild(div);
  log.scrollTop = log.scrollHeight;
  if (role === "assistant" && !text.startsWith("Thinking through")) {
    state.lastAssistantByLog[logId] = text;
  }
}

function creditQuestionHistory() {
  try {
    const parsed = JSON.parse(localStorage.getItem(CREDIT_QUESTION_HISTORY_KEY) || "[]");
    return Array.isArray(parsed) ? parsed.filter(Boolean).map(String).slice(0, 20) : [];
  } catch {
    return [];
  }
}

function saveCreditQuestion(question) {
  const clean = String(question || "").trim();
  if (!clean) return;
  const history = [clean, ...creditQuestionHistory().filter((item) => item.toLowerCase() !== clean.toLowerCase())].slice(0, 20);
  localStorage.setItem(CREDIT_QUESTION_HISTORY_KEY, JSON.stringify(history));
  renderCreditQuestions();
}

function loadCreditQuestion(question) {
  const input = $("creditChatInput");
  if (!input) return;
  input.value = question;
  input.focus();
}

function questionChip(question, source) {
  return `<button class="question-chip" type="button" data-question-source="${source}" data-question="${htmlEscape(question)}">${htmlEscape(question)}</button>`;
}

function renderCreditQuestions() {
  const ready = $("creditReadyQuestions");
  if (ready) ready.innerHTML = CREDIT_READY_QUESTIONS.map((question) => questionChip(question, "ready")).join("");
  const previous = $("creditPreviousQuestions");
  if (previous) {
    const history = creditQuestionHistory();
    previous.innerHTML = history.length
      ? history.map((question) => questionChip(question, "history")).join("")
      : `<span class="question-empty">No previous questions yet.</span>`;
  }
}

function initCreditQuestionBank() {
  renderCreditQuestions();
  document.querySelectorAll("#creditReadyQuestions, #creditPreviousQuestions").forEach((container) => {
    container.addEventListener("click", (event) => {
      const button = event.target.closest("[data-question]");
      if (button) loadCreditQuestion(button.dataset.question);
    });
  });
  $("clearCreditQuestionHistoryBtn")?.addEventListener("click", () => {
    localStorage.removeItem(CREDIT_QUESTION_HISTORY_KEY);
    renderCreditQuestions();
  });
}

function spokenAnswerText(text) {
  return String(text || "")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/^#{1,6}\s*/gm, "")
    .replace(/\*\*/g, "")
    .replace(/\*/g, "")
    .replace(/[_`]/g, "")
    .replace(/\n\s*Provider:.*$/s, "")
    .replace(/\n\s*Citations:\s*$/gm, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function preferredBritishVoice(voices, gender) {
  const names =
    gender === "female"
      ? [
          "Microsoft Sonia Online",
          "Microsoft Libby Online",
          "Google UK English Female",
          "Microsoft Hazel",
          "Serena",
          "Fiona",
          "Susan",
          "Libby",
          "Sonia",
          "Hazel",
        ]
      : [
          "Microsoft Ryan Online",
          "Microsoft George Online",
          "Google UK English Male",
          "Microsoft Daniel",
          "Daniel",
          "George",
          "Arthur",
          "Oliver",
          "Ryan",
        ];

  for (const name of names) {
    const found = voices.find((voice) => voice.name.toLowerCase().includes(name.toLowerCase()));
    if (found) return found;
  }

  const genderWord = gender === "female" ? "female" : "male";
  return (
    voices.find((voice) => voice.lang === "en-GB" && voice.name.toLowerCase().includes(genderWord)) ||
    voices.find((voice) => voice.lang === "en-GB") ||
    voices.find((voice) => voice.lang?.toLowerCase().startsWith("en")) ||
    voices[0]
  );
}

function getVoiceGender(prefix) {
  const select = $("jarvis_voice_gender") || $(`${prefix}VoiceGender`);
  return select?.value || localStorage.getItem("hyperspeed_british_voice_gender") || localStorage.getItem("mig_jarvis_gender") || "male";
}

function speakBritish(text, prefix = "main") {
  if (!text) return;
  localStorage.setItem("mig_jarvis_voice", $("enable_jarvis_voice")?.checked === false ? "false" : "true");
  localStorage.setItem("mig_jarvis_gender", getVoiceGender(prefix));
  if (typeof window.jarvisSpeakBritish === "function") {
    window.jarvisSpeakBritish(text);
    const status = $(`${prefix}VoiceStatus`);
    if (status) status.textContent = "Speaking with Cloudjumper British voice module.";
    return;
  }
  if (!("speechSynthesis" in window)) {
    $(`${prefix}VoiceStatus`) && ($(`${prefix}VoiceStatus`).textContent = "Speech synthesis is not supported in this browser.");
    return;
  }

  const gender = getVoiceGender(prefix);
  window.speechSynthesis.cancel();
  const utterance = new SpeechSynthesisUtterance(text.replace(/\s+/g, " ").trim());
  utterance.lang = "en-GB";
  utterance.rate = gender === "female" ? 0.98 : 0.96;
  utterance.pitch = gender === "female" ? 1.08 : 0.88;
  utterance.volume = 1;

  const setVoiceAndSpeak = () => {
    const voices = window.speechSynthesis.getVoices();
    const voice = preferredBritishVoice(voices, gender);
    if (voice) utterance.voice = voice;
    const status = $(`${prefix}VoiceStatus`);
    if (status) status.textContent = voice ? `Speaking with ${voice.name}` : "Speaking with browser default voice.";
    window.speechSynthesis.speak(utterance);
  };

  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.addEventListener("voiceschanged", setVoiceAndSpeak, { once: true });
  } else {
    setVoiceAndSpeak();
  }
}

function startBritishDictation(prefix, inputId) {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = $(`${prefix}VoiceStatus`);
  if (!SpeechRecognition) {
    if (status) status.textContent = "Speech recognition is not supported in this browser.";
    return;
  }

  const recognition = new SpeechRecognition();
  recognition.lang = "en-GB";
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  if (status) status.textContent = "Listening in British English...";
  recognition.onresult = (event) => {
    const transcript = event.results?.[0]?.[0]?.transcript || "";
    const input = $(inputId);
    if (input) {
      input.value = transcript;
      input.focus();
    }
    if (status) status.textContent = "Voice captured. Review it, then send.";
  };
  recognition.onerror = (event) => {
    if (status) status.textContent = `Voice input failed: ${event.error || "unknown error"}`;
  };
  recognition.onend = () => {
    if (status && status.textContent === "Listening in British English...") status.textContent = "Voice input stopped.";
  };
  recognition.start();
}

function initBritishVoice(prefix, inputId, logId) {
  const enabled = $("enable_jarvis_voice");
  const savedEnabled = localStorage.getItem("mig_jarvis_voice");
  if (enabled && savedEnabled !== null) enabled.checked = savedEnabled !== "false";
  enabled?.addEventListener("change", () => {
    localStorage.setItem("mig_jarvis_voice", enabled.checked ? "true" : "false");
  });

  const gender = $("jarvis_voice_gender") || $(`${prefix}VoiceGender`);
  const savedGender = localStorage.getItem("hyperspeed_british_voice_gender") || localStorage.getItem("mig_jarvis_gender");
  if (gender && (savedGender === "male" || savedGender === "female")) gender.value = savedGender;
  gender?.addEventListener("change", () => {
    localStorage.setItem("hyperspeed_british_voice_gender", gender.value);
    localStorage.setItem("mig_jarvis_gender", gender.value);
  });

  const announceVoice = () => {
    const voice = preferredBritishVoice(window.speechSynthesis.getVoices(), getVoiceGender(prefix));
    const status = $(`${prefix}VoiceStatus`);
    if (status && voice) status.textContent = `Best British voice found: ${voice.name}`;
  };
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    if (typeof window.speechSynthesis.addEventListener === "function") {
      window.speechSynthesis.addEventListener("voiceschanged", announceVoice);
    } else {
      window.speechSynthesis.onvoiceschanged = announceVoice;
    }
  }

  $(`${prefix}VoiceBtn`)?.addEventListener("click", () => startBritishDictation(prefix, inputId));
  $(`${prefix}ReadBtn`)?.addEventListener("click", () => {
    speakBritish(state.lastAssistantByLog[logId] || "No assistant answer is available to read yet.", prefix);
  });
  $(`${prefix}TestVoiceBtn`)?.addEventListener("click", () => {
    speakBritish("HyperSpeed Banking AI Copilot voice module is online. Human credit officer review is required.", prefix);
  });
}

async function sendChat({ inputId, logId, customerSelectId, voicePrefix = "credit" }) {
  const input = $(inputId);
  const text = input?.value.trim();
  const customerId = selectedCustomerId(customerSelectId);
  const allCustomers = selectedCustomerScope(customerSelectId) === "all";
  const customerLabel = selectedCustomerLabel(customerSelectId);
  if (!text || !input) return;
  if (!customerId && !allCustomers) {
    addMessage(logId, "assistant", "Create or select a customer first.");
    return;
  }
  input.value = "";
  if (inputId === "creditChatInput") saveCreditQuestion(text);
  addMessage(logId, "user", text);
  speakBritish(allCustomers ? `You ask me ${text} for All customers` : `You ask me ${text} for Customer ${customerLabel}`, voicePrefix);
  addMessage(logId, "assistant", "Thinking through retrieved customer context...");
  try {
    const response = await api("/chat", {
      method: "POST",
      body: JSON.stringify({
        customer_id: allCustomers ? null : customerId,
        message: text,
        session_id: state.sessionId,
        workflow_context: loanPolicyWorkflowContext(),
        ...providerPayload(),
      }),
    });
    state.sessionId = response.session_id;
    const citationText = formatCitations(response.citations);
    const assistantText = `${response.answer}${citationText}\n\nProvider: ${response.llm_provider_used || "unknown"} / ${response.llm_model_used || "unknown"}`;
    addMessage(logId, "assistant", assistantText);
    speakBritish(spokenAnswerText(response.answer), voicePrefix);
  } catch (error) {
    addMessage(logId, "assistant", `AI response failed: ${error.message}`);
  }
}

function formatCitations(citations = []) {
  if (!citations.length) return "";
  return `\n\nCitations:\n${citations
    .map((c) => `- ${c.document_name || c.filename || "document"}${c.page_number ? `, page ${c.page_number}` : ""}`)
    .join("\n")}`;
}

async function createCustomer(event) {
  event.preventDefault();
  const name = $("customerName")?.value.trim();
  if (!name) return;
  await api("/customers", {
    method: "POST",
    body: JSON.stringify({
      name,
      customer_type: $("customerType")?.value.trim() || "business",
      industry: $("customerIndustry")?.value.trim() || null,
      country: $("customerCountry")?.value.trim() || null,
    }),
  });
  $("customerForm")?.reset();
  if ($("customerType")) $("customerType").value = "business";
  await loadCustomers();
  await loadDocuments();
}

async function uploadDocuments() {
  if (activeSource() !== "manual_upload") {
    await importConnectorDocuments();
    return;
  }
  const fallbackCustomerId = selectedCustomerId();
  const files = selectedUploadFiles();
  const status = $("documentStatus");
  const button = $("uploadBtn");
  const scan = scanUploadFiles(files, fallbackCustomerId);
  if (!files.length) {
    if (status) status.textContent = "Choose at least one file or folder.";
    return;
  }
  if (scan.unrouted.length) {
    if (status) status.textContent = `Choose a specific customer, or upload a folder/files whose names include CUST-###. Missing route for: ${scan.unrouted.slice(0, 5).join(", ")}${scan.unrouted.length > 5 ? "..." : ""}`;
    return;
  }
  if (scan.unsupported.length) {
    if (status) status.textContent = `Unsupported file type: ${scan.unsupported.slice(0, 5).join(", ")}${scan.unsupported.length > 5 ? "..." : ""}. Use PDF, TXT, CSV, XLS, XLSX, or DOCX.`;
    return;
  }
  if (button) button.disabled = true;
  try {
    const uploadedDocs = [];
    const autoIngest = $("autoIngestInput")?.checked !== false;
    if (status) status.textContent = uploadScanSummary(scan);
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      const customerId = uploadRouteForFile(file, fallbackCustomerId);
      if (status) status.textContent = `Uploading ${index + 1}/${files.length} to customer ${customerId}: ${uploadDisplayName(file)}`;
      const form = new FormData();
      form.append("customer_id", String(customerId));
      form.append("document_type", $("documentType")?.value || "financial_statement");
      form.append("file", file, uploadServerFilename(file));
      const uploaded = await api("/documents/upload", { method: "POST", body: form });
      if (uploaded?.id) uploadedDocs.push(uploaded);
    }
    if (autoIngest && uploadedDocs.length) {
      const succeeded = [];
      const failed = [];
      for (let index = 0; index < uploadedDocs.length; index += 1) {
        const document = uploadedDocs[index];
        if (status) status.textContent = `Auto-ingesting ${index + 1}/${uploadedDocs.length}: ${document.filename || `document ${document.id}`}...`;
        try {
          await api(`/ingest/${document.id}`, { method: "POST" });
          succeeded.push(document.id);
        } catch (error) {
          failed.push(`${document.filename || document.id}: ${error.message}`);
        }
      }
      if (status) {
        status.textContent = failed.length
          ? `Uploaded ${files.length}. Auto-ingested ${succeeded.length}/${uploadedDocs.length}. Failed: ${failed.join("; ")}`
          : `Uploaded and ingested ${succeeded.length} document${succeeded.length === 1 ? "" : "s"}.`;
      }
    } else if (status) {
      status.textContent = "Upload complete. Select a document below, then click Ingest selected.";
    }
    clearUploadInputs();
    state.selectedDocumentIds = [];
    state.selectedDocumentId = null;
    await refreshCustomersPreservingSelection("customerSelect");
    await loadDocuments(selectedCustomerId());
  } catch (error) {
    if (status) status.textContent = `Upload failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function listConnectorDocuments() {
  const customerId = selectedCustomerId();
  const status = $("documentStatus");
  const button = $("listConnectorDocsBtn");
  const source = activeSource();
  if (source === "manual_upload") {
    if (status) status.textContent = "Manual upload does not need source listing.";
    return;
  }
  if (!customerId) {
    if (status) status.textContent = "Select a customer before listing connector documents.";
    return;
  }
  if (button) button.disabled = true;
  try {
    const config = connectorConfig(source);
    const response = await api("/connectors/list-documents", {
      method: "POST",
      body: JSON.stringify({
        source_type: source,
        customer_id: customerId,
        prefix: config.prefix || undefined,
        folder_path: config.folder_path || undefined,
        config,
      }),
    });
    state.connectorDocuments = response.documents || [];
    renderConnectorDocuments();
    if (status) status.textContent = response.message || `Found ${state.connectorDocuments.length} source document(s).`;
  } catch (error) {
    state.connectorDocuments = [];
    renderConnectorDocuments();
    if (status) status.textContent = `Source list failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function importConnectorDocuments() {
  const customerId = selectedCustomerId();
  const status = $("documentStatus");
  const button = $("uploadBtn");
  const source = activeSource();
  if (!customerId) {
    if (status) status.textContent = "Select a customer before importing from this source.";
    return;
  }

  let documents = selectedConnectorDocuments();
  const directExternalId = $("connectorExternalId")?.value.trim();
  const directSourceUri = $("connectorSourceUri")?.value.trim();
  const directFilename = $("connectorFilename")?.value.trim();
  if (!documents.length && (directExternalId || directSourceUri)) {
    documents = [{ external_document_id: directExternalId, source_uri: directSourceUri, filename: directFilename }];
  }
  if (!documents.length) {
    await listConnectorDocuments();
    documents = selectedConnectorDocuments();
  }
  if (!documents.length) {
    if (status) status.textContent = "No source documents to import. List the source first or enter an external document ID/source URI.";
    return;
  }

  if (button) button.disabled = true;
  try {
    const config = connectorConfig(source);
    const succeeded = [];
    const failed = [];
    for (let index = 0; index < documents.length; index += 1) {
      const document = documents[index];
      if (status) status.textContent = `Importing ${index + 1}/${documents.length}: ${document.filename || document.external_document_id || document.source_uri}`;
      try {
        const response = await api("/connectors/ingest", {
          method: "POST",
          body: JSON.stringify({
            source_type: source,
            customer_id: customerId,
            external_document_id: document.external_document_id || null,
            source_uri: document.source_uri || null,
            filename: document.filename || directFilename || null,
            config,
          }),
        });
        if (response.status === "ingested" || response.document_id) succeeded.push(response.filename || response.document_id);
        else failed.push(response.message || document.filename || document.external_document_id || "unknown document");
      } catch (error) {
        failed.push(`${document.filename || document.external_document_id || document.source_uri}: ${error.message}`);
      }
    }
    if (status) {
      status.textContent = failed.length
        ? `Imported ${succeeded.length}/${documents.length}. Failed: ${failed.join("; ")}`
        : `Imported and ingested ${succeeded.length} source document${succeeded.length === 1 ? "" : "s"}.`;
    }
    state.selectedDocumentIds = [];
    state.selectedDocumentId = null;
    await refreshCustomersPreservingSelection("customerSelect");
    await loadDocuments(customerId);
  } catch (error) {
    if (status) status.textContent = `Source import failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function ingestSelectedDocument() {
  updateSelectedDocumentIds();
  const docIds = state.selectedDocumentIds.length ? state.selectedDocumentIds : state.selectedDocumentId ? [state.selectedDocumentId] : [];
  const status = $("documentStatus");
  const button = $("ingestSelectedBtn");
  if (!docIds.length) {
    if (status) status.textContent = "Select one or more document rows first.";
    return;
  }
  if (button) button.disabled = true;
  try {
    const succeeded = [];
    const failed = [];
    for (let index = 0; index < docIds.length; index += 1) {
      const docId = docIds[index];
      if (status) status.textContent = `Ingesting ${index + 1}/${docIds.length}: document ${docId}...`;
      try {
        await api(`/ingest/${docId}`, { method: "POST" });
        succeeded.push(docId);
      } catch (error) {
        failed.push(`${docId}: ${error.message}`);
      }
    }
    if (status) {
      status.textContent = failed.length
        ? `Ingested ${succeeded.length}/${docIds.length}. Failed: ${failed.join("; ")}`
        : `Ingestion complete for ${succeeded.length} document${succeeded.length === 1 ? "" : "s"}.`;
    }
    state.selectedDocumentIds = [];
    state.selectedDocumentId = null;
    await refreshCustomersPreservingSelection("customerSelect");
    await loadDocuments();
  } catch (error) {
    if (status) status.textContent = `Ingestion failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function deduplicateDocuments() {
  const customerId = selectedCustomerId();
  const status = $("documentStatus");
  const button = $("dedupeDocsBtn");
  if (!customerId) {
    if (status) status.textContent = "Select a customer before removing duplicates.";
    return;
  }
  if (button) button.disabled = true;
  if (status) status.textContent = "Removing duplicate document records...";
  try {
    const response = await api(`/documents/deduplicate?customer_id=${customerId}`, { method: "POST" });
    state.selectedDocumentId = null;
    state.selectedDocumentIds = [];
    if (status) {
      status.textContent = `Removed ${response.duplicates_removed || 0} duplicate documents from ${response.duplicate_groups || 0} duplicate groups.`;
    }
    await loadDocuments(customerId);
  } catch (error) {
    if (status) status.textContent = `Duplicate cleanup failed: ${error.message}`;
  } finally {
    if (button) button.disabled = false;
  }
}

async function generateAssessment() {
  const customerId = selectedCustomerId();
  if (!customerId) {
    $("assessmentOutput").textContent = "Create or select a customer first.";
    return;
  }
  $("assessmentOutput").textContent = "Generating credit assessment from retrieved evidence...";
  try {
    const response = await api(`/credit-assessment/${customerId}`, {
      method: "POST",
      body: JSON.stringify({ ...providerPayload(), workflow_context: loanPolicyWorkflowContext() }),
    });
    $("riskLevel").textContent = response.heuristic_risk_level ?? "--";
    $("riskScore").textContent = response.heuristic_score ?? "--";
    $("flowiseUsed").textContent = response.flowise_used ? "Yes" : "No";
    $("assessmentOutput").textContent = `${response.answer}${formatCitations(response.citations)}\n\nProvider: ${
      response.llm_provider_used || "unknown"
    } / ${response.llm_model_used || "unknown"}`;
    speakBritish(spokenAnswerText(response.answer), "credit");
  } catch (error) {
    $("assessmentOutput").textContent = `Credit assessment failed: ${error.message}`;
  }
  renderStagePages();
}

function renderLoanPolicyResult(result) {
  const target = $("loanPolicyResult");
  if (!target || !result) return;
  const reasonCodes = result.policy.reason_codes?.length ? result.policy.reason_codes.join(", ") : "None";
  target.innerHTML = `
    <div class="policy-tile">
      <strong>Repayment Capacity</strong>
      <span>DTI: ${result.dti.value_pct ?? "--"}%</span>
      <small>${htmlEscape(result.dti.band)} - ${htmlEscape(result.dti.assessment)}</small>
    </div>
    <div class="policy-tile">
      <strong>Collateral Coverage</strong>
      <span>LTV: ${result.ltv.value_pct ?? "--"}%</span>
      <small>${htmlEscape(result.ltv.band)} - ${htmlEscape(result.ltv.assessment)}. Collateral is backup protection, not the primary approval reason.</small>
    </div>
    <div class="policy-tile">
      <strong>Interest Rate</strong>
      <span>${result.interest.estimated_annual_rate_pct}% annual</span>
      <small>Base ${result.interest.base_rate_pct}% + spread ${result.interest.risk_spread_pct}%. Monthly payment ${Number(
    result.interest.estimated_monthly_payment || 0
  ).toLocaleString(undefined, { maximumFractionDigits: 2 })}.</small>
    </div>
    <div class="policy-tile">
      <strong>Recommendation</strong>
      <span>${htmlEscape(result.policy.recommendation)}</span>
      <small>Committee required: ${result.policy.committee_required ? "Yes" : "No"}. Reason codes: ${htmlEscape(reasonCodes)}. Human credit officer review required.</small>
    </div>`;
}

async function calculateLoanPolicyScore() {
  const customerId = selectedCustomerId();
  const status = $("policyWorkflowStatus");
  if (!customerId) {
    if (status) status.textContent = "Create or select a customer first.";
    return;
  }
  if (status) status.textContent = "Calculating DTI, LTV, pricing, fraud escalation, and recommendation...";
  try {
    const response = await api("/loan-policy/score", {
      method: "POST",
      body: JSON.stringify({
        customer_id: String(customerId),
        loan_amount: numberValue("loanAmountInput"),
        collateral_value: numberValue("collateralValueInput"),
        monthly_income: numberValue("monthlyIncomeInput"),
        monthly_debt_payments: numberValue("monthlyDebtInput"),
        term_months: numberValue("termMonthsInput", 60),
        fraud_indicators: selectedValues("fraudIndicatorsInput"),
        missing_documents: selectedValues("missingDocumentsInput"),
      }),
    });
    state.loanPolicyScore = response;
    state.committeeCase = null;
    state.finalDecision = null;
    renderLoanPolicyResult(response);
    if ($("approvedAmountInput") && !Number($("approvedAmountInput").value)) $("approvedAmountInput").value = String(response.policy.recommendation === "Decline Recommended" ? 0 : numberValue("loanAmountInput"));
    if ($("approvedRateInput") && !Number($("approvedRateInput").value)) $("approvedRateInput").value = String(response.interest.estimated_annual_rate_pct || 0);
    if (status) status.textContent = `Policy score ${response.policy_score_id || ""}: ${response.policy.recommendation}. Human credit officer review required.`;
  } catch (error) {
    if (status) status.textContent = `Policy scoring failed: ${error.message}`;
  }
  renderStagePages();
}

function stagePolicySnapshot() {
  const score = state.loanPolicyScore;
  return {
    loanAmount: numberValue("loanAmountInput"),
    collateral: numberValue("collateralValueInput"),
    dti: score?.dti?.value_pct ?? "--",
    ltv: score?.ltv?.value_pct ?? "--",
    rate: score?.interest?.estimated_annual_rate_pct ?? numberValue("approvedRateInput"),
    recommendation: score?.policy?.recommendation || "Run loan policy scoring",
    committeeRequired: score ? (score.policy?.committee_required ? "Required" : "Optional") : "Not scored",
  };
}

function renderStagePages() {
  const customer = selectedCustomer();
  const policy = stagePolicySnapshot();
  const ingested = state.documents.filter((doc) => String(doc.status || "").toLowerCase() === "ingested").length;
  const uploaded = state.documents.length;
  const risk = $("riskLevel")?.textContent || "--";
  const score = $("riskScore")?.textContent || "--";
  const assessmentReady = ($("assessmentOutput")?.textContent || "").trim() && !($("assessmentOutput")?.textContent || "").includes("No assessment");

  if ($("committeePacket")) {
    $("committeePacket").innerHTML = `
      <div class="context-section">
        <h4>Committee Packet</h4>
        <div class="context-row"><span>Customer</span><strong>${htmlEscape(customer?.name || selectedCustomerLabel())}</strong></div>
        <div class="context-row"><span>Risk / score</span><strong>${htmlEscape(risk)} / ${htmlEscape(score)}</strong></div>
        <div class="context-row"><span>Policy recommendation</span><strong>${htmlEscape(policy.recommendation)}</strong></div>
        <div class="context-row"><span>Committee required</span><strong>${htmlEscape(policy.committeeRequired)}</strong></div>
        <div class="context-row"><span>Missing evidence</span><strong>${ingested ? "Check assessment output" : "RAG ingestion required"}</strong></div>
      </div>
      <div class="context-section">
        <h4>Packet Contents</h4>
        <div class="context-row"><span>Credit appraisal</span><strong>${assessmentReady ? "Available" : "Missing"}</strong></div>
        <div class="context-row"><span>Policy score</span><strong>${htmlEscape(policy.dti)}% DTI / ${htmlEscape(policy.ltv)}% LTV</strong></div>
        <div class="context-row"><span>Collateral coverage</span><strong>${stageMoney(policy.collateral)}</strong></div>
        <div class="context-row"><span>Committee case</span><strong>${htmlEscape(state.committeeCase?.committee_case_id || "Not submitted")}</strong></div>
      </div>`;
  }

  if ($("decisionPanel")) {
    $("decisionPanel").innerHTML = `
      <div class="context-section">
        <h4>Final Decision Record</h4>
        <div class="context-row"><span>Decision</span><strong>${htmlEscape(state.finalDecision?.decision || $("finalDecisionInput")?.value || "Human pending")}</strong></div>
        <div class="context-row"><span>Requested amount</span><strong>${stageMoney(policy.loanAmount)}</strong></div>
        <div class="context-row"><span>Estimated rate</span><strong>${htmlEscape(policy.rate || "--")}%</strong></div>
        <div class="context-row"><span>Policy result</span><strong>${htmlEscape(policy.recommendation)}</strong></div>
        <div class="context-row"><span>Final approver</span><strong>Authorized officer required</strong></div>
      </div>`;
  }

  if ($("decisionChecklist")) {
    $("decisionChecklist").innerHTML = checklistHtml([
      ["Credit appraisal reviewed", assessmentReady],
      ["RAG citations reviewed", ingested > 0],
      ["Policy score reviewed", Boolean(state.loanPolicyScore)],
      ["Committee status reviewed", Boolean(state.committeeCase)],
      ["No AI final approval", true],
      ["Human credit officer review required", true],
    ]);
  }

  if ($("emailDraftPanel")) {
    const subject = state.emailDraft?.subject || "Credit application review update";
    const body = state.emailDraft?.body || `Dear ${customer?.name || "Customer"}, your credit application is under review. A human credit officer will review the supporting documents, policy score, and collateral evidence before any final decision is communicated.`;
    $("emailDraftPanel").innerHTML = `
      <div class="context-section">
        <h4>Draft Customer Notification</h4>
        <div class="context-row"><span>Subject</span><strong>${htmlEscape(subject)}</strong></div>
        <div class="context-row"><span>Recipient</span><strong>${htmlEscape(customer?.name || "Selected customer")}</strong></div>
        <div class="context-row"><span>Status</span><strong>${state.emailDraft ? "Prepared draft" : "Draft only"}</strong></div>
      </div>
      <div class="context-section">
        <h4>Body Preview</h4>
        <p>${htmlEscape(body)}</p>
      </div>`;
  }

  renderReportsPanel();
}

function renderReportsPanel() {
  if (!$("reportsPanel")) return;
  const customer = selectedCustomer();
  const policy = stagePolicySnapshot();
  const ingested = state.documents.filter((doc) => String(doc.status || "").toLowerCase() === "ingested").length;
  $("reportsPanel").innerHTML = `
    <div class="activity-item">
      <div class="activity-icon">DO</div>
      <div><strong>Credit Portfolio Snapshot</strong><p>${state.customers.length} customers, ${state.documents.length} selected-customer documents, ${ingested} ingested.</p></div>
    </div>
    <div class="activity-item">
      <div class="activity-icon">CR</div>
      <div><strong>Credit Case Summary</strong><p>${htmlEscape(customer?.name || selectedCustomerLabel())}: ${htmlEscape(policy.recommendation)}. Committee case ${htmlEscape(state.committeeCase?.committee_case_id || "not submitted")}.</p></div>
    </div>
    <div class="activity-item">
      <div class="activity-icon">FD</div>
      <div><strong>Decision & Notification</strong><p>Final decision ${htmlEscape(state.finalDecision?.decision || "pending")}. Email draft ${state.emailDraft ? "prepared" : "not prepared"}.</p></div>
    </div>`;
}

function showAppView(viewName) {
  const normalized = viewName || "main";
  document.querySelectorAll(".app-view").forEach((view) => {
    view.classList.toggle("hidden", view.id !== `view-${normalized}`);
    view.classList.toggle("active", view.id === `view-${normalized}`);
  });
  document.querySelectorAll("[data-stage-action]").forEach((card) => {
    card.classList.toggle("active", card.dataset.stageAction === normalized);
  });
  renderStagePages();
  document.querySelector(".workspace")?.scrollTo({ top: 0, behavior: "smooth" });
}

async function submitApprovalCommittee() {
  const customerId = selectedCustomerId();
  const status = $("policyWorkflowStatus");
  if (!customerId || !state.loanPolicyScore) {
    if (status) status.textContent = "Calculate a loan policy score first.";
    return;
  }
  try {
    const response = await api("/approval-committee/submit", {
      method: "POST",
      body: JSON.stringify({
        customer_id: String(customerId),
        assessment_id: null,
        policy_score: state.loanPolicyScore,
        submitted_by: $("officerNameInput")?.value || "Credit Officer",
        notes: $("decisionNotesInput")?.value || "Submitted from HyperSpeed Credit Appraisal UI.",
      }),
    });
    state.committeeCase = response;
    setStageState("committee", "complete");
    if (status) status.textContent = `Committee case ${response.committee_case_id} submitted. Next step: ${response.next_step}.`;
    renderStagePages();
  } catch (error) {
    if (status) status.textContent = `Committee submission failed: ${error.message}`;
  }
}

async function recordFinalDecision() {
  const customerId = selectedCustomerId();
  const status = $("policyWorkflowStatus");
  if (!customerId || !state.committeeCase?.committee_case_id) {
    if (status) status.textContent = "Submit the case to Approval Committee before recording a final decision.";
    return;
  }
  try {
    const response = await api("/final-decision", {
      method: "POST",
      body: JSON.stringify({
        committee_case_id: state.committeeCase.committee_case_id,
        customer_id: String(customerId),
        decision: $("finalDecisionInput")?.value || "conditional",
        approved_amount: numberValue("approvedAmountInput"),
        approved_rate_pct: numberValue("approvedRateInput"),
        conditions: linesValue("decisionConditionsInput"),
        decision_by: $("officerNameInput")?.value || "Credit Officer",
        decision_notes: $("decisionNotesInput")?.value || "",
      }),
    });
    state.finalDecision = response;
    setStageState("final-decision", "complete");
    if (status) status.textContent = `${response.decision_id}: ${response.note}`;
    renderStagePages();
  } catch (error) {
    if (status) status.textContent = `Final decision failed: ${error.message}`;
  }
}

async function draftCustomerEmail() {
  const customerId = selectedCustomerId();
  const output = $("emailDraftOutput");
  if (!customerId) {
    if (output) output.textContent = "Create or select a customer first.";
    return;
  }
  const decision = $("finalDecisionInput")?.value || "conditional";
  try {
    const response = await api("/customer-decision-email/draft", {
      method: "POST",
      body: JSON.stringify({
        customer_id: String(customerId),
        customer_email: $("customerEmailInput")?.value || "customer@example.com",
        decision,
        approved_amount: numberValue("approvedAmountInput"),
        approved_rate_pct: numberValue("approvedRateInput"),
        conditions: linesValue("decisionConditionsInput"),
        reason_summary: state.loanPolicyScore?.policy?.recommendation || $("decisionNotesInput")?.value || "Credit appraisal completed.",
        officer_name: $("officerNameInput")?.value || "Credit Officer",
        decision_id: state.finalDecision?.decision_id || null,
      }),
    });
    state.emailDraft = response;
    setStageState("email-draft", "complete");
    if (output) {
      output.textContent = `Subject: ${response.subject}\n\n${response.body}\n\nSend allowed: ${response.send_allowed}\nRequires human approval: ${response.requires_human_approval}`;
    }
    renderStagePages();
  } catch (error) {
    if (output) output.textContent = `Email draft failed: ${error.message}`;
  }
}

function setStageState(action, status) {
  const card = document.querySelector(`[data-stage-action="${action}"]`);
  if (!card) return;
  card.classList.toggle("complete", status === "complete");
  card.classList.toggle("pending", status !== "complete");
  const badge = card.querySelector("em");
  if (badge) badge.textContent = status === "complete" ? "complete" : "pending";
}

function generatePortfolioReport() {
  const status = $("policyWorkflowStatus");
  const customerId = selectedCustomerId();
  const customer = state.customers.find((item) => String(item.id) === String(customerId));
  const policy = state.loanPolicyScore?.policy;
  const dti = state.loanPolicyScore?.dti?.value_pct;
  const ltv = state.loanPolicyScore?.ltv?.value_pct;
  const decision = state.finalDecision?.decision || $("finalDecisionInput")?.value || "pending";
  const documents = state.documents.length;

  if (!status) return;

  status.textContent = [
    "Portfolio summary report",
    "",
    `Customer: ${customer?.name || "No customer selected"}`,
    `Documents: ${documents}`,
    `Policy recommendation: ${policy?.recommendation || "Not calculated"}`,
    `DTI: ${dti ?? "--"}%`,
    `LTV: ${ltv ?? "--"}%`,
    `Committee case: ${state.committeeCase?.committee_case_id || "Not submitted"}`,
    `Final decision: ${decision}`,
    `Email draft: ${state.emailDraft?.subject ? "Prepared" : "Not prepared"}`,
    "",
    "Human credit officer review required before any customer-facing decision.",
  ].join("\n");
  setStageState("reports", "complete");
  renderReportsPanel();
}

function scrollToPolicyWorkflow() {
  $("policyWorkflowPanel")?.scrollIntoView({ behavior: "smooth", block: "start" });
}

function initStageCards() {
  document.querySelectorAll("[data-stage-action]").forEach((card) => {
    card.addEventListener("click", () => {
      showAppView(card.dataset.stageAction);
    });
  });
  document.querySelectorAll("[data-view-link]").forEach((button) => {
    button.addEventListener("click", () => showAppView(button.dataset.viewLink));
  });
  document.querySelectorAll("[data-credit-prompt]").forEach((button) => {
    button.addEventListener("click", () => {
      if ($("creditChatInput")) $("creditChatInput").value = button.dataset.creditPrompt || "";
      showAppView("main");
      $("creditChatInput")?.focus();
    });
  });
  $("stageCommitteeSubmitBtn")?.addEventListener("click", submitApprovalCommittee);
  $("stageFinalDecisionBtn")?.addEventListener("click", recordFinalDecision);
  $("stageEmailDraftBtn")?.addEventListener("click", draftCustomerEmail);
  $("stageReportBtn")?.addEventListener("click", generatePortfolioReport);
}

async function loadConnectorOptions() {
  const sourceSelect = $("sourceSelect");
  if (!sourceSelect) return;
  try {
    const payload = await api("/connectors/options");
    const options = Array.isArray(payload) ? payload : payload.connectors || [];
    state.connectorOptions = options;
    sourceSelect.innerHTML = options
      .map((opt) => `<option value="${htmlEscape(opt.value || opt.id)}">${htmlEscape(opt.label || opt.name || opt.value || opt.id)}</option>`)
      .join("");
    renderSourceMethod();
  } catch {
    sourceSelect.innerHTML = `<option value="manual_upload">Manual Upload</option>`;
    state.connectorOptions = [{ value: "manual_upload", label: "Manual Upload" }];
    renderSourceMethod();
  }
}

async function testConnector() {
  const status = $("documentStatus");
  const source = $("sourceSelect")?.value || "manual_upload";
  if (source === "manual_upload") {
    if (status) status.textContent = uploadScanSummary(scanUploadFiles());
    return;
  }
  try {
    const response = await api("/connectors/test", {
      method: "POST",
      body: JSON.stringify({ source_type: source, config: connectorConfig(source) }),
    });
    if (status) status.textContent = response.message || "Connector test complete.";
  } catch (error) {
    if (status) status.textContent = `Connector test failed: ${error.message}`;
  }
}

function fillProviderSelect() {
  const select = $("providerSelect");
  if (!select) return;
  const modelSelect = $("llmModelSelect");
  select.innerHTML = PROVIDERS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
  select.value = "local_mistral_ollama";
  if (modelSelect) {
    modelSelect.innerHTML = LOCAL_LLM_MODELS.map(([value, label]) => `<option value="${value}">${label}</option>`).join("");
    modelSelect.value = "gemma2:9b";
  }
  const badge = $("providerBadge");
  const refreshBadge = () => {
    const model = modelSelect?.value;
    const local = select.value === "local_mistral_ollama" || select.value === "ollama";
    if (modelSelect) modelSelect.disabled = !local;
    if (badge) badge.textContent = local ? `${select.value} / ${model}` : select.value;
  };
  select.addEventListener("change", refreshBadge);
  modelSelect?.addEventListener("change", refreshBadge);
  refreshBadge();
}

async function initMain() {
  initBritishVoice("main", "mainChatInput", "mainChatLog");
  $("refreshMainBtn")?.addEventListener("click", async () => {
    await refreshStatus();
    await loadCustomers();
    await loadDocuments(selectedCustomerId("mainCustomerSelect"));
  });
  $("mainCustomerSelect")?.addEventListener("change", () => loadDocuments(selectedCustomerId("mainCustomerSelect")));
  $("mainChatForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat({ inputId: "mainChatInput", logId: "mainChatLog", customerSelectId: "mainCustomerSelect", voicePrefix: "main" });
  });
  await refreshStatus();
  await loadCustomers();
  await loadDocuments(selectedCustomerId("mainCustomerSelect"));
}

async function initCredit() {
  initBritishVoice("credit", "creditChatInput", "creditChatLog");
  initCreditQuestionBank();
  initStageCards();
  fillProviderSelect();
  $("customerForm")?.addEventListener("submit", createCustomer);
  $("customerSelect")?.addEventListener("change", () => {
    state.sessionId = null;
    loadDocuments();
  });
  $("sourceSelect")?.addEventListener("change", renderSourceMethod);
  $("fileInput")?.addEventListener("change", showUploadScan);
  $("folderInput")?.addEventListener("change", showUploadScan);
  $("uploadBtn")?.addEventListener("click", uploadDocuments);
  $("ingestSelectedBtn")?.addEventListener("click", ingestSelectedDocument);
  $("recoverDocsBtn")?.addEventListener("click", recoverSavedDocuments);
  $("dedupeDocsBtn")?.addEventListener("click", deduplicateDocuments);
  $("reloadDocsBtn")?.addEventListener("click", () => loadDocuments());
  $("assessmentBtn")?.addEventListener("click", generateAssessment);
  $("loanPolicyBtn")?.addEventListener("click", calculateLoanPolicyScore);
  $("committeeSubmitBtn")?.addEventListener("click", submitApprovalCommittee);
  $("finalDecisionBtn")?.addEventListener("click", recordFinalDecision);
  $("emailDraftBtn")?.addEventListener("click", draftCustomerEmail);
  $("testConnectorBtn")?.addEventListener("click", testConnector);
  $("listConnectorDocsBtn")?.addEventListener("click", listConnectorDocuments);
  $("clearConnectorDocsBtn")?.addEventListener("click", () => {
    state.connectorDocuments = [];
    renderConnectorDocuments();
  });
  $("refreshCreditBtn")?.addEventListener("click", async () => {
    await refreshStatus();
    await loadCustomers();
    await loadDocuments();
  });
  $("creditChatForm")?.addEventListener("submit", (event) => {
    event.preventDefault();
    sendChat({ inputId: "creditChatInput", logId: "creditChatLog", customerSelectId: "customerSelect", voicePrefix: "credit" });
  });
  await refreshStatus();
  await loadConnectorOptions();
  await loadCustomers();
  await loadDocuments();
}

document.addEventListener("DOMContentLoaded", async () => {
  initTheme();
  try {
    if (document.body.dataset.page === "credit") await initCredit();
    else await initMain();
  } catch (error) {
    console.error(error);
  }
});
