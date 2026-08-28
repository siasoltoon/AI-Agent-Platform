import TaskPanel from "../components/TaskPanel";
import AgentStatus from "../components/AgentStatus";
import WorkerStatus from "../components/WorkerStatus";
import LogViewer from "../components/LogViewer";

export default function Dashboard() {
  return (
    <main>
      <h1>AI Agent Platform Dashboard</h1>
      <TaskPanel />
      <AgentStatus />
      <WorkerStatus />
      <LogViewer />
    </main>
  );
}
