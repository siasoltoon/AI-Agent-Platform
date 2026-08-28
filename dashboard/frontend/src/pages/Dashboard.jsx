import TaskPanel from "../components/TaskPanel";
import AgentStatus from "../components/AgentStatus";
import WorkerStatus from "../components/WorkerStatus";
import LogViewer from "../components/LogViewer";
import "../styles/global.css";

export default function Dashboard() {
  return (
    <main className="dashboard-container">
      <header className="dashboard-header">
        <h1>AI Agent Platform Dashboard</h1>
        <p>Agent control and execution monitoring panel</p>
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
