/**
 * SmartPrep AI — Frontend JavaScript
 *
 * Responsibilities:
 *   - New plan form (dynamic subject/topic builder)
 *   - Schedule interactions (mark complete / incomplete)
 *   - Live progress bar updates without page reload
 *   - Toast notifications
 */

// ── Toast ──────────────────────────────────────────────────────────────────

let toastTimer = null;

function showToast(message, type = "default") {
  let toast = document.getElementById("toast");
  if (!toast) {
    toast = document.createElement("div");
    toast.id = "toast";
    toast.className = "toast";
    document.body.appendChild(toast);
  }

  toast.textContent = message;
  toast.className = `toast ${type}`;

  // Force reflow so the transition fires even on re-trigger
  void toast.offsetWidth;
  toast.classList.add("show");

  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove("show"), 3000);
}


// ── Mark slot complete / incomplete ───────────────────────────────────────

async function markSlot(slotId, newStatus, triggerBtn) {
  const card = document.getElementById(`slot-${slotId}`);
  if (!card) return;

  // Optimistic UI: disable button while request is in flight
  triggerBtn.disabled = true;
  triggerBtn.style.opacity = "0.5";

  try {
    const res = await fetch(`/slot/${slotId}/status`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: newStatus }),
    });

    if (!res.ok) {
      throw new Error(`Server error: ${res.status}`);
    }

    const data = await res.json();

    // Update card appearance
    card.className = `slot-card status-${newStatus}`;

    // Rebuild the slot actions based on new status
    const actionsDiv = card.querySelector(".slot-actions");
    actionsDiv.innerHTML = buildSlotActions(slotId, newStatus, card);

    // Update progress bars live
    if (data.stats) {
      refreshProgressUI(data.stats);
    }

    const messages = {
      complete: "✓ Session marked complete!",
      incomplete: "Session rescheduled to a future slot.",
      pending: "Marked as pending.",
    };
    showToast(messages[newStatus] || "Updated.", newStatus === "complete" ? "success" : "default");

  } catch (err) {
    console.error("Failed to update slot:", err);
    showToast("Couldn't update. Please try again.", "error");
    triggerBtn.disabled = false;
    triggerBtn.style.opacity = "1";
  }
}

function buildSlotActions(slotId, status, card) {
  // Figure out if this slot's date is today or past
  const dayGroup = card.closest(".day-group");
  const isPastOrToday = dayGroup
    ? dayGroup.classList.contains("day-today") || dayGroup.classList.contains("day-past")
    : false;

  if (status === "complete") {
    return `<button class="btn btn-sm btn-success-ghost"
              onclick="markSlot(${slotId}, 'pending', this)">✓ Done</button>`;
  }

  if (status === "incomplete") {
    return `
      <span class="badge-status incomplete">Rescheduled</span>
      <button class="btn btn-sm btn-primary"
              onclick="markSlot(${slotId}, 'complete', this)">Mark done</button>`;
  }

  // pending
  let html = `<button class="btn btn-sm btn-outline"
                onclick="markSlot(${slotId}, 'complete', this)">Mark done</button>`;
  if (isPastOrToday) {
    html += ` <button class="btn btn-sm btn-ghost"
                onclick="markSlot(${slotId}, 'incomplete', this)">Can't do it</button>`;
  }
  return html;
}


// ── Refresh progress bars with data from the API response ─────────────────

function refreshProgressUI(stats) {
  // Overall bar
  const overallPct = document.getElementById("overallPct");
  const overallBar = document.getElementById("overallBar");
  const overallSub = document.getElementById("overallSub");

  if (overallPct) overallPct.textContent = `${stats.overall_pct}%`;
  if (overallBar) overallBar.style.width = `${stats.overall_pct}%`;
  if (overallSub) overallSub.textContent = `${stats.completed} / ${stats.total_slots} sessions done`;

  // Per-subject bars
  if (stats.subjects) {
    stats.subjects.forEach(subj => {
      const pctEl  = document.querySelector(`[data-subj-pct="${subj.subject}"]`);
      const barEl  = document.querySelector(`[data-subj-bar="${subj.subject}"]`);
      const cntEl  = document.querySelector(`[data-subj-count="${subj.subject}"]`);

      if (pctEl)  pctEl.textContent  = `${subj.pct}%`;
      if (barEl)  barEl.style.width  = `${subj.pct}%`;
      if (cntEl)  cntEl.textContent  = `${subj.done}/${subj.total}`;
    });
  }
}


