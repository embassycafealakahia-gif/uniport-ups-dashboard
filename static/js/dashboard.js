/**
 * UNIPORT Acceptance Checker Dashboard — Client Application
 * Handles live polling, batch controls, single lookups, table search/filters,
 * student clearance dossier modal, run history archiving, and filtered exports.
 */

// State
let currentPage = 1;
const pageSize = 50;
let searchQuery = "";
let statusFilter = "ALL";
let facultyFilter = "ALL";
let isRunning = false;
let isPaused = false;
let autoScroll = true;

// DOM Elements
const statusDot = document.getElementById("status-dot");
const statusLabel = document.getElementById("status-label");
const btnStart = document.getElementById("btn-start");
const btnPause = document.getElementById("btn-pause");
const btnStop = document.getElementById("btn-stop");
const btnReset = document.getElementById("btn-reset");

const kpiTotal = document.getElementById("kpi-total");
const kpiQueueStatus = document.getElementById("kpi-queue-status");
const kpiAdmitted = document.getElementById("kpi-admitted");
const kpiAccepted = document.getElementById("kpi-accepted");
const kpiNotAccepted = document.getElementById("kpi-not-accepted");
const kpiFailed = document.getElementById("kpi-failed");
const kpiSpeed = document.getElementById("kpi-speed");
const kpiEta = document.getElementById("kpi-eta");

const progressBarFill = document.getElementById("progress-bar-fill");
const progressPercentLabel = document.getElementById("progress-percent-label");
const progressCounts = document.getElementById("progress-counts");

const tableBody = document.getElementById("table-body");
const tableSearch = document.getElementById("table-search");
const selectStatus = document.getElementById("filter-status");
const selectFaculty = document.getElementById("filter-faculty");
const paginationInfo = document.getElementById("pagination-info");
const currentPageBadge = document.getElementById("current-page-badge");
const btnPrevPage = document.getElementById("btn-prev-page");
const btnNextPage = document.getElementById("btn-next-page");

const consoleBody = document.getElementById("console-body");
const autoScrollCheckbox = document.getElementById("auto-scroll-checkbox");
const btnClearLogs = document.getElementById("btn-clear-logs");

// Modals
const studentModal = document.getElementById("student-modal");
const studentModalBody = document.getElementById("student-modal-body");
const btnCloseStudentModal = document.getElementById("btn-close-student-modal");

const uploadModal = document.getElementById("upload-modal");
const btnOpenUpload = document.getElementById("btn-open-upload");
const btnCloseUploadModal = document.getElementById("btn-close-upload-modal");
const btnCancelUpload = document.getElementById("btn-cancel-upload");
const btnSubmitUpload = document.getElementById("btn-submit-upload");
const fileInput = document.getElementById("file-input");
const pasteInput = document.getElementById("paste-input");
const uploadDropzone = document.getElementById("upload-dropzone");
const replaceQueueCheckbox = document.getElementById("replace-queue-checkbox");

const settingsModal = document.getElementById("settings-modal");
const btnOpenSettings = document.getElementById("btn-open-settings");
const btnCloseSettingsModal = document.getElementById("btn-close-settings-modal");
const btnCancelSettings = document.getElementById("btn-cancel-settings");
const btnSaveSettings = document.getElementById("btn-save-settings");
const settingMinDelay = document.getElementById("setting-min-delay");
const settingMaxDelay = document.getElementById("setting-max-delay");

const lookupForm = document.getElementById("lookup-form");
const singleRegInput = document.getElementById("single-reg-input");
const btnSingleLookup = document.getElementById("btn-single-lookup");

// History Modal
const historyModal = document.getElementById("history-modal");
const btnOpenHistory = document.getElementById("btn-open-history");
const btnCloseHistoryModal = document.getElementById("btn-close-history-modal");
const btnCloseHistory = document.getElementById("btn-close-history");
const historyList = document.getElementById("history-list");
const historyCountBadge = document.getElementById("history-count-badge");

