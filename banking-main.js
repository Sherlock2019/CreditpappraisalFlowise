function serviceBase(storageKey, port, fallbackHost = "127.0.0.1") {
  const stored = localStorage.getItem(storageKey);
  if (stored && !stored.includes("backend") && !stored.includes("flowise")) return stored.replace(/\/$/, "");
  const host = window.location.hostname && window.location.hostname !== "0.0.0.0" ? window.location.hostname : fallbackHost;
  return `http://${host}:${port}`;
}

let API_BASE = window.location.origin && window.location.origin !== "null" ? `${window.location.origin}/api` : serviceBase("hyperspeed_api_base", 8000);

const state = {
  customers: [],
  documents: [],
  assets: [],
  chatSessionId: null,
  lastAssessment: null,
  lastChatAnswer: "",
  lastAiMeta: {
    provider: "local_mistral_ollama",
    model: "gemma2:9b",
    flowise: "Not used yet",
    citations: 0,
    fallback: "No",
  },
  activity: [
    { title: "Workflow opened", detail: "Banking cockpit ready for customer selection." },
  ],
};

const loanCase = {
  amount: 50000,
  purpose: "Working capital / credit appraisal",
  termMonths: 60,
  product: "Retail banking term loan",
  repaymentSource: "Operating cash flow",
  officer: "Credit Officer",
  status: "Appraisal in progress",
  monthlyIncome: 8000,
  monthlyDebt: 2200,
  defaultCollateralValue: 90000,
};

const $ = (id) => document.getElementById(id);
const money = (value) => `$${Number(value || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
const pct = (value) => `${Number(value || 0).toFixed(1).replace(".0", "")}%`;
const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char]));

function selectedModel() {
  const raw = $("topModelSelect")?.value || localStorage.getItem("docfactor_top_model") || "local_mistral_ollama|gemma2:9b";
  const [provider, model] = raw.split("|");
  return { provider: provider || "local_mistral_ollama", model: model || "gemma2:9b", raw };
}

function selectedModelPayload() {
  const model = selectedModel();
  return { llm_provider: model.provider, llm_model: model.model };
}

function syncModelBadge() {
  const model = selectedModel();
  if ($("mainProviderBadge")) $("mainProviderBadge").textContent = `${model.provider} / ${model.model}`;
}

function initTopModelSelect() {
  const select = $("topModelSelect");
  if (!select) return;
  const saved = localStorage.getItem("docfactor_top_model");
  if (saved && Array.from(select.options).some((option) => option.value === saved)) select.value = saved;
  syncModelBadge();
  select.addEventListener("change", () => {
    localStorage.setItem("docfactor_top_model", select.value);
    const model = selectedModel();
    state.lastAiMeta = { ...state.lastAiMeta, provider: model.provider, model: model.model };
    syncModelBadge();
    renderAuditAndMeta();
  });
}

function apiCandidates() {
  const sameOriginApi = window.location.origin && window.location.origin !== "null" ? `${window.location.origin}/api` : "";
  return [...new Set([API_BASE, sameOriginApi, serviceBase("hyperspeed_api_base", 8000), "http://127.0.0.1:8000", "http://localhost:8000"].filter(Boolean))];
}

async function api(path, options = {}) {
  const started = performance.now();
  let lastError = null;
  for (const base of apiCandidates()) {
    try {
      const response = await fetch(`${base}${path}`, {
        ...options,
        headers: options.body instanceof FormData ? options.headers || {} : { "Content-Type": "application/json", ...(options.headers || {}) },
      });
      $("statusLatency").textContent = `${Math.max(1, Math.round(performance.now() - started))}ms`;
      if (!response.ok) {
        let detail = response.statusText;
        try { detail = (await response.json()).detail || detail; } catch {}
        throw new Error(Array.isArray(detail) ? detail.map((d) => d.msg || JSON.stringify(d)).join("; ") : detail);
      }
      API_BASE = base;
      localStorage.setItem("hyperspeed_api_base", base);
      return response.json();
    } catch (error) {
      lastError = error;
    }
  }
  $("statusLatency").textContent = "offline";
  throw lastError || new Error("Backend unavailable");
}

function addActivity(title, detail) {
  state.activity.unshift({ title, detail });
  state.activity = state.activity.slice(0, 7);
  renderAuditAndMeta();
}

function spokenAnswerText(text) {
  return String(text || "")
    .replace(/\[[^\]]+\]\([^)]+\)/g, "")
    .replace(/[#*_`]/g, "")
    .replace(/\s+/g, " ")
    .trim();
}

function preferredBritishVoice(voices, gender) {
  const preferredNames = gender === "female"
    ? ["Microsoft Sonia Online", "Microsoft Libby Online", "Google UK English Female", "Sonia", "Libby", "Hazel"]
    : ["Microsoft Ryan Online", "Microsoft George Online", "Google UK English Male", "Daniel", "George", "Ryan"];
  for (const name of preferredNames) {
    const voice = voices.find((item) => item.name.toLowerCase().includes(name.toLowerCase()));
    if (voice) return voice;
  }
  return voices.find((voice) => voice.lang === "en-GB") || voices.find((voice) => voice.lang?.toLowerCase().startsWith("en")) || voices[0];
}

function mainVoiceGender() {
  return $("mainVoiceGender")?.value || localStorage.getItem("hyperspeed_british_voice_gender") || "female";
}

const LANGUAGE_LABELS = {
  "en-US": "English",
  "vi-VN": "Vietnamese",
  "ja-JP": "Japanese",
  "ko-KR": "Korean",
  "th-TH": "Thai",
  "zh-CN": "Chinese",
};

function selectedLanguage() {
  return $("mainLanguageSelect")?.value || localStorage.getItem("hyperspeed_lisa_language") || "en-US";
}

function selectedLanguageName() {
  return LANGUAGE_LABELS[selectedLanguage()] || "English";
}

const mainSpeechQueue = [];
let mainSpeechActive = false;

