import React, { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import L from 'leaflet';
import 'leaflet.heat';
import 'leaflet/dist/leaflet.css';
import './style.css';

const risks = ['Low', 'Moderate', 'High', 'Severe', 'No Travel'];
const colors = ['#2fd4a3', '#f0b429', '#f48b32', '#ff5c7a', '#b86bd1'];
const unknown = '#8fa9b6';
const localDate = (date) => new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16);
const time = (seconds) => new Intl.DateTimeFormat(undefined, { dateStyle: 'medium', timeStyle: 'short' }).format(seconds * 1000);
const miles = (value) => Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 });
const duration = (seconds) => {
  const minutes = Math.round(seconds / 60);
  return minutes < 60 ? `${minutes} min` : `${Math.floor(minutes / 60)} hr ${minutes % 60} min`;
};
const defaultForm = () => ({
  origin: 'Denver, CO', destination: 'Colorado Springs, CO',
  departure: localDate(new Date(Date.now() + 3600000)), load: 42000, spacing: 25,
});

function MapView({ trip, selected, onSelect, hour, showHeat }) {
  const element = useRef(null);
  const map = useRef(null);
  const paths = useRef(null);
  const heat = useRef(null);
  const [tileError, setTileError] = useState(false);

  useEffect(() => {
    const instance = L.map(element.current, { scrollWheelZoom: false }).setView([39.28, -104.88], 9);
    map.current = instance;
    instance.createPane('weather').style.zIndex = 350;
    const tiles = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', {
      maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(instance);
    tiles.on('tileerror', () => setTileError(true));
    tiles.on('tileload', () => setTileError(false));
    paths.current = L.layerGroup().addTo(instance);
    const resize = new ResizeObserver(() => instance.invalidateSize());
    resize.observe(element.current);
    return () => { resize.disconnect(); instance.remove(); };
  }, []);

  useEffect(() => {
    if (!trip) return;
    map.current.fitBounds(L.latLngBounds(trip.routes.flatMap(route => route.geometry)), { padding: [32, 32], maxZoom: 13 });
  }, [trip]);

  useEffect(() => {
    const layer = paths.current;
    layer.clearLayers();
    if (!trip) return;
    const ordered = [...trip.routes].sort((a, b) => Number(a.id === selected) - Number(b.id === selected));
    for (const route of ordered) {
      const active = route.id === selected;
      const color = route.blocked ? colors[4] : active ? '#1ed6a4' : '#7f98a8';
      L.polyline(route.geometry, { color: '#0b1c2b', opacity: 0.85, weight: active ? 9 : 6, interactive: false }).addTo(layer);
      L.polyline(route.geometry, { color, opacity: active ? 1 : 0.77, weight: active ? 6 : 3,
        dashArray: route.blocked ? '6 6' : null }).addTo(layer).on('click', () => onSelect(route.id));
      for (const checkpoint of route.checkpoints) {
        const detail = document.createElement('div');
        const heading = document.createElement('strong');
        heading.textContent = `Mile ${miles(checkpoint.mile)} · ${risks[checkpoint.risk] ?? 'Unknown'}`;
        const body = document.createElement('div');
        body.textContent = `Weather at arrival · ${time(checkpoint.eta)}`;
        detail.append(heading, body);
        if (checkpoint.weather) {
          const { wind, rain, snow } = checkpoint.weather;
          const readings = document.createElement('div');
          readings.textContent = `Wind ${wind.toFixed(1)} mph · Rain ${rain.toFixed(2)} in/hr · Snow ${snow.toFixed(2)} in/hr`;
          detail.append(readings);
        }
        if (checkpoint.reason) {
          const reason = document.createElement('div');
          reason.textContent = checkpoint.reason;
          detail.append(reason);
        }
        L.circleMarker(checkpoint.point, { radius: active ? 6 : 4, fillColor: colors[checkpoint.risk] ?? unknown,
          color: '#0b1c2b', weight: active ? 2 : 1, fillOpacity: active ? 1 : 0.75 }).bindPopup(detail).addTo(layer);
      }
    }
  }, [trip, selected, onSelect]);

  useEffect(() => {
    if (!trip || !showHeat) return;
    heat.current = L.heatLayer([], { pane: 'weather', radius: 35, blur: 26, maxZoom: 9, max: 1,
      gradient: { 0.15: '#2fd4a3', 0.38: '#f0b429', 0.58: '#f48b32', 0.8: '#ff5c7a', 1: '#b86bd1' },
    }).addTo(map.current);
    return () => { heat.current.remove(); heat.current = null; };
  }, [trip, showHeat]);

  useEffect(() => {
    heat.current?.setLatLngs(trip.heat.flatMap(({ point, levels }) =>
      levels[hour] == null ? [] : [[...point, (levels[hour] + 1) / 5]]));
  }, [trip, hour, showHeat]);

  return <div className="map-wrap"><div className="map" ref={element} aria-label="Map of truck route alternatives" />
    {tileError && <span className="tile-message">Basemap temporarily unavailable</span>}
  </div>;
}