// Export Controls
const btnExportMenu = document.getElementById("btn-export-menu");
const exportDropdownContent = document.getElementById("export-dropdown-content");
const exportFilteredCsv = document.getElementById("export-filtered-csv");
const exportFilteredJson = document.getElementById("export-filtered-json");
const btnQuickDownloadFiltered = document.getElementById("btn-quick-download-filtered");

// --- Initialization ---------------------------------------------------------
document.addEventListener("DOMContentLoaded", () => {
  setupEventListeners();
  fetchStats();
  fetchLogs();
  fetchResults();
  fetchHistoryCount();

  // Background polling loop
  setInterval(() => {
    fetchStats();
    fetchLogs();
    if (isRunning) {
      fetchResults();
    }
  }, 1200);
});

function setupEventListeners() {
  // Batch controls
  btnStart.addEventListener("click", handleStart);
  btnPause.addEventListener("click", handlePause);
  btnStop.addEventListener("click", handleStop);
  btnReset.addEventListener("click", handleReset);

  // Single lookup
  lookupForm.addEventListener("submit", handleSingleLookup);

  // Search & Filter
  let debounceTimeout = null;
  tableSearch.addEventListener("input", (e) => {
    clearTimeout(debounceTimeout);
    debounceTimeout = setTimeout(() => {
      searchQuery = e.target.value;
      currentPage = 1;
      fetchResults();
    }, 250);
  });

  selectStatus.addEventListener("change", (e) => {
    statusFilter = e.target.value;
    currentPage = 1;
    fetchResults();
  });

  selectFaculty.addEventListener("change", (e) => {
    facultyFilter = e.target.value;
    currentPage = 1;
    fetchResults();
  });

  // Filtered Downloads
  exportFilteredCsv.addEventListener("click", (e) => {
    e.preventDefault();
    triggerFilteredDownload("csv");
  });

  exportFilteredJson.addEventListener("click", (e) => {
    e.preventDefault();
    triggerFilteredDownload("json");
  });

  if (btnQuickDownloadFiltered) {
    btnQuickDownloadFiltered.addEventListener("click", () => {
      triggerFilteredDownload("csv");
    });
  }

  // Pagination
  btnPrevPage.addEventListener("click", () => {
    if (currentPage > 1) {
      currentPage--;
      fetchResults();
    }
  });

  btnNextPage.addEventListener("click", () => {
    currentPage++;
    fetchResults();
  });

  // Console
  autoScrollCheckbox.addEventListener("change", (e) => {
    autoScroll = e.target.checked;
  });

  btnClearLogs.addEventListener("click", () => {
    consoleBody.innerHTML = "";
  });

  // Export dropdown
  btnExportMenu.addEventListener("click", (e) => {
    e.stopPropagation();
    exportDropdownContent.classList.toggle("show");
  });

  window.addEventListener("click", () => {
    exportDropdownContent.classList.remove("show");
  });

  // History Modal
  btnOpenHistory.addEventListener("click", () => {
    loadHistoryModal();
    historyModal.classList.add("active");
  });
  btnCloseHistoryModal.addEventListener("click", () => historyModal.classList.remove("active"));
  btnCloseHistory.addEventListener("click", () => historyModal.classList.remove("active"));
  historyModal.addEventListener("click", (e) => {
    if (e.target === historyModal) historyModal.classList.remove("active");
  });

  // Upload Modal
  btnOpenUpload.addEventListener("click", () => uploadModal.classList.add("active"));
  btnCloseUploadModal.addEventListener("click", () => uploadModal.classList.remove("active"));
  btnCancelUpload.addEventListener("click", () => uploadModal.classList.remove("active"));
  uploadDropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", handleFileSelect);
  btnSubmitUpload.addEventListener("click", handleUploadSubmit);

  // Settings Modal
  btnOpenSettings.addEventListener("click", () => settingsModal.classList.add("active"));
  btnCloseSettingsModal.addEventListener("click", () => settingsModal.classList.remove("active"));
  btnCancelSettings.addEventListener("click", () => settingsModal.classList.remove("active"));
  btnSaveSettings.addEventListener("click", handleSaveSettings);

  // Student Detail Modal
  btnCloseStudentModal.addEventListener("click", () => studentModal.classList.remove("active"));
  studentModal.addEventListener("click", (e) => {
    if (e.target === studentModal) studentModal.classList.remove("active");
  });
}