function processMainSpeechQueue() {
  if (mainSpeechActive || !mainSpeechQueue.length) return;
  const text = mainSpeechQueue.shift();
  const status = $("mainVoiceStatus");
  const gender = mainVoiceGender();
  const utterance = new SpeechSynthesisUtterance(text);
  utterance.lang = selectedLanguage() === "en-US" ? "en-GB" : selectedLanguage();
  utterance.rate = gender === "female" ? 0.98 : 0.96;
  utterance.pitch = gender === "female" ? 1.08 : 0.88;
  utterance.onend = () => {
    mainSpeechActive = false;
    processMainSpeechQueue();
  };
  utterance.onerror = () => {
    mainSpeechActive = false;
    processMainSpeechQueue();
  };

  const setVoiceAndSpeak = () => {
    const voices = window.speechSynthesis.getVoices();
    const voice = selectedLanguage() === "en-US"
      ? preferredBritishVoice(voices, gender)
      : voices.find((item) => item.lang === selectedLanguage()) || voices.find((item) => item.lang?.split("-")[0] === selectedLanguage().split("-")[0]);
    if (voice) utterance.voice = voice;
    if (status) status.textContent = voice ? `Speaking with ${voice.name}` : "Speaking with browser default voice.";
    mainSpeechActive = true;
    window.speechSynthesis.speak(utterance);
  };

  if (window.speechSynthesis.getVoices().length === 0) {
    window.speechSynthesis.addEventListener("voiceschanged", setVoiceAndSpeak, { once: true });
  } else {
    setVoiceAndSpeak();
  }
}

function speakMainChat(text) {
  if (!text) return;
  const status = $("mainVoiceStatus");
  const audioEnabled = $("mainAudioToggle")?.checked !== false;
  localStorage.setItem("mig_jarvis_voice", audioEnabled ? "true" : "false");
  localStorage.setItem("hyperspeed_british_voice_gender", mainVoiceGender());
  if (!audioEnabled) {
    if (status) status.textContent = "Audio is off.";
    return;
  }
  if (!("speechSynthesis" in window)) {
    if (status) status.textContent = "Speech synthesis is not supported in this browser.";
    return;
  }
  mainSpeechQueue.push(spokenAnswerText(text));
  processMainSpeechQueue();
}

function startMainChatDictation() {
  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const status = $("mainVoiceStatus");
  if (!SpeechRecognition) {
    if (status) status.textContent = "Speech recognition is not supported in this browser.";
    return;
  }
  const recognition = new SpeechRecognition();
  recognition.lang = selectedLanguage() === "en-US" ? "en-GB" : selectedLanguage();
  recognition.interimResults = false;
  recognition.maxAlternatives = 1;
  if (status) status.textContent = `Listening in ${selectedLanguageName()}...`;
  recognition.onresult = (event) => {
    const rawTranscript = event.results?.[0]?.[0]?.transcript || "";
    let transcript = rawTranscript.replace(/^ask\s+lisa[:,]?\s*/i, "").trim();
    const shouldSend = /\b(send|submit|ask now)\.?$/i.test(transcript);
    transcript = transcript.replace(/\b(send|submit|ask now)\.?$/i, "").trim();
    const input = $("mainBankChatInput");
    if (input) {
      input.value = transcript;
      input.focus();
    }
    if (status) status.textContent = shouldSend ? "Voice query captured. Sending..." : "Voice query captured. Review it, then send.";
    if (shouldSend && transcript) $("mainBankChatForm")?.requestSubmit();
  };
  recognition.onerror = (event) => {
    if (status) status.textContent = `Voice input failed: ${event.error || "unknown error"}`;
  };
  recognition.onend = () => {
    if (status?.textContent === `Listening in ${selectedLanguageName()}...`) status.textContent = "Voice input stopped.";
  };
  recognition.start();
}

function initMainChatVoice() {
  const audio = $("mainAudioToggle");
  const savedAudio = localStorage.getItem("mig_jarvis_voice");
  if (audio && savedAudio !== null) audio.checked = savedAudio !== "false";
  audio?.addEventListener("change", () => localStorage.setItem("mig_jarvis_voice", audio.checked ? "true" : "false"));

  const gender = $("mainVoiceGender");
  const savedGender = localStorage.getItem("hyperspeed_british_voice_gender");
  if (gender && (savedGender === "male" || savedGender === "female")) gender.value = savedGender;
  gender?.addEventListener("change", () => localStorage.setItem("hyperspeed_british_voice_gender", gender.value));

  const language = $("mainLanguageSelect");
  const savedLanguage = localStorage.getItem("hyperspeed_lisa_language");
  if (language && savedLanguage && LANGUAGE_LABELS[savedLanguage]) language.value = savedLanguage;
  language?.addEventListener("change", () => {
    localStorage.setItem("hyperspeed_lisa_language", language.value);
    if ($("mainVoiceStatus")) $("mainVoiceStatus").textContent = `Language set to ${selectedLanguageName()}.`;
  });

  const announceVoice = () => {
    const voices = window.speechSynthesis?.getVoices?.() || [];
    const voice = selectedLanguage() === "en-US"
      ? preferredBritishVoice(voices, mainVoiceGender())
      : voices.find((item) => item.lang === selectedLanguage()) || voices.find((item) => item.lang?.split("-")[0] === selectedLanguage().split("-")[0]);
    if ($("mainVoiceStatus") && voice) $("mainVoiceStatus").textContent = `Best ${selectedLanguageName()} voice found: ${voice.name}`;
  };
  if (window.speechSynthesis) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.addEventListener?.("voiceschanged", announceVoice);
    announceVoice();
  }
  $("mainVoiceBtn")?.addEventListener("click", startMainChatDictation);
  $("mainReadBtn")?.addEventListener("click", () => speakMainChat(state.lastChatAnswer || "No assistant answer is available to read yet."));
  $("mainTestVoiceBtn")?.addEventListener("click", () => speakMainChat("HYPERSPEED CREDIT LOAN OFFICER copilot is online. Human credit officer review is required."));
}

function switchView(view) {
  if (view === "appraisal") {
    window.location.href = "credit-appraisal.html";
    return;
  }
  const requestedView = view;
  const panelView = requestedView === "ask-lisa" ? "dashboard" : requestedView;
  const scrollTarget = requestedView === "ask-lisa" ? "askLisa" : null;
  document.querySelectorAll(".nav-item").forEach((item) => item.classList.toggle("active", item.dataset.view === requestedView));
  document.querySelectorAll(".view").forEach((panel) => panel.classList.toggle("active", panel.id === `view-${panelView}`));
  const titles = {
    dashboard: "HYPERSPEED CREDIT LOAN OFFICER",
    credit: "Credit Scoring Center",
    committee: "Approval Committee",
    decision: "Final Decision",
    email: "Customer Email Draft",
    asset: "Asset Appraisal Center",
    customer: "Customer Management",
    document: "Document Analysis Center",
    chat: "AI Chat Assistant",
    reports: "Reports & Analytics",
    "ask-lisa": "HYPERSPEED CREDIT LOAN OFFICER",
  };
  $("pageTitle").textContent = titles[requestedView] || titles.dashboard;
  history.replaceState(null, "", `#${requestedView}`);
  if (panelView === "asset") loadAssetAppraisals();
  renderCaseContext();
  if (scrollTarget) setTimeout(() => $(scrollTarget)?.scrollIntoView({ behavior: "smooth", block: "start" }), 50);
}

