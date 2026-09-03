(() => {
  "use strict";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));

  const isCompleted = (value) => String(value ?? "").trim().toLowerCase() === "completed";

  function resumeButton(taskId) {
    return `<button class="secondary-btn completed-resume-btn" type="button" data-completed-resume="${escapeHtml(taskId)}" style="margin-inline-start:8px">Resume</button>`;
  }

  function injectResumeControls() {
    const rows = document.querySelectorAll("#app table tbody tr");
    rows.forEach((row) => {
      if (row.querySelector("[data-completed-resume], [data-resume-task]")) return;

      const taskCell = row.querySelector("td[data-task]");
      if (!taskCell) return;

      const statusText = row.querySelector("td:nth-child(2)")?.textContent || "";
      if (!isCompleted(statusText)) return;

      const taskId = taskCell.dataset.task;
      const actionCell = row.querySelector("td:last-child");
      if (taskId && actionCell) actionCell.insertAdjacentHTML("beforeend", resumeButton(taskId));
    });

    const modal = document.querySelector("#app #modalBackdrop");
    if (!modal || modal.querySelector("[data-completed-resume], [data-resume-task]")) return;

    const taskId = modal.querySelector(".modal-head h3")?.textContent?.match(/Task\s+(.+)$/)?.[1]?.trim();
    const statusText = modal.querySelector(".detail")?.textContent || "";
    const actions = modal.querySelector(".actions");
    if (taskId && isCompleted(statusText) && actions) {
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

  const observer = new MutationObserver(injectResumeControls);
  observer.observe(document.body, { childList: true, subtree: true });

  injectResumeControls();
  window.setInterval(injectResumeControls, 500);
})();