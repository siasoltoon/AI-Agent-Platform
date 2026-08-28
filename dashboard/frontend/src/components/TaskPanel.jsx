import { createTask } from "../api/tasks";

export default function TaskPanel() {
  async function handleCreateTask() {
    await createTask({ title: "New Agent Task" });
  }

  return (
    <section>
      <h2>Task Panel</h2>
      <button onClick={handleCreateTask}>Create Task</button>
    </section>
  );
}