function fillSelect(selectId, selectedId) {
  const select = $(selectId);
  if (!select) return;
  const previous = selectedId || select.value || state.customers[0]?.id;
  select.innerHTML = state.customers.map((c) => `<option value="${c.id}">${c.id} - ${escapeHtml(c.name)}</option>`).join("");
  if (previous && state.customers.some((c) => String(c.id) === String(previous))) {
    select.value = String(previous);
  }
}

function selectedCustomerId(id = "creditCustomerSelect") {
  const select = $(id);
  return Number(select?.value || $("creditCustomerSelect")?.value || state.customers[0]?.id || 0);
}

function selectedCustomer(id = "creditCustomerSelect") {
  const customerId = selectedCustomerId(id);
  return state.customers.find((customer) => Number(customer.id) === customerId) || null;
}

function syncCustomerSelects(customerId) {
  for (const id of ["creditCustomerSelect", "assetCustomerSelect", "documentCustomerSelect", "mainChatCustomerSelect"]) {
    const select = $(id);
    if (select && customerId) select.value = String(customerId);
  }
}

function currentDocs() {
  return state.documents;
}

function currentAssets() {
  return state.assets;
}

function computePolicy() {
  const collateral = currentAssets().reduce((sum, asset) => sum + Number(asset.collateral_value || 0), 0) || loanCase.defaultCollateralValue;
  const dti = loanCase.monthlyIncome ? (loanCase.monthlyDebt / loanCase.monthlyIncome) * 100 : 0;
  const ltv = collateral ? (loanCase.amount / collateral) * 100 : 0;
  const rate = Math.max(6.5, 7.2 + Math.max(0, dti - 25) * 0.08 + Math.max(0, ltv - 70) * 0.05);
  const ingested = currentDocs().filter((doc) => doc.status === "ingested").length;
  const recommendation = !ingested
    ? "Documents required"
    : dti <= 40 && ltv <= 80
      ? "Conditionally acceptable"
      : "Committee review required";
  const committeeRequired = recommendation === "Conditionally acceptable" ? "Optional" : "Required";
  return { collateral, dti, ltv, rate, recommendation, committeeRequired };
}

function renderBars() {
  const values = [65, 82, 45, 90, 72, 58, 76];
  const days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  $("scoreBars").innerHTML = values.map((value, i) => `<div class="bar-wrap"><div class="bar" style="height:${value * 2.2}px"><strong>${value}</strong></div><span class="bar-label">${days[i]}</span></div>`).join("");
}

function renderCustomers() {
  const selected = $("creditCustomerSelect")?.value || state.customers[0]?.id;
  for (const id of ["creditCustomerSelect", "assetCustomerSelect", "documentCustomerSelect", "mainChatCustomerSelect"]) fillSelect(id, selected);
  $("dashCustomers").textContent = state.customers.length;
  $("customerList").innerHTML = state.customers.length
    ? state.customers.slice(0, 8).map((c) => `<div class="activity-item"><div class="activity-icon">CU</div><div><div class="activity-title">${escapeHtml(c.name)}</div><div class="activity-desc">${escapeHtml(c.customer_type || "customer")} | ${escapeHtml(c.industry || "No industry")} | ${escapeHtml(c.country || "No country")}</div></div><div class="activity-time">Active</div></div>`).join("")
    : `<p>No customers yet.</p>`;
  renderCreditAppraisalCaseFile();
}

function renderDocuments() {
  const ingested = currentDocs().filter((doc) => doc.status === "ingested").length;
  $("dashDocs").textContent = currentDocs().length;
  $("docTotal").textContent = currentDocs().length;
  $("docIngested").textContent = ingested;
  $("docPending").textContent = Math.max(0, currentDocs().length - ingested);
  $("documentList").innerHTML = currentDocs().length
    ? currentDocs().slice(0, 8).map((doc) => `<div class="activity-item"><div class="activity-icon">DO</div><div><div class="activity-title">${escapeHtml(doc.filename)}</div><div class="activity-desc">${escapeHtml(doc.document_type || "document")} | ${escapeHtml(doc.source_type || "manual")} | ${escapeHtml(doc.status)}</div></div><div class="activity-time">${doc.id}</div></div>`).join("")
    : `<p>No documents loaded. Use the upload form in this stage.</p>`;
  $("recentAssessments").innerHTML = currentDocs().length
    ? currentDocs().slice(0, 6).map((doc) => `<div class="activity-item"><div class="activity-icon">DO</div><div><div class="activity-title">${escapeHtml(doc.filename)}</div><div class="activity-desc">Ingestion status: ${escapeHtml(doc.status)} | Type: ${escapeHtml(doc.document_type || "document")}</div></div><div class="activity-time">${doc.id}</div></div>`).join("")
    : "<p>No document evidence for this customer yet.</p>";
  renderCreditAppraisalCaseFile();
}

function renderAssets(summary = null) {
  const total = summary?.total_appraised_value ?? currentAssets().reduce((sum, a) => sum + Number(a.appraised_value || 0), 0);
  const collateral = summary?.total_collateral_value ?? currentAssets().reduce((sum, a) => sum + Number(a.collateral_value || 0), 0);
  const byClass = summary?.by_class || currentAssets().reduce((acc, a) => ({ ...acc, [a.asset_class]: (acc[a.asset_class] || 0) + Number(a.appraised_value || 0) }), {});
  $("dashAssets").textContent = money(total);
  $("assetDonutValue").textContent = money(total);
  $("assetTotalValue").textContent = money(total);
  $("assetCollateralValue").textContent = money(collateral);
  $("assetCount").textContent = summary?.appraisal_count ?? currentAssets().length;
  $("assetLegend").innerHTML = Object.entries(byClass).map(([klass, value]) => `<span class="legend-item"><i class="legend-dot"></i>${escapeHtml(klass.replaceAll("_", " "))} (${money(value)})</span>`).join("") || `<span class="legend-item">No assets yet</span>`;
  $("assetClassSummary").innerHTML = Object.entries(byClass).map(([klass, value]) => `<div class="activity-item"><div class="activity-icon">AS</div><div><div class="activity-title">${escapeHtml(klass.replaceAll("_", " "))}</div><div class="activity-desc">${money(value)} appraised value</div></div><div class="activity-time">Class</div></div>`).join("") || "<p>No appraisals for this customer.</p>";
  $("assetRows").innerHTML = currentAssets().length
    ? currentAssets().map((a) => `<tr><td>${a.id}</td><td>${escapeHtml(a.asset_name)}</td><td>${escapeHtml(a.asset_class)}</td><td>${money(a.appraised_value)}</td><td>${money(a.collateral_value)}</td><td>${escapeHtml(a.status)}</td></tr>`).join("")
    : `<tr><td colspan="6">No asset appraisals for this customer.</td></tr>`;
  renderCreditAppraisalCaseFile();
}