function triggerFilteredDownload(format = "csv") {
  const url = `/api/export/${format}?search=${encodeURIComponent(searchQuery)}&status_filter=${statusFilter}&faculty_filter=${encodeURIComponent(facultyFilter)}&filtered_only=true`;
  window.location.href = url;
  showToast(`Downloading filtered ${format.toUpperCase()}...`, "info");
}

// --- Fetch Stats & Update UI ------------------------------------------------
async function fetchStats() {
  try {
    const res = await fetch("/api/stats");
    if (!res.ok) return;
    const data = await res.json();

    isRunning = data.is_running;
    isPaused = data.is_paused;

    if (isRunning) {
      if (isPaused) {
        statusDot.className = "pulse-dot paused";
        statusLabel.textContent = "PAUSED";
      } else {
        statusDot.className = "pulse-dot running";
        statusLabel.textContent = "CHECKING PORTAL";
      }
    } else {
      statusDot.className = "pulse-dot idle";
      statusLabel.textContent = "IDLE";
    }

    btnStart.disabled = isRunning && !isPaused;
    btnPause.disabled = !isRunning;
    btnPause.innerHTML = isPaused ? '<i class="ph ph-play"></i> Resume' : '<i class="ph ph-pause"></i> Pause';
    btnStop.disabled = !isRunning;

    kpiTotal.textContent = data.total_items.toLocaleString();
    kpiQueueStatus.textContent = `${data.checked.toLocaleString()} checked (${data.progress_percent}%)`;
    kpiAdmitted.textContent = data.admitted.toLocaleString();
    kpiAccepted.textContent = data.accepted.toLocaleString();
    kpiNotAccepted.textContent = data.not_accepted.toLocaleString();
    kpiFailed.textContent = data.failed_logins.toLocaleString();
    kpiSpeed.textContent = `${data.speed_per_min}/min`;

    if (isRunning && data.eta_seconds > 0) {
      const etaMin = Math.ceil(data.eta_seconds / 60);
      kpiEta.textContent = `ETA: ~${etaMin} min`;
    } else {
      kpiEta.textContent = isRunning ? "Calculating ETA..." : "ETA: --";
    }

    progressBarFill.style.width = `${data.progress_percent}%`;
    progressPercentLabel.textContent = `${data.progress_percent}%`;
    progressCounts.textContent = `${data.current_index.toLocaleString()} / ${data.total_items.toLocaleString()} items`;

  } catch (err) {
    console.error("Stats fetch error:", err);
  }
}

// --- Fetch Logs -------------------------------------------------------------
let lastLogCount = 0;
async function fetchLogs() {
  try {
    const res = await fetch("/api/logs");
    if (!res.ok) return;
    const data = await res.json();
    const logs = data.logs || [];

    if (logs.length === lastLogCount) return;
    lastLogCount = logs.length;

    consoleBody.innerHTML = "";
    logs.forEach((log) => {
      const entry = document.createElement("div");
      entry.className = `log-entry ${log.level.toLowerCase()}`;
      
      const timeSpan = document.createElement("span");
      timeSpan.className = "log-time";
      timeSpan.textContent = `[${log.timestamp}]`;

      const msgSpan = document.createElement("span");
      msgSpan.className = "log-msg";
      msgSpan.textContent = log.reg_number ? `[${log.reg_number}] ${log.message}` : log.message;

      entry.appendChild(timeSpan);
      entry.appendChild(msgSpan);
      consoleBody.appendChild(entry);
    });

    if (autoScroll) {
      consoleBody.scrollTop = consoleBody.scrollHeight;
    }
  } catch (err) {
    console.error("Logs fetch error:", err);
  }
}