function recommendation(trip, route) {
  if (trip.recommended !== route.id) return null;
  const other = trip.routes.filter(item => item.id !== route.id && !item.blocked && item.complete)
    .sort((a, b) => a.riskMiles[3] - b.riskMiles[3] || a.riskMiles[2] - b.riskMiles[2] ||
      a.averageRisk - b.averageRisk || a.seconds - b.seconds)[0];
  if (!other) return 'Only eligible route.';
  const extraTime = route.seconds > other.seconds ? ` Drive is ${duration(route.seconds - other.seconds)} longer.` : '';
  for (const [level, label] of [[3, 'Severe'], [2, 'High']]) {
    const difference = other.riskMiles[level] - route.riskMiles[level];
    if (difference > 0.000001) return `${miles(difference)} fewer ${label} miles than the next eligible route.${extraTime}`;
  }
  if (other.averageRisk - route.averageRisk > 0.00000001) return `Lowest average risk among routes with equal Severe and High mileage.${extraTime}`;
  if (other.seconds > route.seconds) return 'Shortest drive among routes with equal weather risk.';
  return 'Tied on weather risk and drive time.';
}

function App() {
  const [form, setForm] = useState(defaultForm);
  const [trip, setTrip] = useState(null);
  const [selected, setSelected] = useState(null);
  const [hour, setHour] = useState(0);
  const [showHeat, setShowHeat] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  async function plan(demo) {
    setBusy(true);
    setError('');
    try {
      const details = demo ? defaultForm() : form;
      if (demo) setForm(details);
      const session = await fetch('/api/session/');
      if (!session.ok) throw new Error('Could not connect to the trip planner.');
      const csrf = document.cookie.split('; ').find(cookie => cookie.startsWith('csrftoken='))?.split('=')[1];
      const response = await fetch('/api/trip/', { method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRFToken': csrf ?? '' },
        body: JSON.stringify({ ...details, spacing: Number(details.spacing),
          departure: new Date(details.departure).toISOString(), demo }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error);
      setTrip(data);
      setSelected(data.recommended ?? data.routes[0].id);
      setHour(0);
    } catch (failure) {
      setError(failure.message || 'The trip could not be evaluated.');
    } finally {
      setBusy(false);
    }
  }

  function field(name, label, type, extra = {}) {
    return <label>{label}<input required type={type} value={form[name]}
      onChange={event => setForm({ ...form, [name]: event.target.value })} {...extra} /></label>;
  }

  return <>
    <header><div className="brand"><span className="brand-mark" aria-hidden="true"><i /><i /><i /></span><strong>spotter</strong></div>
      <span className="header-label">Weather route planner</span></header>
    <main>
      <section className="intro"><h1>Plan a weather-aware trip</h1>
        <p>Compare truck routes using forecast conditions at each checkpoint’s arrival time.</p></section>
      <form className="trip-form" onSubmit={event => { event.preventDefault(); plan(false); }}>
        {field('origin', 'Origin', 'text', { maxLength: 160 })}
        {field('destination', 'Destination', 'text', { maxLength: 160 })}
        {field('departure', 'Departure · local time', 'datetime-local')}
        {field('load', 'Load weight · lb', 'number', { min: 0, step: 'any' })}
        <label>Checkpoints<select value={form.spacing} onChange={event => setForm({ ...form, spacing: event.target.value })}>
          {[10, 25, 50].map(value => <option value={value} key={value}>Every {value} mi</option>)}</select></label>
        <button className="primary" disabled={busy} type="submit">{busy ? 'Evaluating…' : 'Compare routes'}</button>
      </form>
      <div className="trip-status"><button className="sample" type="button" onClick={() => plan(true)} disabled={busy}>Load sample trip</button>
        {trip?.demo && <span className="demo">Sample trip · simulated routes and weather</span>}
        {busy && <span role="status">Calculating routes and weather exposure…</span>}</div>
      {error && <p className="notice" role="alert">{error}</p>}
      <div className="workspace">
        <section className="routes panel" aria-label="Route comparison">
          <div className="panel-head"><h2>Route comparison</h2>{trip && <span>{trip.routes.length} available</span>}</div>
          {!trip && <p className="empty">Compare routes for your trip or load the sample to explore a completed comparison.</p>}
          {trip && <>
            <p className="endpoints">{trip.origin} <span>→</span> {trip.destination}</p>
            {trip.routes.length < 3 && <p className="notice">The routing provider found fewer than three distinct options.</p>}
            {!trip.recommended && <p className="notice">{trip.routes.every(route => route.blocked) ?
              'Every route has a No Travel checkpoint.' : 'Forecast coverage is incomplete. No route recommendation is available.'}</p>}
            {[...trip.routes].sort((a, b) => Number(b.id === trip.recommended) - Number(a.id === trip.recommended)).map(route =>
              <button type="button" className={`route ${selected === route.id ? 'active' : ''}`} key={route.id}
                aria-pressed={selected === route.id} onClick={() => setSelected(route.id)}>
                <span className="route-title"><strong>Route {route.id}</strong><span className="risk-label"
                  style={{ color: colors[route.worstRisk] ?? unknown }}>{risks[route.worstRisk] ?? 'Unknown'}</span></span>
                {trip.recommended === route.id && <span className="recommended">Recommended</span>}
                <span className="route-time">{duration(route.seconds)} <small>· {miles(route.miles)} mi</small></span>
                <span className="arrival">Arrives {time(route.eta)}</span>
                <span className="risk-miles">{miles(route.riskMiles[3])} Severe mi <span>·</span> {miles(route.riskMiles[2])} High mi
                  {route.riskMiles[4] > 0 && <> · {miles(route.riskMiles[4])} No Travel mi</>}</span>
                {!route.complete && <span className="explanation">Some checkpoints have no forecast.</span>}
                {route.blocked && <span className="explanation">A checkpoint exceeds a No Travel threshold.</span>}
                {recommendation(trip, route) && <span className="explanation">{recommendation(trip, route)}</span>}
              </button>)}
          </>}
        </section>
        <section className="map-panel panel" aria-label="Weather corridor">
          <div className="panel-head"><h2>Weather corridor</h2>
            <label className="toggle"><input type="checkbox" checked={showHeat} disabled={!trip}
              onChange={event => setShowHeat(event.target.checked)} /> Heatmap</label></div>
          <MapView trip={trip} selected={selected} onSelect={setSelected} hour={hour} showHeat={showHeat} />
          <div className="forecast">
            <div className="forecast-label"><label htmlFor="forecast">Forecast hour <strong>+{hour}h</strong></label>
              {trip && <span>{time(trip.departure + hour * 3600)}</span>}</div>
            <input id="forecast" type="range" min="0" max="48" step="1" value={hour} disabled={!trip || !showHeat}
              onChange={event => setHour(Number(event.target.value))} />
            <div className="range-ends"><span>Departure</span><span>+48 hours</span></div>
            {trip && showHeat && trip.heat.some(point => point.levels[hour] == null) &&
              <p className="forecast-gap">Forecast unavailable at some corridor points for this hour.</p>}
          </div>
          <div className="legend" aria-label="Weather risk legend">{[...risks, 'Unknown'].map((risk, index) =>
            <span key={risk}><i style={{ backgroundColor: colors[index] ?? unknown }} />{risk}</span>)}</div>
          {trip && <details className="checkpoints"><summary>Route {selected} checkpoints · Weather at arrival</summary>
            <ul>{trip.routes.find(route => route.id === selected)?.checkpoints.map(checkpoint =>
              <li key={checkpoint.mile}><strong>Mile {miles(checkpoint.mile)}</strong> · {time(checkpoint.eta)} · {risks[checkpoint.risk] ?? 'Unknown'}
                {checkpoint.weather && <> · Wind {checkpoint.weather.wind.toFixed(1)} mph · Rain {checkpoint.weather.rain.toFixed(2)} in/hr · Snow {checkpoint.weather.snow.toFixed(2)} in/hr</>}
              </li>)}</ul></details>}
        </section>
      </div>
    </main>
  </>;
}

createRoot(document.getElementById('root')).render(<App />);