function checklistHtml(items) {
  return items.map(([label, ok]) => `<div class="check-item ${ok ? "ok" : ""}"><span class="check-dot"></span><span>${escapeHtml(label)}</span></div>`).join("");
}

function renderWorkflow(stageData) {
  const steps = [
    { code: "DB", name: "Dashboard", detail: "Command center", done: true, view: "dashboard" },
    { code: "CU", name: "Customer Management", detail: stageData.hasCustomer ? "Customer profile selected" : "Create or select customer", done: stageData.hasCustomer, view: "customer" },
    { code: "DO", name: "Document Analysis", detail: `${stageData.uploaded} uploaded / ${stageData.ingested} ingested`, done: stageData.uploaded > 0, view: "document" },
    { code: "AS", name: "Asset Appraisal", detail: stageData.hasAssets ? `${money(stageData.policy.collateral)} eligible collateral` : "Capture collateral value", done: stageData.hasAssets, view: "asset" },
    { code: "$", name: "Credit Scoring", detail: stageData.policy.recommendation, done: stageData.hasCustomer && stageData.uploaded > 0, view: "credit", badge: "3" },
    { code: "CA", name: "Credit Appraisal", detail: state.lastAssessment ? "AI appraisal generated" : "Open full appraisal page", done: Boolean(state.lastAssessment), href: "credit-appraisal.html" },
    { code: "AI", name: "Ask LISA", detail: state.chatSessionId ? "Chat session active" : "Credit analyst assistant", done: Boolean(state.chatSessionId), view: "ask-lisa", badge: "New" },
    { code: "CM", name: "Committee", detail: stageData.policy.committeeRequired, done: stageData.policy.committeeRequired === "Required", view: "committee" },
    { code: "FD", name: "Final Decision", detail: "Human decision pending", done: false, view: "decision" },
    { code: "EM", name: "Email Draft", detail: "Customer notification pending", done: false, view: "email" },
    { code: "RP", name: "Reports", detail: "Portfolio summary", done: false, view: "reports" },
  ];
  $("workflowSteps").innerHTML = steps.map((step, index) => {
    const firstPending = steps.findIndex((item) => !item.done);
    const status = step.done ? "done" : index === firstPending ? "current" : "pending";
    const label = step.done ? "complete" : index === firstPending ? "active" : "pending";
    const attrs = step.href ? `href="${step.href}"` : `type="button" data-view="${step.view}" data-workflow-view="${step.view}"`;
    const tag = step.href ? "a" : "button";
    const badge = step.badge ? `<span class="workflow-badge">${escapeHtml(step.badge)}</span>` : "";
    const active = step.view && location.hash === `#${step.view}` ? " active" : "";
    return `<${tag} class="workflow-step nav-item ${status}${active}" ${attrs}><span class="workflow-code">${escapeHtml(step.code || `S${index + 1}`)}</span><div class="workflow-copy"><div class="workflow-kicker">Stage ${index + 1}</div><div class="workflow-name">${escapeHtml(step.name)}</div><div class="workflow-detail">${escapeHtml(step.detail)}</div><span class="workflow-status">${label}</span></div>${badge}</${tag}>`;
  }).join("");
}

function renderLoanAndPolicy(customer, stageData) {
  $("loanSummaryList").innerHTML = `
    <div class="context-section">
      <h4>Borrower</h4>
      <div class="context-row"><span>Name</span><strong>${escapeHtml(customer?.name || "No customer selected")}</strong></div>
      <div class="context-row"><span>Type</span><strong>${escapeHtml(customer?.customer_type || "--")}</strong></div>
      <div class="context-row"><span>Industry</span><strong>${escapeHtml(customer?.industry || "--")}</strong></div>
      <div class="context-row"><span>Country</span><strong>${escapeHtml(customer?.country || "--")}</strong></div>
    </div>
    <div class="context-section">
      <h4>Loan Application</h4>
      <div class="context-row"><span>Amount</span><strong>${money(loanCase.amount)}</strong></div>
      <div class="context-row"><span>Purpose</span><strong>${escapeHtml(loanCase.purpose)}</strong></div>
      <div class="context-row"><span>Term</span><strong>${loanCase.termMonths} months</strong></div>
      <div class="context-row"><span>Product</span><strong>${escapeHtml(loanCase.product)}</strong></div>
      <div class="context-row"><span>Repayment source</span><strong>${escapeHtml(loanCase.repaymentSource)}</strong></div>
      <div class="context-row"><span>Officer</span><strong>${escapeHtml(loanCase.officer)}</strong></div>
      <div class="context-row"><span>Status</span><strong>${escapeHtml(loanCase.status)}</strong></div>
    </div>`;
  $("policySummaryGrid").innerHTML = `
    <div class="policy-card"><span>DTI</span><strong>${pct(stageData.policy.dti)}</strong></div>
    <div class="policy-card"><span>LTV</span><strong>${pct(stageData.policy.ltv)}</strong></div>
    <div class="policy-card"><span>Estimated Rate</span><strong>${stageData.policy.rate.toFixed(2)}%</strong></div>
    <div class="policy-card"><span>Recommendation</span><strong>${escapeHtml(stageData.policy.recommendation)}</strong></div>
    <div class="policy-card"><span>Monthly Payment Source</span><strong>${escapeHtml(loanCase.repaymentSource)}</strong></div>
    <div class="policy-card"><span>Committee</span><strong>${escapeHtml(stageData.policy.committeeRequired)}</strong></div>`;
}

