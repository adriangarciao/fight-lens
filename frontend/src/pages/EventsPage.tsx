import { Link } from "react-router-dom";
import { api, type EventSummary } from "../api";
import { fmtDate } from "../format";
import { useAsync } from "../useAsync";

function EventList({ events }: { events: EventSummary[] }) {
  return (
    <ul className="event-list">
      {events.map((e, i) => (
        <li key={e.id}>
          <Link to={`/events/${e.id}`} className="event-row" style={{ animationDelay: `${i * 40}ms` }}>
            <span className="event-date mono small">{fmtDate(e.date)}</span>
            <span>
              <span className="event-name">{e.name}</span>
              <br />
              <span className="small muted">{e.location}</span>
            </span>
            <span className={`badge ${e.status === "scheduled" ? "hot" : ""}`}>
              {e.bout_count} bouts · {e.status}
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export function EventsPage() {
  const upcoming = useAsync(api.upcomingEvents, []);
  const recent = useAsync(api.recentEvents, []);
  return (
    <>
      <div className="kicker">Fight cards</div>
      <h1>Upcoming</h1>
      {upcoming.loading && <p className="loading">Loading cards</p>}
      {upcoming.error && <p className="error">{upcoming.error}</p>}
      {upcoming.data && (upcoming.data.length ? <EventList events={upcoming.data} /> : <p className="empty">No scheduled cards in the current data snapshot.</p>)}

      <section className="section">
        <div className="section-head">
          <h2>Recent results</h2>
        </div>
        {recent.loading && <p className="loading">Loading</p>}
        {recent.error && <p className="error">{recent.error}</p>}
        {recent.data && <EventList events={recent.data} />}
      </section>
    </>
  );
}
