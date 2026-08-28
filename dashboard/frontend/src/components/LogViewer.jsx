import { connectWebsocket } from "../services/websocket";

export default function LogViewer() {
  function startLogs() {
    connectWebsocket();
  }

  return (
    <section>
      <h2>Live Logs</h2>
      <button onClick={startLogs}>Connect Logs</button>
    </section>
  );
}