function renderStageInterfaces(customer, stageData) {
  if ($("stageAppraisalCustomer")) {
    $("stageAppraisalCustomer").textContent = customer?.name || "--";
    $("stageAppraisalCustomerMeta").textContent = customer ? `${customer.customer_type || "customer"} | ${customer.industry || "No industry"} | ${customer.country || "No country"}` : "Borrower profile";
    $("stageRagDatabase").textContent = stageData.ragReady ? "Ready" : "Not ready";
    $("stageLlmRouter").textContent = state.lastAiMeta.model || "gemma2:9b";
    $("stageAppraisalContext").innerHTML = `
      <div class="context-section">
        <h4>Stage Purpose</h4>
        <div class="context-row"><span>Input</span><strong>Customer, loan request, retrieved documents</strong></div>
        <div class="context-row"><span>Process</span><strong>Prompt + LLM credit appraisal</strong></div>
        <div class="context-row"><span>Output</span><strong>Risk, strengths, weaknesses, citations</strong></div>
      </div>
      <div class="context-section">
        <h4>Appraisal Inputs</h4>
        <div class="context-row"><span>Loan amount</span><strong>${money(loanCase.amount)}</strong></div>
        <div class="context-row"><span>Documents</span><strong>${stageData.uploaded} uploaded / ${stageData.ingested} ingested</strong></div>
        <div class="context-row"><span>Collateral</span><strong>${money(stageData.policy.collateral)}</strong></div>
        <div class="context-row"><span>Model</span><strong>${escapeHtml(state.lastAiMeta.provider)} / ${escapeHtml(state.lastAiMeta.model)}</strong></div>
      </div>`;
    $("stageEvidenceList").innerHTML = currentDocs().length
      ? currentDocs().map((doc) => `<div class="activity-item"><div class="activity-icon">DO</div><div><div class="activity-title">${escapeHtml(doc.filename)}</div><div class="activity-desc">${escapeHtml(doc.document_type || "document")} | ${escapeHtml(doc.status)} | citation source</div></div><div class="activity-time">${doc.id}</div></div>`).join("")
      : "<p>No evidence loaded yet. Use the Documents stage to upload and ingest files.</p>";
    $("stageAssessmentPreview").textContent = state.lastAssessment?.answer || "No credit appraisal generated yet. Use the stage button or ask the AI chat for a credit-risk summary with citations.";
  }

  if ($("committeePacket")) {
    $("committeePacket").innerHTML = `
      <div class="context-section">
        <h4>Committee Packet</h4>
        <div class="context-row"><span>Customer</span><strong>${escapeHtml(customer?.name || "--")}</strong></div>
        <div class="context-row"><span>Risk / score</span><strong>${escapeHtml(state.lastAssessment?.risk || "--")} / ${escapeHtml(state.lastAssessment?.score || "--")}</strong></div>
        <div class="context-row"><span>Policy recommendation</span><strong>${escapeHtml(stageData.policy.recommendation)}</strong></div>
        <div class="context-row"><span>Committee required</span><strong>${escapeHtml(stageData.policy.committeeRequired)}</strong></div>
        <div class="context-row"><span>Missing evidence</span><strong>${stageData.ragReady ? "Check assessment output" : "RAG ingestion required"}</strong></div>
      </div>
      <div class="context-section">
        <h4>Packet Contents</h4>
        <div class="context-row"><span>Credit appraisal</span><strong>${state.lastAssessment ? "Available" : "Missing"}</strong></div>
        <div class="context-row"><span>Policy score</span><strong>${pct(stageData.policy.dti)} DTI / ${pct(stageData.policy.ltv)} LTV</strong></div>
        <div class="context-row"><span>Collateral coverage</span><strong>${money(stageData.policy.collateral)}</strong></div>
        <div class="context-row"><span>Human officer</span><strong>${escapeHtml(loanCase.officer)}</strong></div>
      </div>`;
  }

  if ($("decisionPanel")) {
    $("decisionPanel").innerHTML = `
      <div class="context-section">
        <h4>Final Decision Record</h4>
        <div class="context-row"><span>Decision</span><strong>Human pending</strong></div>
        <div class="context-row"><span>Requested amount</span><strong>${money(loanCase.amount)}</strong></div>
        <div class="context-row"><span>Estimated rate</span><strong>${stageData.policy.rate.toFixed(2)}%</strong></div>
        <div class="context-row"><span>Policy result</span><strong>${escapeHtml(stageData.policy.recommendation)}</strong></div>
        <div class="context-row"><span>Final approver</span><strong>Authorized officer required</strong></div>
      </div>`;
    $("decisionChecklist").innerHTML = checklistHtml([
      ["Credit appraisal reviewed", Boolean(state.lastAssessment)],
      ["RAG citations reviewed", stageData.ragReady],
      ["Policy score reviewed", true],
      ["Committee status reviewed", stageData.policy.committeeRequired !== "--"],
      ["No AI final approval", true],
      ["Human credit officer review required", true],
    ]);
  }

  if ($("emailDraftPanel")) {
    $("emailDraftPanel").innerHTML = `
      <div class="context-section">
        <h4>Draft Customer Notification</h4>
        <div class="context-row"><span>Subject</span><strong>Credit application review update</strong></div>
        <div class="context-row"><span>Recipient</span><strong>${escapeHtml(customer?.name || "Selected customer")}</strong></div>
        <div class="context-row"><span>Status</span><strong>Draft only</strong></div>
      </div>
      <div class="context-section">
        <h4>Body Preview</h4>
        <p>Dear ${escapeHtml(customer?.name || "Customer")}, your credit application is under review. A human credit officer will review the supporting documents, policy score, and collateral evidence before any final decision is communicated.</p>
      </div>`;
  }
}

