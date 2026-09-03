(() => {
  "use strict";

  const state = {
    route: location.hash.replace(/^#\/?/, "") || "overview",
    sidebarOpen: false,
    tasks: [],
    selectedTask: null,
    health: { live: null, ready: null, agent: null, workers: null },
    loading: false,
    error: null,
    taskStatus: "",
    taskSearch: "",
    toasts: [],
    modal: null,
    lastRefresh: null,
  };

  const routes = [
    ["overview", "⌂", "Overview"], ["tasks", "✓", "Tasks"], ["agents", "◈", "Agents"],
    ["workers", "▣", "Workers"], ["executions", "↻", "Executions"], ["logs", "≡", "Logs"],
    ["monitoring", "◉", "Monitoring"], ["models", "◇", "Models"], ["tools", "⚒", "Tools"],
    ["projects", "□", "Projects"], ["diagnostics", "⚕", "Diagnostics"], ["settings", "⚙", "Settings"],
  ];

  const $ = (selector) => document.querySelector(selector);
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>\"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
  const fmtDate = (ts) => ts ? new Date(Number(ts) * 1000).toLocaleString() : "—";
  const fmtDuration = (task) => {
    if (!task?.started_at) return "—";
    const end = task.completed_at || Date.now() / 1000;
    const seconds = Math.max(0, Number(end) - Number(task.started_at));
    return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
  };
  const statusClass = (status) => ({completed:"success",running:"success",queued:"warning",failed:"danger",cancelled:"neutral"}[String(status || "").toLowerCase()] || "neutral");
  const statusPill = (status) => `<span class="status-pill ${statusClass(status)}"><span class="dot ${statusClass(status) === "success" ? "ok" : statusClass(status) === "danger" ? "bad" : statusClass(status) === "warning" ? "warn" : ""}"></span>${escapeHtml(String(status || "UNKNOWN").toUpperCase())}</span>`;

  async function api(path, options = {}) {
    const response = await fetch(path, { headers: { "Content-Type": "application/json", ...(options.headers || {}) }, ...options });
    let payload = null; try { payload = await response.json(); } catch (_) {}
    if (!response.ok) {
      const detail = payload?.detail;
      const message = typeof detail === "string" ? detail : detail?.error || detail?.message || JSON.stringify(detail || payload || response.statusText);
      throw new Error(`HTTP ${response.status}: ${message}`);
    }
    return payload;
  }

  async function refreshCore() {
    state.loading = true;
    try {
      const [tasks, live, ready, agent, workers] = await Promise.allSettled([
        api("/tasks?limit=100"), api("/health/live"), api("/health/ready"), api("/agents/status"), api("/workers/")
      ]);
      state.tasks = tasks.status === "fulfilled" ? (tasks.value?.tasks || []) : [];
      state.health.live = live.status === "fulfilled" ? live.value : { status: "failed", error: live.reason?.message };
      state.health.ready = ready.status === "fulfilled" ? ready.value : { status: "failed", error: ready.reason?.message };
      state.health.agent = agent.status === "fulfilled" ? agent.value : { status: "offline", error: agent.reason?.message };
      state.health.workers = workers.status === "fulfilled" ? workers.value : { workers: [], error: workers.reason?.message };
      state.lastRefresh = Date.now();
      if (state.selectedTask) { const current = state.tasks.find((t) => t.id === state.selectedTask.id); if (current) state.selectedTask = current; }
      state.error = null;
    } catch (error) { state.error = error.message; }
    finally { state.loading = false; render(); }
  }

  function toast(message, kind = "success") {
    const id = Date.now() + Math.random(); state.toasts.push({ id, message, kind }); renderToasts();
    setTimeout(() => { state.toasts = state.toasts.filter((t) => t.id !== id); renderToasts(); }, 4500);
  }
  function renderToasts() { const host = $(".toast-stack"); if (host) host.innerHTML = state.toasts.map((t) => `<div class="toast ${t.kind}">${escapeHtml(t.message)}</div>`).join(""); }
  function nav() { return routes.map(([id, icon, label]) => `<button class="${state.route === id ? "active" : ""}" data-route="${id}" aria-current="${state.route === id ? "page" : "false"}"><span class="icon">${icon}</span><span>${label}</span></button>`).join(""); }
  function shell() {
    const route = routes.find((r) => r[0] === state.route) || routes[0];
    return `<div class="app"><aside class="sidebar ${state.sidebarOpen ? "open" : ""}"><div class="brand"><div class="brand-mark">AI</div><div><strong>AI Agent Platform</strong><span>Operations Control Center</span></div></div><nav class="nav" aria-label="Main navigation">${nav()}</nav><div class="sidebar-footer"><div class="connection"><div class="connection-row"><span>Backend</span>${healthBadge(state.health.ready?.status === "ready")}</div><div class="connection-row"><span>Agent Worker</span>${healthBadge(state.health.agent?.status === "ready")}</div><div class="connection-row"><span>Last refresh</span><span class="muted">${state.lastRefresh ? new Date(state.lastRefresh).toLocaleTimeString() : "—"}</span></div></div></div></aside><main class="main"><header class="topbar"><div class="topbar-title"><button class="icon-btn mobile-menu" id="mobileMenu" aria-label="باز کردن منو">☰</button><div><div class="page-title">${escapeHtml(route[2])}</div><div class="page-subtitle">AI Agent Platform / ${escapeHtml(route[2])}</div></div></div><div class="top-actions">${healthBadge(state.health.ready?.status === "ready", "SYSTEM")}<button class="icon-btn" id="refreshBtn" title="Refresh">↻</button></div></header><div class="content">${page()}</div></main><div class="toast-stack" aria-live="polite"></div>${state.modal ? modal() : ""}</div>`;
  }
  function healthBadge(ok, label="") { return `<span class="status-pill ${ok ? "success" : "danger"}"><span class="dot ${ok ? "ok" : "bad"}></span>${label ? label + " " : ""}${ok ? "ONLINE" : "OFFLINE"}</span>`; }
  function page() {
    if (state.route === "overview") return overview(); if (state.route === "tasks") return tasksPage();
    if (state.route === "agents") return resourcePage("Agents", "Agent runtime status", agentRows());
    if (state.route === "workers") return resourcePage("Workers", "Worker connectivity and capacity", workerRows());
    if (state.route === "executions") return executionsPage(); if (state.route === "logs") return unavailable("Live Logs", "No log API is currently exposed by the backend.");
    if (state.route === "monitoring") return monitoringPage(); if (state.route === "models") return unavailable("Models", "A model registry endpoint is not currently exposed.");
    if (state.route === "tools") return unavailable("Tools", "A tool-registry endpoint is not currently exposed.");
    if (state.route === "projects") return unavailable("Projects / Workspaces", "No project/workspace API is currently exposed.");
    if (state.route === "diagnostics") return diagnosticsPage(); if (state.route === "settings") return settingsPage(); return overview();
  }
  function overview() { const counts=countTasks(); const workers=Array.isArray(state.health.workers?.workers)?state.health.workers.workers:[]; const recent=[...state.tasks].sort((a,b)=>Number(b.created_at||0)-Number(a.created_at||0)).slice(0,8); const successRate=(counts.total-counts.failed)?Math.round((counts.completed/Math.max(1,counts.total))*100):0; return `<section class="hero"><div><h1>Command Center</h1><p>نمای زنده‌ی وضعیت واقعی Controller، Task Engine، Agent Runtime و Worker.</p></div><div class="actions"><button class="primary-btn" data-action="new-task">+ اجرای Task جدید</button></div></section><div class="grid kpis">${kpi("Total Tasks",counts.total,"از Task Store")}${kpi("Queued",counts.queued,"در صف")}${kpi("Running",counts.running,"در حال اجرا")}${kpi("Completed",counts.completed,`${successRate}% از کل`)}${kpi("Failed",counts.failed,"نیازمند بررسی")}</div><div class="grid two-col"><section class="card"><div class="card-head"><h2>System Health</h2><span>Backend source of truth</span></div><div class="card-body"><div class="health-grid">${healthItem("Controller",state.health.live?.status==="ok",state.health.live?.environment||"live probe")}${healthItem("Task Store",state.health.ready?.checks?.task_store==="ok",state.health.ready?.status||"unknown")}${healthItem("Agent Runtime",state.health.agent?.status==="ready",state.health.agent?.status||"unknown")}${healthItem("Workers",workers.length>0,workers.length?`${workers.length} registered`:"No worker data")}</div></div></section><section class="card"><div class="card-head"><h2>Live Activity</h2><span>derived from durable task state</span></div><div class="card-body"><div class="activity">${recent.length?recent.map(activityRow).join(""):`<div class="empty">هنوز فعالیتی ثبت نشده است.</div>`}</div></div></section></div>`; }
  function kpi(label,value,meta){return `<div class="card kpi"><div class="label">${label}</div><div class="value">${value}</div><div class="meta">${meta}</div></div>`;}
  function countTasks(){const c={total:state.tasks.length,queued:0,running:0,completed:0,failed:0,cancelled:0};state.tasks.forEach(t=>{if(c[t.status]!==undefined)c[t.status]++;});return c;}
  function healthItem(name,ok,detail){return `<div class="health-item"><strong><span class="dot ${ok?"ok":"bad"}"></span>${name}</strong><span>${escapeHtml(detail)}</span></div>`;}
  function activityRow(t){return `<div class="activity-row"><span class="dot ${statusClass(t.status)==="danger"?"bad":statusClass(t.status)==="success"?"ok":"warn"}"></span><div class="event"><strong>${escapeHtml(t.status||"Task update").toUpperCase()} · <span class="task-id">${escapeHtml(t.id)}</span></strong><small>${escapeHtml(t.prompt)}</small></div><time>${fmtDate(t.created_at)}</time></div>`;}
  function resourcePage(title,subtitle,body){return `<section class="hero"><div><h1>${title}</h1><p>${subtitle}</p></div></section><section class="card">${body}</section>`;}
  function agentRows(){const a=state.health.agent;return `<div class="card-body"><div class="detail-grid"><div class="detail"><label>Runtime</label><div>${statusPill(a?.status||"offline")}</div></div><div class="detail"><label>Worker</label><div>${a?.worker?escapeHtml(JSON.stringify(a.worker)):"No worker status reported"}</div></div></div></div>`;}
  function workerRows(){const workers=state.health.workers?.workers||[];if(!workers.length)return `<div class="empty">هیچ Worker ثبت‌شده‌ای از API دریافت نشد.</div>`;return `<div class="table-wrap"><table><thead><tr><th>Worker ID</th><th>Host</th><th>Status</th><th>Last heartbeat</th></tr></thead><tbody>${workers.map(w=>`<tr><td>${escapeHtml(w.worker_id||w.id||"—")}</td><td>${escapeHtml(w.host||w.ip||"—")}</td><td>${statusPill(w.status)}</td><td>${escapeHtml(w.last_heartbeat||"—")}</td></tr>`).join("")}</tbody></table></div>`;}

  function tasksPage(){ const filtered=state.tasks.filter(t=>`${t.id} ${t.prompt} ${t.model||""}`.toLowerCase().includes(state.taskSearch.toLowerCase())&&(!state.taskStatus||t.status===state.taskStatus)); return `<section class="hero"><div><h1>Task Management</h1><p>مدیریت Taskها با وضعیت و داده‌ی واقعی Task Store.</p></div><button class="primary-btn" data-action="new-task">+ New Task</button></section><section class="card"><div class="card-body"><div class="toolbar"><input class="field search" id="taskSearch" value="${escapeHtml(state.taskSearch)}" placeholder="Search task ID, prompt, model…" aria-label="Search tasks"/><select class="field" id="taskStatus"><option value="">All statuses</option>${["queued","running","completed","failed","cancelled"].map(s=>`<option value="${s}" ${state.taskStatus===s?"selected":""}>${s}</option>`).join("")}</select><button class="ghost-btn" data-action="new-task">Create Task</button></div>${state.loading?`<div class="loading">در حال دریافت Taskها…</div>`:filtered.length?`<div class="table-wrap"><table><thead><tr><th>Task</th><th>Status</th><th>Model</th><th>Created</th><th>Duration</th><th>Actions</th></tr></thead><tbody>${filtered.map(taskRow).join("")}</tbody></table></div>`:`<div class="empty">No tasks found.</div>`}</div></section>`; }
  function taskRow(t){ const resume=t.status==="completed"?`<button class="secondary-btn" data-resume-task="${escapeHtml(t.id)}">Resume</button>`:""; const retry=t.status==="failed"?`<button class="secondary-btn" data-retry-task="${escapeHtml(t.id)}">Retry</button>`:""; return `<tr><td class="clickable" data-task="${escapeHtml(t.id)}"><span class="task-id">${escapeHtml(t.id)}</span><div class="muted" style="font-size:9px;margin-top:4px;max-width:420px;overflow:hidden;text-overflow:ellipsis">${escapeHtml(t.prompt)}</div></td><td>${statusPill(t.status)}</td><td>${escapeHtml(t.model||"default")}</td><td>${fmtDate(t.created_at)}</td><td>${fmtDuration(t)}</td><td><div class="actions"><button class="ghost-btn" data-task="${escapeHtml(t.id)}">Details</button>${resume}${retry}</div></td></tr>`; }
  function executionsPage(){const rows=state.tasks.filter(t=>t.started_at).sort((a,b)=>Number(b.started_at)-Number(a.started_at));return `<section class="hero"><div><h1>Executions</h1><p>Execution history derived from Task Store records.</p></div></section><section class="card"><div class="table-wrap"><table><thead><tr><th>Task</th><th>Started</th><th>Completed</th><th>Duration</th><th>Result</th><th>Evidence</th></tr></thead><tbody>${rows.length?rows.map(t=>`<tr class="clickable" data-task="${escapeHtml(t.id)}"><td class="task-id">${escapeHtml(t.id)}</td><td>${fmtDate(t.started_at)}</td><td>${fmtDate(t.completed_at)}</td><td>${fmtDuration(t)}</td><td>${statusPill(t.status)}</td><td>${evidenceBadge(t)}</td></tr>`).join(""):`<tr><td colspan="6"><div class="empty">No executions recorded.</div></td></tr>`}</tbody></table></div></section>`;}
  function evidenceBadge(t){const verified=t?.result?.result?.execution_evidence?.verified??t?.result?.execution_evidence?.verified;return verified===true?statusPill("verified"):verified===false?statusPill("not verified"):"—";}
  function monitoringPage(){const c=countTasks();return `<section class="hero"><div><h1>System Monitoring</h1><p>Only signals actually exposed by the backend are shown.</p></div></section><div class="grid three-col">${resourceSummaryStatic("Backend",state.health.live?.status||"unknown")}${resourceSummaryStatic("Task Store",state.health.ready?.status||"unknown")}${resourceSummaryStatic("Queue",`${c.queued} queued / ${c.running} running`)}${resourceSummaryStatic("Agent Runtime",state.health.agent?.status||"unknown")}</div>`;}
  function resourceSummaryStatic(title,detail){return `<section class="card"><div class="card-head"><h2>${title}</h2><span>real data only</span></div><div class="card-body"><div class="notice"><strong>${escapeHtml(detail)}</strong>No synthetic metrics are generated.</div></div></section>`;}
  function diagnosticsPage(){const checks=[["Backend live",state.health.live?.status==="ok",state.health.live?.status],["Task Store",state.health.ready?.checks?.task_store==="ok",state.health.ready?.status],["Agent Runtime",state.health.agent?.status==="ready",state.health.agent?.status],["Worker API",state.health.workers&&!state.health.workers.error,state.health.workers?.error||"reachable"]];return `<section class="hero"><div><h1>Diagnostics</h1><p>Health checks are explicit; unavailable checks are not represented as passing.</p></div></section><section class="card"><div class="card-body"><div class="grid">${checks.map(([n,ok,d])=>`<div class="detail"><label>${n}</label><div>${ok===true?statusPill("pass"):ok===false?statusPill("fail"):statusPill("not exposed")} <span class="muted">${escapeHtml(d||"")}</span></div></div>`).join("")}</div></div></section>`;}
  function settingsPage(){return `<section class="hero"><div><h1>Settings</h1><p>Browser-local presentation preferences only.</p></div></section>`;}
  function unavailable(title,text){return `<section class="hero"><div><h1>${title}</h1><p>Backend contract status</p></div></section><section class="card"><div class="card-body"><div class="notice"><strong>Not currently exposed</strong>${escapeHtml(text)}</div></div></section>`;}
  function modal(){if(state.modal.type==="task")return taskModal();if(state.modal.type==="detail")return detailModal();return "";}
  function taskModal(){return `<div class="modal-backdrop" id="modalBackdrop"><div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h3>Create Task</h3><button class="icon-btn" data-action="close-modal">×</button></div><div class="modal-body"><form class="form" id="taskForm"><label for="prompt">Task prompt</label><textarea class="field" id="prompt" required maxlength="200000"></textarea><label for="model">Model (optional)</label><input class="field" id="model" maxlength="128"/><label for="timeout">Timeout seconds (optional)</label><input class="field" id="timeout" type="number" min="1" max="1800"/></form></div><div class="modal-foot"><button class="primary-btn" type="submit" form="taskForm">Queue Task</button><button class="ghost-btn" data-action="close-modal">Cancel</button></div></div></div>`;}
  function detailModal(){const t=state.selectedTask;if(!t)return "";const resume=t.status==="completed"?`<button class="secondary-btn" data-resume-task="${escapeHtml(t.id)}">Resume</button>`:"";const retry=t.status==="failed"?`<button class="secondary-btn" data-retry-task="${escapeHtml(t.id)}">Retry</button>`:"";return `<div class="modal-backdrop" id="modalBackdrop"><div class="modal" role="dialog" aria-modal="true"><div class="modal-head"><h3>Task ${escapeHtml(t.id)}</h3><button class="icon-btn" data-action="close-modal">×</button></div><div class="modal-body"><div class="detail-grid"><div class="detail"><label>Status</label><div>${statusPill(t.status)}</div></div><div class="detail"><label>Model</label><div>${escapeHtml(t.model||"default")}</div></div><div class="detail"><label>Created</label><div>${fmtDate(t.created_at)}</div></div><div class="detail"><label>Started</label><div>${fmtDate(t.started_at)}</div></div><div class="detail"><label>Completed</label><div>${fmtDate(t.completed_at)}</div></div></div><div style="margin-top:14px"><div class="muted">PROMPT</div><p style="font-size:12px;line-height:1.7">${escapeHtml(t.prompt)}</p></div>${t.error?`<div class="notice"><strong>Execution error</strong>${escapeHtml(t.error)}</div>`:""}<div style="margin-top:14px"><div class="muted">RESULT / EXECUTION RECORD</div><pre class="code">${escapeHtml(JSON.stringify(t.result,null,2))}</pre></div><div style="margin-top:14px" class="actions">${resume}${retry}<button class="danger-btn" data-action="cancel-task" data-id="${escapeHtml(t.id)}" ${["completed","failed","cancelled"].includes(t.status)?"disabled":""}>Cancel</button></div></div></div></div>`;}
  async function openTask(id){const local=state.tasks.find(t=>t.id===id);if(!local)return;try{state.selectedTask=await api(`/tasks/${encodeURIComponent(id)}`);}catch(_){state.selectedTask=local;}state.modal={type:"detail"};render();}
  async function createTask(event){event.preventDefault();const prompt=$("#prompt")?.value.trim();if(!prompt)return;const body={prompt};const model=$("#model")?.value.trim();const timeout=Number($("#timeout")?.value);if(model)body.model=model;if(timeout)body.timeout_seconds=timeout;try{const created=await api("/tasks/",{method:"POST",body:JSON.stringify(body)});state.modal=null;toast(`Task ${created.id} queued successfully.`);await refreshCore();state.route="tasks";location.hash="#tasks";render();}catch(error){toast(error.message,"error");}}
  async function cancelTask(id){try{await api(`/tasks/${encodeURIComponent(id)}/cancel`,{method:"POST"});toast("Task cancellation requested.");state.modal=null;await refreshCore();}catch(error){toast(error.message,"error");}}
  async function resumeTask(id){try{const task=await api(`/tasks/${encodeURIComponent(id)}/resume`,{method:"POST"});state.modal=null;toast(`Task ${task.id} resumed and queued.`);await refreshCore();}catch(error){toast(`Resume failed: ${error.message}`,"error");}}
  async function retryTask(id){try{const task=await api(`/tasks/${encodeURIComponent(id)}/retry`,{method:"POST"});state.modal=null;toast(`Task ${task.id} requeued.`);await refreshCore();}catch(error){toast(`Retry failed: ${error.message}`,"error");}}
  function render(){document.body.innerHTML=shell();bind();renderToasts();}
  function bind(){
    document.querySelectorAll("[data-route]").forEach(b=>b.addEventListener("click",()=>{state.route=b.dataset.route;state.sidebarOpen=false;location.hash="#"+state.route;render();}));
    $("#mobileMenu")?.addEventListener("click",()=>{state.sidebarOpen=!state.sidebarOpen;render();}); $("#refreshBtn")?.addEventListener("click",refreshCore);
    document.querySelectorAll("[data-action='new-task']").forEach(b=>b.addEventListener("click",()=>{state.modal={type:"task"};render();setTimeout(()=>$("#prompt")?.focus(),0);}));
    document.querySelectorAll("[data-action='close-modal']").forEach(b=>b.addEventListener("click",()=>{state.modal=null;render();})); $("#modalBackdrop")?.addEventListener("click",e=>{if(e.target.id==="modalBackdrop"){state.modal=null;render();}}); $("#taskForm")?.addEventListener("submit",createTask);
    $("#taskSearch")?.addEventListener("input",e=>{state.taskSearch=e.target.value;render();setTimeout(()=>{const el=$("#taskSearch");if(el){el.focus();el.setSelectionRange(el.value.length,el.value.length);}},0);}); $("#taskStatus")?.addEventListener("change",e=>{state.taskStatus=e.target.value;render();});
    document.querySelectorAll("[data-task]").forEach(el=>el.addEventListener("click",e=>{if(!e.target.closest("[data-resume-task],[data-retry-task]"))openTask(el.dataset.task);}));
    document.querySelectorAll("[data-action='cancel-task']").forEach(b=>b.addEventListener("click",()=>cancelTask(b.dataset.id)));
    document.querySelectorAll("[data-resume-task]").forEach(b=>b.addEventListener("click",()=>resumeTask(b.dataset.resumeTask)));
    document.querySelectorAll("[data-retry-task]").forEach(b=>b.addEventListener("click",()=>retryTask(b.dataset.retryTask)));
  }
  window.addEventListener("hashchange",()=>{state.route=location.hash.replace(/^#\/?/,"")||"overview";render();refreshCore();}); render(); refreshCore(); setInterval(refreshCore,10000);
})();
