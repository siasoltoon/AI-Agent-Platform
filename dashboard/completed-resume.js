(() => {
  "use strict";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));

  function resumeButton(taskId, compact = false) {
    return `<button class="secondary-btn" type="button" data-completed-resume="${escapeHtml(taskId)}" style="${compact ? "margin-inline-start:8px" : ""}">Resume</button>`;
  }

  function isCompleted(value) {
    return String(value ?? "").trim().toLowerCase() === "completed";
  }

  function injectResumeControls() {
    document.querySelectorAll("#app tr").forEach((row) => {
      const taskCell = row.querySelector("td[data-task]");
      if (!taskCell) return;
      const taskId = taskCell.dataset.task;
      if (!taskId || row.querySelector("[data-completed-resume]")) return;

      const statusCell = row.querySelector("td:nth-child(2)");
      if (!isCompleted(statusCell?.textContent)) return;

      const actionCell = row.querySelector("td:last-child");
      if (actionCell) actionCell.insertAdjacentHTML("beforeend", resumeButton(taskId, true));
    });

    const modal = document.querySelector("#app #modalBackdrop");
    if (!modal || modal.querySelector("[data-completed-resume]")) return;
    const taskIdMatch = modal.querySelector(".modal-head h3")?.textContent?.match(/Task\s+(.+)$/);
    const taskId = taskIdMatch?.[1]?.trim();
    const status = modal.querySelector(".detail label")?.parentElement?.textContent;
    const actions = modal.querySelector(".actions");
    if (taskId && isCompleted(status) && actions) {
      actions.insertAdjacentHTML("afterbegin", resumeButton(taskId));
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

  const app = document.getElementById("app");
  if (app) {
    const observer = new MutationObserver(injectResumeControls);
    observer.observe(app, { childList: true, subtree: true });
  }

  injectResumeControls();
  window.setInterval(injectResumeControls, 1000);
})();
