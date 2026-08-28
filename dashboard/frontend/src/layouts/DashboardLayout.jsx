export default function DashboardLayout({ children }) {
  return (
    <main className="dashboard-container">
      <section className="dashboard-grid">
        {children}
      </section>
    </main>
  );
}