// ── New Plan Form ──────────────────────────────────────────────────────────

function initNewPlanForm() {
  const subjectsList   = document.getElementById("subjectsList");
  const addSubjectBtn  = document.getElementById("addSubjectBtn");
  const generateBtn    = document.getElementById("generateBtn");
  const formError      = document.getElementById("formError");

  if (!subjectsList) return; // Not on the new-plan page

  // Start with one subject block already open
  addSubjectBlock();

  addSubjectBtn.addEventListener("click", addSubjectBlock);
  generateBtn.addEventListener("click", handleGenerate);

  function addSubjectBlock() {
    const tpl = document.getElementById("subjectTemplate");
    const clone = tpl.content.cloneNode(true);
    const block = clone.querySelector(".subject-block");

    // Wire up "remove subject" button
    block.querySelector(".remove-subject-btn").addEventListener("click", () => {
      block.remove();
    });

    // Wire up "add topic" button
    block.querySelector(".add-topic-btn").addEventListener("click", () => {
      addTopicRow(block.querySelector(".topics-list"));
    });

    subjectsList.appendChild(block);

    // Add two starter topics automatically so it feels inviting
    const topicsList = block.querySelector(".topics-list");
    addTopicRow(topicsList);
    addTopicRow(topicsList);
  }

  function addTopicRow(topicsList) {
    const tpl = document.getElementById("topicTemplate");
    const clone = tpl.content.cloneNode(true);
    const row = clone.querySelector(".topic-row");

    row.querySelector(".remove-topic-btn").addEventListener("click", () => {
      row.remove();
    });

    topicsList.appendChild(row);

    // Focus the new input for quick keyboard entry
    row.querySelector(".topic-name-input").focus();
  }

  async function handleGenerate() {
    clearError();

    const name     = document.getElementById("planName").value.trim();
    const examDate = document.getElementById("examDate").value;

    if (!name) { showError("Please enter a plan name."); return; }
    if (!examDate) { showError("Please pick an exam date."); return; }

    // Collect subjects
    const subjects = [];
    const subjectBlocks = subjectsList.querySelectorAll(".subject-block");

    for (const block of subjectBlocks) {
      const subjectName = block.querySelector(".subject-name-input").value.trim();
      if (!subjectName) continue;

      const topics = [];
      for (const row of block.querySelectorAll(".topic-row")) {
        const topicName = row.querySelector(".topic-name-input").value.trim();
        const difficulty = row.querySelector(".topic-difficulty-select").value;
        if (topicName) topics.push({ name: topicName, difficulty });
      }

      if (topics.length > 0) {
        subjects.push({ name: subjectName, topics });
      }
    }

    if (subjects.length === 0) {
      showError("Add at least one subject with a topic.");
      return;
    }

    // Disable button and show loading state
    generateBtn.textContent = "Generating…";
    generateBtn.classList.add("loading");

    try {
      const res = await fetch("/plan/create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, exam_date: examDate, subjects }),
      });

      const data = await res.json();

      if (!res.ok) {
        showError(data.error || "Something went wrong.");
        return;
      }

      // Navigate to the new plan's dashboard
      window.location.href = `/plan/${data.plan_id}`;

    } catch (err) {
      console.error("Plan creation failed:", err);
      showError("Network error — please try again.");
    } finally {
      generateBtn.textContent = "⚡ Generate Schedule";
      generateBtn.classList.remove("loading");
    }
  }

  function showError(msg) {
    formError.textContent = msg;
    formError.style.display = "block";
    formError.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  function clearError() {
    formError.textContent = "";
    formError.style.display = "none";
  }
}
