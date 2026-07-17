import { Link, Outlet } from "react-router-dom";

export default function App() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="border-b border-parchment/20 px-4 py-3 flex items-center justify-between print:hidden">
        <span className="font-display text-xl tracking-wide">CLIO</span>
        <nav className="flex gap-4 text-sm">
          <Link to="/">Scenario</Link>
          <Link to="/cache">Case Cache</Link>
          <Link to="/history">History</Link>
        </nav>
      </header>
      <main className="flex-1 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