// --- Fetch Results Table ----------------------------------------------------
async function fetchResults() {
  try {
    const url = `/api/results?search=${encodeURIComponent(searchQuery)}&status_filter=${statusFilter}&faculty_filter=${encodeURIComponent(facultyFilter)}&page=${currentPage}&page_size=${pageSize}`;
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();

    if (selectFaculty.options.length <= 1 && data.faculties && data.faculties.length > 0) {
      data.faculties.forEach((f) => {
        const opt = document.createElement("option");
        opt.value = f;
        opt.textContent = f;
        selectFaculty.appendChild(opt);
      });
    }

    renderTable(data.records);

    paginationInfo.textContent = `Showing ${(data.page - 1) * pageSize + (data.records.length > 0 ? 1 : 0)} - ${(data.page - 1) * pageSize + data.records.length} of ${data.total.toLocaleString()} records`;
    currentPageBadge.textContent = `Page ${data.page} of ${Math.max(1, data.total_pages)}`;
    btnPrevPage.disabled = data.page <= 1;
    btnNextPage.disabled = data.page >= data.total_pages;

  } catch (err) {
    console.error("Results fetch error:", err);
  }
}

function renderTable(records) {
  if (!records || records.length === 0) {
    tableBody.innerHTML = `
      <tr>
        <td colspan="7" class="empty-state">
          <i class="ph ph-tray empty-icon"></i>
          <div>No matching records found.</div>
        </td>
      </tr>
    `;
    return;
  }

  tableBody.innerHTML = "";
  records.forEach((r) => {
    const tr = document.createElement("tr");
    tr.style.cursor = "pointer";
    tr.addEventListener("click", () => openStudentDossier(r));

    const name = `${r.surname || ""} ${r.other_names || ""}`.trim() || (r.login_result === "LOGIN_FAILED" ? "Login Failed" : "Unknown");
    const photoUrl = r.photo_url || "https://ups.uniport.edu.ng/assets/images/logo1-thumb.png";

    let admBadge = '<span class="badge badge-failed"><i class="ph ph-x-circle"></i> Failed</span>';
    if (r.login_result === "SUCCESS") {
      if ((r.admission_status || "").toUpperCase().includes("ADMITTED")) {
        admBadge = '<span class="badge badge-admitted"><i class="ph ph-seal-check"></i> Admitted</span>';
      } else {
        admBadge = `<span class="badge badge-failed">${r.admission_status || "Not Admitted"}</span>`;
      }
    }

    let accBadge = '<span class="badge badge-failed">--</span>';
    if (r.login_result === "SUCCESS") {
      const acc = (r.acceptance_status || "").trim().toUpperCase();
      if (acc === "ACCEPTED") {
        accBadge = '<span class="badge badge-accepted"><i class="ph ph-check"></i> Accepted</span>';
      } else if (acc.includes("NOT ACCEPTED")) {
        accBadge = '<span class="badge badge-not-accepted"><i class="ph ph-clock"></i> Not Accepted</span>';
      } else {
        accBadge = `<span class="badge badge-not-accepted">${r.acceptance_status || "Pending"}</span>`;
      }
    }

    tr.innerHTML = `
      <td>
        <div class="student-col">
          <img src="${photoUrl}" class="student-avatar" onerror="this.src='https://ups.uniport.edu.ng/assets/images/logo1-thumb.png';">
          <div class="student-name-block">
            <span class="student-name">${escapeHtml(name)}</span>
            <span class="student-mode">${escapeHtml(r.admission_mode || "UTME")} • ${escapeHtml(r.program_type || "FULL-TIME")}</span>
          </div>
        </div>
      </td>
      <td><span class="reg-pill">${escapeHtml(r.reg_number || "")}</span></td>
      <td>
        <div class="dept-course">
          <span class="dept-name">${escapeHtml(r.course || r.department || "--")}</span>
          <span class="faculty-name">${escapeHtml(r.faculty || "--")}</span>
        </div>
      </td>
      <td><strong>${escapeHtml(r.utme_score || "--")}</strong></td>
      <td>${admBadge}</td>
      <td>${accBadge}</td>
      <td>
        <button class="btn btn-xs btn-secondary" title="View Full Dossier">
          <i class="ph ph-eye"></i> View
        </button>
      </td>
    `;
    tableBody.appendChild(tr);
  });
}

// --- Run History Management -------------------------------------------------
async function fetchHistoryCount() {
  try {
    const res = await fetch("/api/history");
    if (!res.ok) return;
    const data = await res.json();
    const count = data.runs ? data.runs.length : 0;
    if (historyCountBadge) {
      historyCountBadge.textContent = count;
    }
  } catch (err) {
    console.error("History count fetch error:", err);
  }
}

