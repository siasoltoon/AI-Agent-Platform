(() => {
  "use strict";

  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", "\"": "&quot;", "'": "&#39;"
  }[c]));

  async function loadCompleted() {
    const response = await fetch("/tasks?status=completed&limit=100", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return (await response.json()).tasks || [];
  }

  function mount() {
    const content = document.querySelector("#app .content");
    if (!content || location.hash.replace(/^#\/?/, "") !== "tasks") return;
    let panel = document.getElementById("completed-resume-panel");
    if (!panel) {
      content.insertAdjacentHTML("afterbegin", `
        <section class="card" id="completed-resume-panel" style="margin-bottom:16px">
          <div class="card-head"><h2>Completed Tasks</h2><span>Resume با همان Task ID و Mission Memory</span></div>
          <div class="card-body" id="completed-resume-body"><div class="empty">در حال دریافت Taskهای completed…</div></div>
        </section>`);
      panel = document.getElementById("completed-resume-panel");
      loadCompleted().then(render).catch((error) => renderError(error));
    }
  }

  function render(tasks) {
    const body = document.getElementById("completed-resume-body");
    if (!body) return;
    if (!tasks.length) {
      body.innerHTML = `<div class="empty">هیچ Task کاملی برای Resume وجود ندارد.</div>`;
      return;
    }
    body.innerHTML = `<div class="table-wrap"><table><thead><tr><th>Task ID</th><th>Prompt</th><th>Completed</th><th>Action</th></tr></thead><tbody>${tasks.map((task) => `
      <tr>
        <td><span class="task-id">${escapeHtml(task.id)}</span></td>
        <td>${escapeHtml(task.prompt)}</td>
        <td>${task.completed_at ? escapeHtml(new Date(Number(task.completed_at) * 1000).toLocaleString()) : "—"}</td>
        <td><button class="secondary-btn" data-completed-resume="${escapeHtml(task.id)}">Resume</button></td>
      </tr>`).join("")}</tbody></table></div>`;
  }

  function renderError(error) {
    const body = document.getElementById("completed-resume-body");
    if (body) body.innerHTML = `<div class="notice"><strong>خطا در دریافت Taskهای completed</strong>${escapeHtml(error.message)}</div>`;
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
        const panel = document.getElementById("completed-resume-panel");
        if (panel) panel.remove();
        mount();
      }, 350);
    } catch (error) {
      button.disabled = false;
      button.textContent = original;
      window.alert(`Resume failed: ${error.message}`);
    }
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-completed-resume]");
    if (!button) return;
    resume(button.dataset.completedResume, button);
  });

  const observer = new MutationObserver(() => mount());
  observer.observe(document.getElementById("app"), { childList: true, subtree: true });
  window.addEventListener("hashchange", () => {
    const panel = document.getElementById("completed-resume-panel");
    if (panel) panel.remove();
    mount();
  });
  mount();
})();