function renderCreditAppraisalCaseFile() {
  if (!$("appraisalBorrower")) return;
  const customer = selectedCustomer("creditCustomerSelect");
  const ingested = currentDocs().filter((doc) => doc.status === "ingested").length;
  const uploaded = currentDocs().length;
  const collateral = currentAssets().reduce((sum, asset) => sum + Number(asset.collateral_value || 0), 0);
  const hasFinancials = currentDocs().some((doc) => /financial|statement|xlsx|xls/i.test(`${doc.filename || ""} ${doc.document_type || ""}`));
  const hasPdf = currentDocs().some((doc) => /\.pdf$/i.test(doc.filename || ""));
  const hasAssets = collateral > 0;
  const ragReady = ingested > 0;
  const policy = computePolicy();
  const stage = state.lastAssessment ? "Credit assessment generated" : ragReady && hasAssets ? "Ready for appraisal" : uploaded ? "Evidence incomplete" : "Waiting for documents";
  const stageData = { hasCustomer: Boolean(customer), uploaded, ingested, ragReady, hasAssets, policy };

  $("appraisalBorrower").textContent = customer?.name || "--";
  $("appraisalBorrowerMeta").textContent = customer ? `${customer.customer_type || "customer"} | ${customer.industry || "No industry"} | ${customer.country || "No country"}` : "Select a customer";
  $("appraisalEvidence").textContent = `${uploaded}/${ingested}`;
  $("appraisalCollateral").textContent = money(collateral);
  $("appraisalStage").textContent = stage;
  $("creditCaseCustomer").textContent = customer?.name || "--";
  $("creditCaseMeta").textContent = customer ? `${customer.customer_type || "customer"} | ${customer.industry || "No industry"} | ${customer.country || "No country"}` : "Borrower profile";
  $("creditLoanAmount").textContent = money(loanCase.amount);
  $("creditLoanMeta").textContent = `${loanCase.product} | ${loanCase.termMonths} months`;
  $("creditRagStatus").textContent = `${uploaded} uploaded / ${ingested} ingested`;
  $("creditPolicyStatus").textContent = policy.recommendation;

  const checklist = [
    ["Customer profile selected", Boolean(customer)],
    ["Loan request captured", true],
    ["Documents uploaded", uploaded > 0],
    ["Documents ingested into RAG", ragReady],
    ["Financial statements available", hasFinancials],
    ["PDF evidence available", hasPdf],
    ["Asset collateral appraised", hasAssets],
    ["Policy scoring visible", true],
    ["Human review guardrail active", true],
  ];
  $("appraisalChecklistDashboard").innerHTML = checklistHtml(checklist);
  $("appraisalChecklistCredit").innerHTML = checklistHtml(checklist);
  renderWorkflow(stageData);
  renderLoanAndPolicy(customer, stageData);
  renderStageInterfaces(customer, stageData);
  renderCaseContext(stageData);
}

function renderCaseContext(stageData = null) {
  if (!$("chatCaseContext")) return;
  const customer = selectedCustomer("mainChatCustomerSelect") || selectedCustomer("creditCustomerSelect");
  const uploaded = currentDocs().length;
  const ingested = currentDocs().filter((doc) => doc.status === "ingested").length;
  const citations = ingested || state.lastAiMeta.citations || 0;
  const assetTotal = currentAssets().reduce((sum, asset) => sum + Number(asset.appraised_value || 0), 0);
  const collateral = currentAssets().reduce((sum, asset) => sum + Number(asset.collateral_value || 0), 0);
  const confidence = currentAssets().length ? Math.round(currentAssets().reduce((sum, asset) => sum + Number(asset.confidence_score || 0), 0) / currentAssets().length) : 0;
  const policy = stageData?.policy || computePolicy();
  const risk = state.lastAssessment?.risk || state.lastAssessment?.heuristic_risk_level || "--";
  const score = state.lastAssessment?.score || state.lastAssessment?.heuristic_score || "--";
  $("chatCaseContext").innerHTML = `
    <div class="context-section">
      <h4>Customer Context</h4>
      <div class="context-row"><span>Name</span><strong>${escapeHtml(customer?.name || "No customer selected")}</strong></div>
      <div class="context-row"><span>Type</span><strong>${escapeHtml(customer?.customer_type || "--")}</strong></div>
      <div class="context-row"><span>Industry</span><strong>${escapeHtml(customer?.industry || "--")}</strong></div>
      <div class="context-row"><span>Country</span><strong>${escapeHtml(customer?.country || "--")}</strong></div>
      <div class="context-row"><span>Risk / score</span><strong>${escapeHtml(risk)} / ${escapeHtml(score)}</strong></div>
    </div>
    <div class="context-section">
      <h4>Loan Request</h4>
      <div class="context-row"><span>Amount</span><strong>${money(loanCase.amount)}</strong></div>
      <div class="context-row"><span>Purpose</span><strong>${escapeHtml(loanCase.purpose)}</strong></div>
      <div class="context-row"><span>Term</span><strong>${loanCase.termMonths} months</strong></div>
      <div class="context-row"><span>Repayment</span><strong>${escapeHtml(loanCase.repaymentSource)}</strong></div>
      <div class="context-row"><span>Status</span><strong>${escapeHtml(loanCase.status)}</strong></div>
    </div>
    <div class="context-section">
      <h4>Document Evidence</h4>
      <div class="context-row"><span>Uploaded docs</span><strong>${uploaded}</strong></div>
      <div class="context-row"><span>Ingested docs</span><strong>${ingested}</strong></div>
      <div class="context-row"><span>Citations available</span><strong>${citations}</strong></div>
      <div class="context-row"><span>Missing docs</span><strong>${ingested ? "Review policy checklist" : "Ingest documents"}</strong></div>
    </div>
    <div class="context-section">
      <h4>Asset Collateral</h4>
      <div class="context-row"><span>Appraised value</span><strong>${money(assetTotal)}</strong></div>
      <div class="context-row"><span>Eligible value</span><strong>${money(collateral)}</strong></div>
      <div class="context-row"><span>Haircut source</span><strong>${currentAssets().length ? "Per asset" : "Not appraised"}</strong></div>
      <div class="context-row"><span>Confidence</span><strong>${confidence ? `${confidence}%` : "--"}</strong></div>
    </div>
    <div class="context-section">
      <h4>Policy + Decision</h4>
      <div class="context-row"><span>DTI</span><strong>${pct(policy.dti)}</strong></div>
      <div class="context-row"><span>LTV</span><strong>${pct(policy.ltv)}</strong></div>
      <div class="context-row"><span>Rate</span><strong>${policy.rate.toFixed(2)}%</strong></div>
      <div class="context-row"><span>Recommendation</span><strong>${escapeHtml(policy.recommendation)}</strong></div>
      <div class="context-row"><span>Committee</span><strong>${escapeHtml(policy.committeeRequired)}</strong></div>
      <div class="context-row"><span>Final decision</span><strong>Human pending</strong></div>
    </div>`;
  renderAuditAndMeta();
}