async function loadHistoryModal() {
  historyList.innerHTML = '<div style="text-align:center; padding:30px; color:var(--text-dim);"><i class="ph ph-spinner ph-spin" style="font-size:2rem;"></i><p style="margin-top:8px;">Loading archives...</p></div>';

  try {
    const res = await fetch("/api/history");
    const data = await res.json();
    const runs = data.runs || [];

    if (runs.length === 0) {
      historyList.innerHTML = `
        <div class="empty-state">
          <i class="ph ph-clock-counter-clockwise empty-icon"></i>
          <div>No historical runs saved yet. Runs are archived automatically when completed or reset.</div>
        </div>
      `;
      return;
    }

    historyList.innerHTML = "";
    runs.forEach((run) => {
      const card = document.createElement("div");
      card.className = "history-card";

      const stats = run.stats || {};
      const admitted = stats.admitted || 0;
      const accepted = stats.accepted || 0;
      const notAccepted = stats.not_accepted || 0;
      const failed = stats.failed_logins || 0;

      card.innerHTML = `
        <div class="history-info">
          <div class="history-title">${escapeHtml(run.label || run.run_id)}</div>
          <div class="history-date"><i class="ph ph-calendar-blank"></i> ${escapeHtml(run.saved_at || "Unknown Date")} • ${run.record_count} records (${run.queue_count} queue)</div>
          <div class="history-stats-pills">
            <span class="mini-stat-pill emerald">Admitted: ${admitted}</span>
            <span class="mini-stat-pill cyan">Accepted: ${accepted}</span>
            <span class="mini-stat-pill amber">Not Accepted: ${notAccepted}</span>
            <span class="mini-stat-pill rose">Failed: ${failed}</span>
          </div>
        </div>
        <div class="history-actions">
          <a href="/api/history/${run.run_id}/export/csv" class="btn btn-xs btn-secondary" title="Download CSV for this run">
            <i class="ph ph-file-csv"></i> CSV
          </a>
          <a href="/api/history/${run.run_id}/export/json" class="btn btn-xs btn-secondary" title="Download JSON for this run">
            <i class="ph ph-file-code"></i> JSON
          </a>
          <button class="btn btn-xs btn-primary btn-restore-run" data-run-id="${run.run_id}" title="Restore into active workspace to view or rerun">
            <i class="ph ph-arrow-counter-clockwise"></i> Load / Rerun
          </button>
          <button class="btn btn-xs btn-outline btn-delete-run" data-run-id="${run.run_id}" title="Delete snapshot">
            <i class="ph ph-trash"></i>
          </button>
        </div>
      `;

      card.querySelector(".btn-restore-run").addEventListener("click", () => handleRestoreRun(run.run_id));
      card.querySelector(".btn-delete-run").addEventListener("click", () => handleDeleteRun(run.run_id));

      historyList.appendChild(card);
    });

  } catch (err) {
    historyList.innerHTML = `<div class="empty-state" style="color:#fb7185;">Error loading history: ${escapeHtml(err.message)}</div>`;
  }
}

