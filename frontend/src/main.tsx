import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, NavLink, Route, Routes, Link } from "react-router-dom";
import { ComparePage } from "./pages/ComparePage";
import { EventPage } from "./pages/EventPage";
import { EventsPage } from "./pages/EventsPage";
import "./styles.css";

function App() {
  return (
    <div className="shell">
      <header className="masthead">
        <Link to="/" className="brand">
          Fight<span>Lens</span>
        </Link>
        <nav>
          <NavLink to="/" end>Cards</NavLink>
          <NavLink to="/compare">Compare</NavLink>
        </nav>
      </header>
      <div className="dateline">
        <span>UFC matchup analysis</span>
        <span>Model estimates only: not guaranteed results, not sportsbook odds</span>
      </div>
      <main>
        <Routes>
          <Route path="/" element={<EventsPage />} />
          <Route path="/events/:id" element={<EventPage />} />
          <Route path="/compare" element={<ComparePage />} />
          <Route path="*" element={<p className="empty">Page not found.</p>} />
        </Routes>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <BrowserRouter>
      <App />
    </BrowserRouter>
  </StrictMode>,
);