function renderAuditAndMeta() {
  if ($("auditPreview")) {
    $("auditPreview").innerHTML = state.activity.map((item) => `<div class="timeline-item"><div><strong>${escapeHtml(item.title)}</strong>${escapeHtml(item.detail)}</div></div>`).join("");
  }
  if ($("aiMetadata")) {
    $("aiMetadata").innerHTML = `
      <div class="meta-card"><span>Provider</span><strong>${escapeHtml(state.lastAiMeta.provider)}</strong></div>
      <div class="meta-card"><span>Model</span><strong>${escapeHtml(state.lastAiMeta.model)}</strong></div>
      <div class="meta-card"><span>Flowise used</span><strong>${escapeHtml(state.lastAiMeta.flowise)}</strong></div>
      <div class="meta-card"><span>Citations</span><strong>${state.lastAiMeta.citations}</strong></div>
      <div class="meta-card"><span>Fallback</span><strong>${escapeHtml(state.lastAiMeta.fallback)}</strong></div>
      <div class="meta-card"><span>Guardrail</span><strong>Human review</strong></div>`;
  }
}

async function loadCustomers() {
  state.customers = await api("/customers");
  renderCustomers();
}

async function loadDocuments() {
  const customerId = selectedCustomerId("creditCustomerSelect");
  state.documents = customerId ? await api(`/documents?customer_id=${customerId}`) : [];
  renderDocuments();
}

async function loadAssetAppraisals() {
  const customerId = selectedCustomerId("assetCustomerSelect");
  if (!customerId) {
    state.assets = [];
    renderAssets();
    return;
  }
  try {
    state.assets = await api(`/asset-appraisals?customer_id=${customerId}`);
    const summary = await api(`/asset-appraisals/summary/${customerId}`);
    renderAssets(summary);
    $("assetStatus").textContent = `Loaded ${state.assets.length} asset appraisal${state.assets.length === 1 ? "" : "s"} for customer ${customerId}.`;
  } catch (error) {
    $("assetStatus").textContent = `Asset appraisal API not ready: ${error.message}. Restart FastAPI after this update.`;
    state.assets = [];
    renderAssets();
  }
}

async function switchCustomer(customerId) {
  syncCustomerSelects(customerId);
  await loadDocuments();
  await loadAssetAppraisals();
  state.chatSessionId = null;
  addActivity("Customer context changed", `Loaded customer ${customerId} documents and collateral.`);
}

async function createCustomer(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const status = $("customerStatus");
  try {
    if (status) status.textContent = "Creating customer...";
    const created = await api("/customers", {
      method: "POST",
      body: JSON.stringify({
        name: $("mainCustomerName").value.trim(),
        customer_type: $("mainCustomerType").value.trim() || "business",
        industry: $("mainCustomerIndustry").value.trim() || null,
        country: $("mainCustomerCountry").value.trim() || null,
      }),
    });
    form.reset();
    $("mainCustomerType").value = "business";
    if (status) status.textContent = `Customer added: ${created.name || `ID ${created.id}`}.`;
    addActivity("Customer created", `${created.name || "New customer"} added to the appraisal workflow.`);
    await refreshAll(created.id);
  } catch (error) {
    if (status) status.textContent = `Add customer failed: ${error.message}`;
    addActivity("Customer create failed", error.message);
  }
}

async function uploadCockpitDocuments(event) {
  event.preventDefault();
  const status = $("documentUploadStatus");
  const files = Array.from($("documentFileInput")?.files || []);
  const customerId = selectedCustomerId("documentCustomerSelect");
  const documentType = $("documentTypeInput")?.value || "credit_document";
  const autoIngest = $("documentAutoIngest")?.checked !== false;
  if (!customerId) {
    if (status) status.textContent = "Select or add a customer before uploading.";
    return;
  }
  if (!files.length) {
    if (status) status.textContent = "Choose at least one PDF, DOCX, spreadsheet, CSV, or TXT file.";
    return;
  }
  try {
    const uploaded = [];
    for (let index = 0; index < files.length; index += 1) {
      const file = files[index];
      if (status) status.textContent = `Uploading ${index + 1}/${files.length}: ${file.name}`;
      const form = new FormData();
      form.append("customer_id", String(customerId));
      form.append("document_type", documentType);
      form.append("file", file, file.name);
      const document = await api("/documents/upload", { method: "POST", body: form });
      uploaded.push(document);
    }
    if (autoIngest) {
      let ingested = 0;
      for (let index = 0; index < uploaded.length; index += 1) {
        const document = uploaded[index];
        if (status) status.textContent = `Ingesting ${index + 1}/${uploaded.length}: ${document.filename}`;
        await api(`/ingest/${document.id}`, { method: "POST", body: JSON.stringify({}) });
        ingested += 1;
      }
      if (status) status.textContent = `Uploaded ${uploaded.length} and ingested ${ingested} document${ingested === 1 ? "" : "s"}.`;
    } else if (status) {
      status.textContent = `Uploaded ${uploaded.length} document${uploaded.length === 1 ? "" : "s"}.`;
    }
    $("documentUploadForm")?.reset();
    if ($("documentAutoIngest")) $("documentAutoIngest").checked = true;
    syncCustomerSelects(customerId);
    await loadDocuments();
    addActivity("Documents uploaded", `${uploaded.length} file${uploaded.length === 1 ? "" : "s"} added for customer ${customerId}.`);
  } catch (error) {
    if (status) status.textContent = `Upload failed: ${error.message}`;
    addActivity("Document upload failed", error.message);
  }
}

async function createAssetAppraisal(event) {
  event.preventDefault();
  const customerId = selectedCustomerId("assetCustomerSelect");
  const created = await api("/asset-appraisals", {
    method: "POST",
    body: JSON.stringify({
      customer_id: customerId,
      asset_name: $("assetNameInput").value.trim(),
      asset_class: $("assetClassInput").value,
      appraised_value: Number($("assetValueInput").value || 0),
      haircut_pct: Number($("assetHaircutInput").value || 0),
      confidence_score: Number($("assetConfidenceInput").value || 75),
      notes: $("assetNotesInput").value.trim() || null,
      status: "verified",
    }),
  });
  $("assetStatus").textContent = "Asset appraisal saved.";
  event.currentTarget.reset();
  $("assetValueInput").value = "250000";
  $("assetHaircutInput").value = "20";
  $("assetConfidenceInput").value = "80";
  addActivity("Asset appraisal saved", `${created.asset_name || "Collateral"} added with eligible value ${money(created.collateral_value)}.`);
  await loadAssetAppraisals();
}