async function handleRestoreRun(runId) {
  if (!confirm(`Restore run ${runId} into active workspace? This will load all its registration numbers and verified records so you can view or rerun it.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/history/${runId}/restore`, { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast("Run restored into active workspace!", "success");
      historyModal.classList.remove("active");
      fetchStats();
      fetchResults();
      fetchHistoryCount();
    } else {
      showToast(data.detail || "Failed to restore run", "error");
    }
  } catch (err) {
    showToast(`Error restoring run: ${err.message}`, "error");
  }
}

async function handleDeleteRun(runId) {
  if (!confirm(`Delete historical snapshot ${runId}? This cannot be undone.`)) {
    return;
  }

  try {
    const res = await fetch(`/api/history/${runId}`, { method: "DELETE" });
    if (res.ok) {
      showToast("Snapshot deleted.", "info");
      loadHistoryModal();
      fetchHistoryCount();
    }
  } catch (err) {
    showToast(`Error deleting snapshot: ${err.message}`, "error");
  }
}

// --- Student Dossier Modal --------------------------------------------------
function openStudentDossier(data) {
  const photoUrl = data.photo_url || "https://ups.uniport.edu.ng/assets/images/logo1-thumb.png";
  const fullName = `${data.surname || ""} ${data.other_names || ""}`.trim() || data.reg_number;

  let admBadge = '<span class="badge badge-failed">Failed Login / No Record</span>';
  if (data.login_result === "SUCCESS") {
    admBadge = `<span class="badge badge-admitted">${data.admission_status || "ADMITTED"}</span>`;
  }

  let accBadge = '<span class="badge badge-failed">--</span>';
  if (data.login_result === "SUCCESS") {
    const acc = (data.acceptance_status || "").trim().toUpperCase();
    if (acc === "ACCEPTED") {
      accBadge = '<span class="badge badge-accepted">ACCEPTED OFFER</span>';
    } else {
      accBadge = '<span class="badge badge-not-accepted">NOT ACCEPTED</span>';
    }
  }

  studentModalBody.innerHTML = `
    <div class="student-dossier">
      <div class="dossier-photo-card">
        <div class="passport-frame">
          <img src="${photoUrl}" onerror="this.src='https://ups.uniport.edu.ng/assets/images/logo1-thumb.png';">
        </div>
        <div class="utme-score-badge">UTME Score: ${data.utme_score || "N/A"}</div>
        <div>${accBadge}</div>
      </div>

      <div class="dossier-grid">
        <div class="dossier-field full-span">
          <span class="dossier-label">Full Name (Surname First)</span>
          <span class="dossier-value">${escapeHtml(fullName)}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">JAMB Registration Number</span>
          <span class="dossier-value font-mono">${escapeHtml(data.reg_number || "--")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Portal User ID</span>
          <span class="dossier-value">${escapeHtml(data.user_id || "--")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Faculty</span>
          <span class="dossier-value">${escapeHtml(data.faculty || "--")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Department</span>
          <span class="dossier-value">${escapeHtml(data.department || "--")}</span>
        </div>

        <div class="dossier-field full-span">
          <span class="dossier-label">Degree Course</span>
          <span class="dossier-value">${escapeHtml(data.course || "--")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Degree Type</span>
          <span class="dossier-value">${escapeHtml(data.degree_type || "UNDER-GRADUATE")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Program Type</span>
          <span class="dossier-value">${escapeHtml(data.program_type || "FULL-TIME")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Admission Mode</span>
          <span class="dossier-value">${escapeHtml(data.admission_mode || "UTME")}</span>
        </div>

        <div class="dossier-field">
          <span class="dossier-label">Admission Status</span>
          <span class="dossier-value">${admBadge}</span>
        </div>

        ${data.error_message ? `
        <div class="dossier-field full-span" style="border-color: rgba(244,63,94,0.4);">
          <span class="dossier-label" style="color:#fb7185;">Notice / Status Reason</span>
          <span class="dossier-value" style="color:#fecdd3;">${escapeHtml(data.error_message)}</span>
        </div>` : ""}

        <div class="dossier-field full-span">
          <span class="dossier-label">Checked Timestamp</span>
          <span class="dossier-value" style="font-size:0.78rem; color:var(--text-dim);">${escapeHtml(data.timestamp || "--")}</span>
        </div>
      </div>
    </div>
  `;

  studentModal.classList.add("active");
}

// --- Single Lookup Handler --------------------------------------------------
async function handleSingleLookup(e) {
  e.preventDefault();
  const reg = singleRegInput.value.trim().toUpperCase();
  if (!reg) return;

  btnSingleLookup.disabled = true;
  btnSingleLookup.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Checking...';

  try {
    const res = await fetch("/api/check-single", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reg_number: reg }),
    });

    const data = await res.json();
    if (res.ok && data.data) {
      showToast("Student profile retrieved!", "success");
      openStudentDossier(data.data);
      fetchStats();
      fetchResults();
    } else {
      showToast(data.detail || "Lookup failed", "error");
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  } finally {
    btnSingleLookup.disabled = false;
    btnSingleLookup.innerHTML = '<i class="ph ph-arrow-right"></i> Check Now';
  }
}

