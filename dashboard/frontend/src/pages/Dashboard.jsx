import TaskPanel from "../components/TaskPanel";
import AgentStatus from "../components/AgentStatus";
import WorkerStatus from "../components/WorkerStatus";
import LogViewer from "../components/LogViewer";
import "../styles/global.css";

export default function Dashboard() {
  return (
    <main className="dashboard-container">
      <header className="dashboard-header">
        <div>
          <h1>AI Agent Platform</h1>
          <p>Autonomous agent control center</p>
        </div>
        <div className="system-status">SYSTEM ONLINE</div>
      </header>

      <section className="dashboard-grid">
        <TaskPanel />
        <AgentStatus />
        <WorkerStatus />
        <LogViewer />
      </section>
    </main>
  );
}
