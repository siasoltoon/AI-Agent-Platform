import { useEffect, useRef, useState } from "react";
import { createTask, getTask, getTasks } from "../api/tasks";

const TERMINAL_STATUSES = new Set(["completed", "failed", "cancelled"]);

function statusLabel(status) {
  return {
    queued: "در صف",
    running: "در حال اجرا",
    completed: "تکمیل شد",
    failed: "ناموفق",
    cancelled: "لغو شد",
  }[status] || status;
}

export default function TaskPanel() {
  const [prompt, setPrompt] = useState("");
  const [task, setTask] = useState(null);
  const [tasks, setTasks] = useState([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const pollTimer = useRef(null);

  async function refreshTasks() {
    try {
      const payload = await getTasks();
      setTasks(Array.isArray(payload?.tasks) ? payload.tasks : []);
    } catch (err) {
      setError(err.message || "خطا در دریافت وضعیت Taskها");
    }
  }

  function stopPolling() {
    if (pollTimer.current) {
      clearTimeout(pollTimer.current);
      pollTimer.current = null;
    }
  }

  async function pollTask(taskId) {
    try {
      const current = await getTask(taskId);
      setTask(current);
      await refreshTasks();

      if (!TERMINAL_STATUSES.has(current.status)) {
        pollTimer.current = setTimeout(() => pollTask(taskId), 500);
        return;
      }

      setSubmitting(false);
    } catch (err) {
      setError(err.message || "خطا در دریافت وضعیت اجرای Task");
      setSubmitting(false);
    }
  }

  useEffect(() => {
    refreshTasks();
    return stopPolling;
  }, []);

  async function handleCreateTask(event) {
    event.preventDefault();
    const value = prompt.trim();
    if (!value || submitting) return;

    stopPolling();
    setSubmitting(true);
    setError("");

    try {
      const created = await createTask({ prompt: value });
      setTask(created);
      setPrompt("");
      await refreshTasks();

      if (created.id && !TERMINAL_STATUSES.has(created.status)) {
        pollTimer.current = setTimeout(() => pollTask(created.id), 250);
      } else {
        setSubmitting(false);
      }
    } catch (err) {
      setError(err.message || "ثبت Task ناموفق بود.");
      setSubmitting(false);
      await refreshTasks();
    }
  }

  return (
    <section className="task-panel">
      <h2>اجرای Task</h2>
      <p>Task ثبت می‌شود، سپس Agent آن را در Worker اجرا می‌کند و وضعیت واقعی به‌روزرسانی می‌شود.</p>

      <form onSubmit={handleCreateTask}>
        <textarea
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="مثلاً: یک فایل hello.txt بساز و داخل آن Hello World بنویس"
          rows={5}
          disabled={submitting}
        />
        <button type="submit" disabled={submitting || !prompt.trim()}>
          {submitting ? "در حال اجرای Agent..." : "اجرای Task"}
        </button>
      </form>

      {error && <div className="task-error">{error}</div>}

      {task && (
        <div className="task-result">
          <strong>وضعیت: {statusLabel(task.status)}</strong>
          <div>Task ID: {task.id || "—"}</div>
          {task.result && <pre>{JSON.stringify(task.result, null, 2)}</pre>}
          {task.error && <div>خطا: {task.error}</div>}
        </div>
      )}

      <div className="task-history">
        <div className="task-history-header">
          <strong>Taskهای اخیر</strong>
          <button type="button" onClick={refreshTasks}>بروزرسانی</button>
        </div>
        {tasks.length === 0 ? (
          <p>هنوز Taskای ثبت نشده است.</p>
        ) : (
          tasks.slice(0, 10).map((item) => (
            <div className="task-row" key={item.id}>
              <span>{item.prompt}</span>
              <b>{statusLabel(item.status)}</b>
            </div>
          ))
        )}
      </div>
    </section>
  );
}
