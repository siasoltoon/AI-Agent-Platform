import { getAgents } from "../api/agents";

export default function AgentStatus() {
  async function refreshAgents() {
    await getAgents();
  }

  return (
    <section>
      <h2>Agent Status</h2>
      <button onClick={refreshAgents}>Refresh Agents</button>
    </section>
  );
}