async function generateCreditAssessment() {
  const customerId = selectedCustomerId("creditCustomerSelect");
  $("creditAssessmentPreview").textContent = "Generating assessment from RAG evidence...";
  try {
    const response = await api(`/credit-assessment/${customerId}`, { method: "POST", body: JSON.stringify(selectedModelPayload()) });
    state.lastAssessment = {
      score: response.heuristic_score ?? "--",
      risk: response.heuristic_risk_level || "Generated",
      answer: response.answer || "",
    };
    $("creditScoreValue").textContent = state.lastAssessment.score;
    $("creditRiskBadge").textContent = state.lastAssessment.risk;
    $("creditAssessmentPreview").textContent = state.lastAssessment.answer;
    $("dashAssessments").textContent = state.lastAssessment.score;
    addActivity("Credit assessment generated", `${state.lastAssessment.risk} risk with score ${state.lastAssessment.score}.`);
    renderCreditAppraisalCaseFile();
  } catch (error) {
    $("creditAssessmentPreview").textContent = `Credit assessment failed: ${error.message}`;
    addActivity("Credit assessment failed", error.message);
  }
}

async function sendChat(event) {
  event.preventDefault();
  const input = $("mainBankChatInput");
  const text = input.value.trim();
  if (!text) return;
  const log = $("mainBankChatMessages");
  log.insertAdjacentHTML("beforeend", `<div class="message user">${escapeHtml(text)}</div>`);
  input.value = "";
  speakMainChat(`Question asked: ${text}`);
  try {
    const model = selectedModelPayload();
    const localizedMessage = selectedLanguage() === "en-US"
      ? text
      : `Respond in ${selectedLanguageName()}. User question: ${text}`;
    const response = await api("/chat", {
      method: "POST",
      body: JSON.stringify({ customer_id: selectedCustomerId("mainChatCustomerSelect"), message: localizedMessage, session_id: state.chatSessionId, ...model }),
    });
    const citations = Array.isArray(response.citations) ? response.citations.length : Number(response.citations_count || 0);
    state.chatSessionId = response.session_id;
    state.lastAiMeta = {
      provider: response.llm_provider || response.provider || "local_mistral_ollama",
      model: response.llm_model || response.model || "gemma2:9b",
      flowise: response.flowise_used ? "Yes" : "No",
      citations,
      fallback: response.fallback_used ? "Yes" : "No",
    };
    state.lastChatAnswer = response.answer || "";
    if ($("mainProviderBadge")) $("mainProviderBadge").textContent = `${state.lastAiMeta.provider} / ${state.lastAiMeta.model}`;
    log.insertAdjacentHTML("beforeend", `<div class="message assistant">${escapeHtml(state.lastChatAnswer).replaceAll("\n", "<br>")}</div>`);
    speakMainChat(state.lastChatAnswer);
    addActivity("AI response generated", `${state.lastAiMeta.provider} / ${state.lastAiMeta.model}, ${citations} citation${citations === 1 ? "" : "s"}.`);
    renderCaseContext();
  } catch (error) {
    log.insertAdjacentHTML("beforeend", `<div class="message assistant">Chat failed: ${escapeHtml(error.message)}</div>`);
    state.lastAiMeta = { ...state.lastAiMeta, fallback: "Error" };
    addActivity("AI response failed", error.message);
  }
  log.scrollTop = log.scrollHeight;
}

async function refreshAll(preferredCustomerId = null) {
  try {
    await loadCustomers();
    syncCustomerSelects(preferredCustomerId || selectedCustomerId("creditCustomerSelect"));
    await loadDocuments();
    await loadAssetAppraisals();
    $("statusUptime").textContent = "99.9%";
  } catch (error) {
    $("statusUptime").textContent = "API offline";
    addActivity("Backend offline", error.message);
  }
}

function initParticles() {
  const container = $("particles");
  for (let i = 0; i < 18; i += 1) {
    const particle = document.createElement("div");
    particle.className = "particle";
    particle.style.left = `${Math.random() * 100}%`;
    particle.style.animationDuration = `${Math.random() * 10 + 10}s`;
    particle.style.animationDelay = `${Math.random() * 10}s`;
    container.appendChild(particle);
  }
}

document.addEventListener("DOMContentLoaded", async () => {
  initParticles();
  renderBars();
  initTopModelSelect();
  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.view)));
  document.querySelectorAll("[data-view-link]").forEach((button) => button.addEventListener("click", () => switchView(button.dataset.viewLink)));
  $("mainCustomerForm")?.addEventListener("submit", createCustomer);
  $("documentUploadForm")?.addEventListener("submit", uploadCockpitDocuments);
  $("assetForm")?.addEventListener("submit", createAssetAppraisal);
  $("assetCustomerSelect")?.addEventListener("change", (event) => switchCustomer(event.target.value));
  $("creditCustomerSelect")?.addEventListener("change", (event) => switchCustomer(event.target.value));
  $("documentCustomerSelect")?.addEventListener("change", (event) => switchCustomer(event.target.value));
  $("mainChatCustomerSelect")?.addEventListener("change", (event) => switchCustomer(event.target.value));
  $("refreshAssetsBtn")?.addEventListener("click", loadAssetAppraisals);
  $("generateCreditAssessmentBtn")?.addEventListener("click", generateCreditAssessment);
  $("stageGenerateAssessmentBtn")?.addEventListener("click", generateCreditAssessment);
  $("mainBankChatForm")?.addEventListener("submit", sendChat);
  initMainChatVoice();
  $("workflowSteps")?.addEventListener("click", (event) => {
    const button = event.target.closest("[data-workflow-view]");
    if (button) switchView(button.dataset.workflowView);
  });
  document.querySelectorAll("[data-quick]").forEach((button) => button.addEventListener("click", () => { $("mainBankChatInput").value = button.dataset.quick; }));
  document.querySelectorAll("[data-credit-prompt]").forEach((button) => button.addEventListener("click", () => {
    $("mainBankChatInput").value = button.dataset.creditPrompt;
    $("mainChatCustomerSelect").value = $("creditCustomerSelect").value;
    switchView("ask-lisa");
  }));
  await refreshAll();
  const initialView = (location.hash || "#dashboard").slice(1);
  switchView(initialView === "chat" ? "dashboard" : initialView);
});
