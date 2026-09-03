(() => {
  "use strict";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));

  let completedIds = new Set();
  let loading = false;

  async function loadCompletedIds() {
    if (loading) return;
    loading = true;
    try {
      const response = await fetch("/tasks?status=completed&limit=100", { cache: "no-store" });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      completedIds = new Set((payload.tasks || []).map((task) => String(task.id)));
    } catch (_) {
      completedIds = new Set();
    } finally {
      loading = false;
      injectResumeControls();
    }
  }

  function resumeButton(taskId, compact = false) {
    return `<button class="secondary-btn" type="button" data-completed-resume="${escapeHtml(taskId)}" style="${compact ? "margin-inline-start:8px" : ""}">Resume</button>`;
  }

  function injectResumeControls() {
    if (location.hash.replace(/^#\/?/, "") !== "tasks") return;

    document.querySelectorAll("#app tr[data-task]").forEach((row) => {
      const taskId = row.dataset.task;
      if (!completedIds.has(String(taskId))) return;
      const actionCell = row.querySelector("td:last-child");
      if (!actionCell || actionCell.querySelector("[data-completed-resume]")) return;
      actionCell.insertAdjacentHTML("beforeend", resumeButton(taskId, true));
    });

    const modal = document.querySelector("#app #modalBackdrop");
    const modalTitle = document.querySelector("#app #detailTitle");
    if (modal && modalTitle) {
      const match = modalTitle.textContent.match(/Task\s+(.+)$/);
      const taskId = match?.[1]?.trim();
      if (taskId && completedIds.has(taskId) && !modal.querySelector("[data-completed-resume]")) {
        const actions = modal.querySelector(".actions");
        if (actions) actions.insertAdjacentHTML("afterbegin", resumeButton(taskId));
      }
    }
  }

  async function resume(taskId, button) {
    button.disabled = true;
    const original = button.textContent;
    button.textContent = "Resuming…";
    try {
      const response = await fetch(`/tasks/${encodeURIComponent(taskId)}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" }
      });
      let payload = null;
      try { payload = await response.json(); } catch (_) {}
      if (!response.ok) {
        const detail = payload?.detail;
        throw new Error(typeof detail === "string" ? detail : detail?.message || JSON.stringify(detail || payload));
      }

      button.textContent = "Queued";
      button.classList.add("success");
      completedIds.delete(String(taskId));

      window.setTimeout(() => {
        const refresh = document.getElementById("refreshBtn");
        if (refresh) refresh.click();
        const modalClose = document.querySelector("#modalBackdrop [data-action='close-modal']");
        if (modalClose) modalClose.click();
      }, 250);
    } catch (error) {
      button.disabled = false;
      button.textContent = original;
      window.alert(`Resume failed: ${error.message}`);
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-completed-resume]");
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    resume(button.dataset.completedResume, button);
  }, true);

  const observer = new MutationObserver(() => {
    injectResumeControls();
  });
  const app = document.getElementById("app");
  if (app) observer.observe(app, { childList: true, subtree: true });

  window.addEventListener("hashchange", () => {
    if (location.hash.replace(/^#\/?/, "") === "tasks") loadCompletedIds();
  });

  loadCompletedIds();
  window.setInterval(() => {
    if (location.hash.replace(/^#\/?/, "") === "tasks") loadCompletedIds();
  }, 5000);
})();