// --- Batch Execution Controls -----------------------------------------------
async function handleStart() {
  try {
    const res = await fetch("/api/control/start", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast("Batch checker started!", "success");
      fetchStats();
    } else {
      showToast(data.detail || "Could not start checker", "error");
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  }
}

async function handlePause() {
  try {
    const res = await fetch("/api/control/pause", { method: "POST" });
    const data = await res.json();
    if (res.ok) {
      showToast(data.is_paused ? "Batch paused" : "Batch resumed", "info");
      fetchStats();
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  }
}

async function handleStop() {
  try {
    const res = await fetch("/api/control/stop", { method: "POST" });
    if (res.ok) {
      showToast("Stopping batch and archiving run...", "info");
      fetchStats();
      fetchHistoryCount();
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  }
}

async function handleReset() {
  if (!confirm("Are you sure you want to reset all current results? Previous results will be safely archived into Run History.")) {
    return;
  }
  try {
    const res = await fetch("/api/control/reset", { method: "POST" });
    if (res.ok) {
      showToast("Results archived to Run History and active queue reset.", "info");
      fetchStats();
      fetchResults();
      fetchHistoryCount();
    } else {
      const data = await res.json();
      showToast(data.detail || "Failed to reset", "error");
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  }
}

// --- Upload / Load Reg Numbers ----------------------------------------------
function handleFileSelect(e) {
  const file = e.target.files[0];
  if (!file) return;

  const reader = new FileReader();
  reader.onload = (event) => {
    pasteInput.value = event.target.result;
    showToast(`Loaded ${file.name} into input box`, "info");
  };
  reader.readAsText(file);
}

async function handleUploadSubmit() {
  const text = pasteInput.value.trim();
  if (!text) {
    showToast("Please paste or choose a file with registration numbers", "error");
    return;
  }

  const lines = text.split("\n");
  const replace = replaceQueueCheckbox.checked;

  btnSubmitUpload.disabled = true;
  btnSubmitUpload.innerHTML = '<i class="ph ph-spinner ph-spin"></i> Adding...';

  try {
    const res = await fetch("/api/upload-regs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ reg_numbers: lines, replace }),
    });

    const data = await res.json();
    if (res.ok) {
      showToast(`Queue updated! Total: ${data.count} items.`, "success");
      uploadModal.classList.remove("active");
      pasteInput.value = "";
      fileInput.value = "";
      fetchStats();
    } else {
      showToast(data.detail || "Upload error", "error");
    }
  } catch (err) {
    showToast(`Upload error: ${err.message}`, "error");
  } finally {
    btnSubmitUpload.disabled = false;
    btnSubmitUpload.innerHTML = '<i class="ph ph-check"></i> Add to Queue';
  }
}

// --- Settings Handler -------------------------------------------------------
async function handleSaveSettings() {
  const minDelay = parseFloat(settingMinDelay.value);
  const maxDelay = parseFloat(settingMaxDelay.value);

  if (isNaN(minDelay) || isNaN(maxDelay) || minDelay < 0.5 || maxDelay < minDelay) {
    showToast("Invalid delay values. Min must be >= 0.5 and Max >= Min.", "error");
    return;
  }

  try {
    const res = await fetch("/api/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ min_delay: minDelay, max_delay: maxDelay }),
    });
    if (res.ok) {
      showToast("Pacing settings saved!", "success");
      settingsModal.classList.remove("active");
    } else {
      const data = await res.json();
      showToast(data.detail || "Error saving settings", "error");
    }
  } catch (err) {
    showToast(`Network error: ${err.message}`, "error");
  }
}

// --- Utilities --------------------------------------------------------------
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  const toast = document.createElement("div");
  toast.className = `toast ${type}`;

  const iconName = type === "success" ? "check-circle" : type === "error" ? "warning-circle" : "info";
  toast.innerHTML = `<i class="ph ph-${iconName}" style="font-size:1.2rem;"></i> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateX(100%)";
    toast.style.transition = "all 0.3s ease";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
