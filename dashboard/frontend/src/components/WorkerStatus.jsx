import React from "react";
import { getWorkers } from "../api/workers";

export default function WorkerStatus() {
  async function refreshWorkers() {
    await getWorkers();
  }

  return (
    <section>
      <h2>Worker Status</h2>
      <button onClick={refreshWorkers}>Refresh Workers</button>
    </section>
  );
}
