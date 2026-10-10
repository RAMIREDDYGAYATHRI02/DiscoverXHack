import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { Activity, ArrowLeftRight, ArrowRight, ArrowUpRight, CalendarDays, Check, ChevronLeft, ChevronRight, CircleHelp, Clock3, HeartHandshake, History, LayoutDashboard, ListChecks, LogOut, Plus, Search, ShieldCheck, Sparkles, Stethoscope, Users, X } from 'lucide-react';
import './styles.css';

const Monday = (value) => { const d = new Date(`${value.slice(0, 10)}T12:00:00Z`); d.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7)); d.setUTCHours(0, 0, 0, 0); return d; };
const weekKey = (value) => Monday(value).toISOString().slice(0, 10);
const displayDate = (value, options = { weekday: 'short', month: 'short', day: 'numeric' }) => new Date(`${value.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-US', options);
const shortDate = (value) => new Date(`${value.slice(0, 10)}T12:00:00Z`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
const time = (value) => value.slice(11, 16);
const weekDates = (key) => { const start = new Date(`${key}T00:00:00Z`); return Array.from({ length: 7 }, (_, i) => { const d = new Date(start); d.setUTCDate(d.getUTCDate() + i); return d.toISOString().slice(0, 10); }); };
const prettyWeek = (key) => { const dates = weekDates(key); return `${shortDate(`${dates[0]}T00:00`)} – ${shortDate(`${dates[6]}T00:00`)}, ${dates[6].slice(0, 4)}`; };
const personName = (staff, id) => staff.find((item) => item.id === id)?.name || 'Unknown';
const initials = (name) => name.split(' ').map((part) => part[0]).slice(0, 2).join('').toUpperCase();
const hoursFor = (item) => (Date.parse(`${item.end}:00Z`) - Date.parse(`${item.start}:00Z`)) / 3600000;
const API_BASE = import.meta.env.VITE_API_BASE_URL || '';

async function getState() {
  const response = await fetch(`${API_BASE}/api/state`);
  const data = await response.json();
  if (!response.ok) throw new Error(data.message || 'Could not connect to the roster.');
  return data;
}

function App() {
  const [data, setData] = useState(null);
  const [current, setCurrent] = useState(null);
  const [view, setView] = useState('overview');
  const [week, setWeek] = useState('');
  const [range, setRange] = useState('week');
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [loadingError, setLoadingError] = useState('');

  const refresh = useCallback(async () => {
    try {
      const next = await getState();
      setData(next);
      setLoadingError('');
      setWeek((previous) => previous || weekKey(next.shifts[0].start));
      setCurrent((previous) => previous && next.staff.some((person) => person.id === previous.id) ? next.staff.find((person) => person.id === previous.id) : null);
    } catch (error) { setLoadingError(error.message); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  useEffect(() => { if (!toast) return undefined; const timer = setTimeout(() => setToast(null), 4200); return () => clearTimeout(timer); }, [toast]);

  const act = async (action, options = {}) => {
    if (!current || busy) return;
    setBusy(true);
    try {
      const response = await fetch(`${API_BASE}/api/actions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ actor_id: current.id, action, ...options }) });
      const result = await response.json();
      if (!response.ok) throw new Error(result.message || 'That action could not be completed.');
      setToast({ message: result.message, error: false });
      await refresh();
    } catch (error) { setToast({ message: error.message, error: true }); await refresh(); }
    finally { setBusy(false); }
  };

  const staff = data?.staff || [];
  const shifts = data?.shifts || [];
  const listings = data?.listings || [];
  const history = data?.history || [];
  const isManager = current?.role === 'MANAGER';
  const ownedShifts = useMemo(() => shifts.filter((item) => item.assigned_to === current?.id).sort((a, b) => a.start.localeCompare(b.start)), [shifts, current]);
  const activeListingFor = (shiftId) => listings.find((listing) => listing.shift_id === shiftId && ['OPEN', 'CLAIMED'].includes(listing.status));
  const openListings = listings.filter((listing) => listing.status === 'OPEN' && listing.posted_by !== current?.id);
  const claimedListings = listings.filter((listing) => listing.status === 'CLAIMED');
  const currentWeekShifts = ownedShifts.filter((item) => weekKey(item.start) === week);
  const displayedMyShifts = range === 'week' ? currentWeekShifts : ownedShifts;
  const claimsHistory = history.slice(0, 6);
  const nav = isManager
    ? [{ id: 'overview', label: 'Overview', icon: LayoutDashboard }, { id: 'approvals', label: 'Approvals', icon: ListChecks, count: claimedListings.length }, { id: 'activity', label: 'Activity', icon: History }]
    : [{ id: 'overview', label: 'Overview', icon: LayoutDashboard }, { id: 'my-shifts', label: 'My shifts', icon: CalendarDays, count: ownedShifts.length }, { id: 'find-shifts', label: 'Find a cover', icon: Search, count: openListings.length }, { id: 'activity', label: 'Activity', icon: History }];

  const go = (next) => { setView(next); window.scrollTo({ top: 0, behavior: 'smooth' }); };

  if (loadingError && !data) return <div className="error-screen"><div className="brand"><span className="brand-icon"><ArrowLeftRight size={18} /></span><span>shift<span className="brand-light">swap</span></span></div><div className="error-card"><div className="error-mark"><CircleHelp size={25} /></div><h1>We can’t reach the roster yet.</h1><p>{loadingError}</p><button className="button primary" onClick={refresh}>Try again <ArrowRight size={15} /></button></div></div>;
  if (!data) return <div className="loading-screen"><span className="loader" /><span>Loading CityCare roster…</span></div>;

  if (!current) return <RoleSelect staff={staff} onChoose={(person) => { setCurrent(person); setView('overview'); }} />;

  const navView = nav.find((item) => item.id === view)?.label || 'Overview';
  const weekShifts = currentWeekShifts;
  const hours = weekShifts.reduce((sum, item) => sum + hoursFor(item), 0);
  const weekDateWord = new Date(`${week}T12:00:00Z`).toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' });

  return <div className="app-shell">
    <aside className="sidebar">
      <button className="brand brand-button" onClick={() => go('overview')}><span className="brand-icon"><ArrowLeftRight size={18} /></span><span>shift<span className="brand-light">swap</span></span></button>
      <div className="workspace-label">CITYCARE CLINIC</div>
      <nav className="side-nav" aria-label="Main navigation">{nav.map((item) => <button key={item.id} className={`nav-item ${view === item.id ? 'active' : ''}`} onClick={() => go(item.id)}><item.icon size={17} strokeWidth={1.8} /><span>{item.label}</span>{item.count > 0 && <span className="nav-count">{item.count}</span>}</button>)}</nav>
      <div className="sidebar-bottom"><div className="team-card"><span className="team-icon"><HeartHandshake size={17} /></span><div><strong>Care comes first.</strong><span>Thanks for supporting your team.</span></div></div><div className="side-footer"><span className="status-dot" />Roster is up to date<span className="footer-more">···</span></div></div>
    </aside>

    <main className="main-content">
      <header className="topbar"><div className="breadcrumb"><span>CityCare</span><span className="crumb-divider">/</span><strong>{navView}</strong></div><div className="top-actions"><span className="today-label">Week of {shortDate(`${week}T00:00`)}</span><span className="top-divider" /><label className="acting-as"><span>Acting as</span><select value={current.id} onChange={(event) => { const chosen = staff.find((person) => person.id === event.target.value); setCurrent(chosen); setView('overview'); }} aria-label="Choose which person you are acting as">{staff.map((person) => <option key={person.id} value={person.id}>{person.name} · {person.role === 'MANAGER' ? 'Manager' : 'Staff'}</option>)}</select></label><span className="profile-avatar">{initials(current.name)}</span></div></header>
      {toast && <div className={`toast ${toast.error ? 'toast-error' : ''}`} role="status"><span>{toast.error ? <X size={15} /> : <Check size={15} />}</span>{toast.message}</div>}

      {view === 'overview' && <section className="page active">
        <div className="welcome-row"><div><div className="eyebrow">{weekDateWord.toUpperCase()}</div><h1>{isManager ? 'Welcome back,' : 'Good morning,'} {current.name}<Sparkles className="heading-sparkle" size={18} /></h1><p className="page-subtitle">{isManager ? 'Here’s where the team could use your help.' : 'Here’s your schedule and what’s happening with your team.'}</p></div><div className="week-picker"><button className="week-arrow" onClick={() => { const date = new Date(`${week}T00:00:00Z`); date.setUTCDate(date.getUTCDate() - 7); setWeek(date.toISOString().slice(0, 10)); }} aria-label="Previous week"><ChevronLeft size={16} /></button><span>{prettyWeek(week)}</span><button className="week-arrow" onClick={() => { const date = new Date(`${week}T00:00:00Z`); date.setUTCDate(date.getUTCDate() + 7); setWeek(date.toISOString().slice(0, 10)); }} aria-label="Next week"><ChevronRight size={16} /></button><button className="today-button" onClick={() => setWeek(weekKey(shifts[0].start))}>Roster week</button></div></div>
        <div className="metric-grid">
          <Metric label={isManager ? 'CLAIMS TO REVIEW' : 'MY SHIFTS THIS WEEK'} value={isManager ? claimedListings.length : weekShifts.length} icon={isManager ? ListChecks : CalendarDays} tone="lavender" foot={<><b>{isManager ? 'Manager review' : `${hours} hours`}</b> {isManager ? 'awaiting your decision' : ' scheduled'}</>} />
          <Metric label="OPEN FOR COVER" value={openListings.length} icon={ArrowUpRight} tone="peach" foot={<>{isManager ? 'Across the clinic' : 'Across your team'}</>} />
          <Metric label="CLAIMS IN REVIEW" value={claimedListings.length} icon={ShieldCheck} tone="mint" foot={<>Claims awaiting manager review</>} />
          <Metric label="TEAM MEMBERS" value={staff.filter((item) => item.role === 'STAFF').length} icon={Users} tone="blue" foot={<>Ready to help each other</>} />
        </div>
        <div className="content-grid">
          <section className="panel schedule-panel"><div className="panel-heading"><div><h2>{isManager ? 'Clinic coverage' : 'My schedule'}</h2><p>{isManager ? 'Current assignments for this week' : 'Your shifts for this week'}</p></div>{!isManager && <button className="text-button" onClick={() => go('my-shifts')}>Full schedule <ArrowRight size={13} /></button>}</div>
            {isManager ? <ManagerCoverage shifts={shifts.filter((item) => weekKey(item.start) === week).slice(0, 7)} staff={staff} listings={listings} /> : <ShiftSchedule shifts={weekShifts.slice(0, 5)} staff={staff} listings={listings} current={current} onAct={act} />}
          </section>
          <section className="panel activity-panel"><div className="panel-heading"><div><h2>Team activity</h2><p>The latest across your clinic</p></div><button className="icon-button" onClick={() => go('activity')} aria-label="View all activity"><ArrowRight size={15} /></button></div><ActivityList history={claimsHistory.slice(0, 5)} staff={staff} /></section>
        </div>
        <section className="cover-banner"><span className="cover-banner-icon"><Sparkles size={17} /></span><div><h2>A little help goes a long way.</h2><p>Pick up a shift that fits your week and support the people you work with.</p></div><button className="banner-button" onClick={() => go(isManager ? 'approvals' : 'find-shifts')}>{isManager ? 'Review claims' : 'Explore open shifts'} <ArrowRight size={13} /></button><span className="banner-decoration"><Sparkles size={76} /></span></section>
      </section>}

      {view === 'my-shifts' && !isManager && <section className="page active"><div className="page-heading"><div><div className="eyebrow">YOUR ROSTER</div><h1>My shifts</h1><p className="page-subtitle">Post a shift for cover when your plans change.</p></div><div className="section-filter"><button className={range === 'week' ? 'filter-button active' : 'filter-button'} onClick={() => setRange('week')}>This week</button><button className={range === 'all' ? 'filter-button active' : 'filter-button'} onClick={() => setRange('all')}>All shifts</button></div></div>
        <div className="panel table-panel"><div className="shift-table-head"><span>SHIFT</span><span>WHEN</span><span>TIME</span><span>STATUS</span><span /></div>{displayedMyShifts.length ? displayedMyShifts.map((item) => { const listing = activeListingFor(item.id); return <div className="shift-row" key={item.id}><div className="shift-name"><strong>{item.required_certification ? `${item.required_certification} care` : 'General care'}</strong><span>{item.id}</span></div><div className="shift-when">{displayDate(item.start)}<span>{item.start.slice(0, 10) === item.end.slice(0, 10) ? 'Same day' : `Ends ${displayDate(item.end)}`}</span></div><div className="shift-time">{time(item.start)} – {time(item.end)}</div><div><StatusBadge listing={listing} /></div><div>{listing?.status === 'OPEN' && listing.posted_by === current.id && <button className="action-button danger" disabled={busy} onClick={() => act('WITHDRAW', { listing_id: listing.id })}>Withdraw</button>}{listing?.status === 'CLAIMED' && <button className="action-button" disabled>Claim pending</button>}{!listing && <button className="action-button" disabled={busy} onClick={() => act('POST', { shift_id: item.id })}><Plus size={12} /> Post</button>}</div></div>; }) : <Empty title="No shifts this week" detail="Try the all shifts view to see your full roster." />}</div>
      </section>}

      {view === 'find-shifts' && !isManager && <section className="page active"><div className="page-heading"><div><div className="eyebrow">TEAM COVERAGE</div><h1>Find a cover</h1><p className="page-subtitle">Each shift is checked against your certifications and roster.</p></div><span className="open-pill"><span className="status-dot" />{openListings.length} {openListings.length === 1 ? 'shift' : 'shifts'} open</span></div>
        {openListings.length ? <div className="listing-grid">{openListings.map((listing) => { const item = shifts.find((shift) => shift.id === listing.shift_id); if (!item) return null; const reasons = previewReasons(data, item, current.id); return <article className="listing-card" key={listing.id}><div className="listing-top"><div className="listing-owner"><span className="owner-avatar">{initials(personName(staff, listing.posted_by))}</span><div><strong>{personName(staff, listing.posted_by)}</strong><span>Posted for cover</span></div></div><span className={`cert-tag ${item.required_certification ? '' : 'none'}`}>{item.required_certification || 'No certification'}</span></div><h3>{item.required_certification ? `${item.required_certification} care` : 'General care'} <span className="listing-shift-id">· {item.id}</span></h3><div className="listing-meta"><span><CalendarDays size={13} />{displayDate(item.start)}</span><span><Clock3 size={13} />{time(item.start)} – {time(item.end)}</span><span>{hoursFor(item)}h</span></div><div className="claim-check"><div className={`eligibility ${reasons.length ? 'ineligible' : ''}`}><strong>{reasons.length ? 'Not eligible' : 'You’re eligible to claim'}</strong>{reasons.length ? <ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <span>Rules 1–5 checked against your current roster</span>}</div><button className="button primary claim-button" disabled={busy || reasons.length > 0} onClick={() => act('CLAIM', { listing_id: listing.id })}>Claim shift <ArrowRight size={12} /></button></div></article>; })}</div> : <Empty title="All caught up" detail="There are no open cover requests right now." />}
      </section>}

      {view === 'approvals' && isManager && <section className="page active"><div className="page-heading"><div><div className="eyebrow">MANAGER WORKSPACE</div><h1>Approvals</h1><p className="page-subtitle">Review the request and make sure the roster still meets clinic rules.</p></div><span className="open-pill"><span className="status-dot amber" />{claimedListings.length} awaiting review</span></div>
        {claimedListings.length ? <div className="approval-list">{claimedListings.map((listing) => { const item = shifts.find((shift) => shift.id === listing.shift_id); if (!item) return null; const claimant = staff.find((person) => person.id === listing.claimed_by); const reasons = previewReasons(data, item, listing.claimed_by); return <article className="approval-card" key={listing.id}><div className="approval-main"><div className="approval-shift"><span className="owner-avatar">{initials(personName(staff, listing.posted_by))}</span><div className="approval-person"><strong>{personName(staff, listing.posted_by)} <span className="approval-arrow">→</span> {claimant?.name}</strong><span>{item.id} · {item.required_certification ? `${item.required_certification} care` : 'General care'} · {displayDate(item.start)} · {time(item.start)} – {time(item.end)}</span></div></div><span className="status-badge badge-claimed">Needs review</span></div><div className={`approval-detail ${reasons.length ? 'bad' : 'good'}`}><strong>{reasons.length ? 'Approval blocked by current roster' : 'Rules pass against the current roster'}</strong>{reasons.length ? <ul>{reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul> : <span>Certification, rest period, overlaps, and weekly hours are valid.</span>}</div><div className="approval-actions"><span className="approval-note">Posted by {personName(staff, listing.posted_by)} · Claimant {claimant?.name}</span><div className="approval-buttons"><button className="button secondary" disabled={busy} onClick={() => act('REJECT', { listing_id: listing.id })}>Reject</button><button className="button primary" disabled={busy || reasons.length > 0} onClick={() => act('APPROVE', { listing_id: listing.id })}><Check size={13} /> Approve claim</button></div></div></article>; })}</div> : <Empty title="Nothing to review" detail="Claimed shifts will show up here for manager approval." />}
      </section>}

      {view === 'activity' && <section className="page active"><div className="page-heading"><div><div className="eyebrow">A SHARED RECORD</div><h1>Activity</h1><p className="page-subtitle">Every roster action, in one place.</p></div></div><div className="panel activity-page-panel"><ActivityList history={history} staff={staff} full /></div></section>}
      <footer className="page-footer"><span>ShiftSwap for CityCare Clinic</span><span>Every shift covered, together <Sparkles size={12} /></span></footer>
    </main>
  </div>;
}

function RoleSelect({ staff, onChoose }) {
  const managers = staff.filter((person) => person.role === 'MANAGER');
  const team = staff.filter((person) => person.role === 'STAFF');
  return <main className="welcome-screen"><div className="welcome-header"><div className="brand"><span className="brand-icon"><ArrowLeftRight size={18} /></span><span>shift<span className="brand-light">swap</span></span></div><span className="clinic-label"><span className="status-dot" /> CITYCARE CLINIC · STAFF PORTAL</span></div><div className="welcome-body"><div className="welcome-intro"><span className="welcome-emblem"><Stethoscope size={22} /></span><div className="eyebrow">A BETTER WAY TO SWAP</div><h1>Every shift covered,<br /><span>together.</span></h1><p>Choose your profile to see your schedule, find shift cover, or review team requests.</p></div><div className="choose-panel"><div className="choose-heading"><div><span className="eyebrow">WELCOME TO CITYCARE</span><h2>Who are you today?</h2></div><span className="no-login"><ShieldCheck size={14} /> No login required</span></div><div className="choose-columns"><div className="choose-group"><div className="choose-label"><span>STAFF</span><span>{team.length} team members</span></div><div className="people-list">{team.map((person) => <button className="person-option" key={person.id} onClick={() => onChoose(person)}><span className="person-avatar">{initials(person.name)}</span><span className="person-info"><strong>{person.name}</strong><span>{person.certifications.length ? person.certifications.join(' · ') : 'General care'}</span></span><ArrowRight size={15} className="person-arrow" /></button>)}</div></div><div className="choose-group manager-group"><div className="choose-label"><span>MANAGERS</span><span>{managers.length} team leads</span></div><div className="people-list">{managers.map((person) => <button className="person-option manager-option" key={person.id} onClick={() => onChoose(person)}><span className="person-avatar manager-avatar">{initials(person.name)}</span><span className="person-info"><strong>{person.name}</strong><span>Manager workspace</span></span><ArrowRight size={15} className="person-arrow" /></button>)}</div><div className="manager-note"><ShieldCheck size={15} /><span>Managers can review claims and approve roster changes.</span></div></div></div></div></div><div className="welcome-footer"><span>CityCare Clinic · ShiftSwap</span><span>Making room for life, one shift at a time <Sparkles size={12} /></span></div></main>;
}

function Metric({ label, value, icon: Icon, tone, foot }) { return <article className="metric-card"><div className="metric-top"><span className="metric-label">{label}</span><span className={`metric-icon ${tone}`}><Icon size={14} /></span></div><div className="metric-value">{value}</div><div className="metric-foot">{foot}</div></article>; }

function StatusBadge({ listing }) {
  if (listing?.status === 'OPEN') return <span className="status-badge badge-listed">Posted</span>;
  if (listing?.status === 'CLAIMED') return <span className="status-badge badge-claimed">Claim pending</span>;
  return <span className="status-badge badge-neutral">Scheduled</span>;
}

function ShiftSchedule({ shifts, staff, listings, current, onAct }) {
  if (!shifts.length) return <Empty title="A little breathing room" detail="You have no shifts scheduled for this week." />;
  return <div className="schedule-list">{shifts.map((item) => { const listing = listings.find((entry) => entry.shift_id === item.id && ['OPEN', 'CLAIMED'].includes(entry.status)); return <div className="schedule-item" key={item.id}><div className="schedule-date"><strong>{displayDate(item.start).split(',')[0]}</strong>{shortDate(item.start)}</div><div className="schedule-detail"><strong>{item.required_certification ? `${item.required_certification} care` : 'General care'}</strong><span>{time(item.start)} – {time(item.end)} · {hoursFor(item)} hours</span></div><div className="schedule-trailing">{listing?.status === 'OPEN' && <StatusBadge listing={listing} />}{listing?.status === 'CLAIMED' && <StatusBadge listing={listing} />}{!listing && <button className="mini-post" onClick={() => onAct('POST', { shift_id: item.id })} aria-label={`Post shift ${item.id} for cover`}><Plus size={13} /> Post</button>}</div></div>; })}</div>;
}

function ManagerCoverage({ shifts, staff, listings }) {
  if (!shifts.length) return <Empty title="No shifts in this week" detail="Move to another week to view roster coverage." />;
  return <div className="coverage-list">{shifts.map((item) => { const owner = staff.find((person) => person.id === item.assigned_to); const listing = listings.find((entry) => entry.shift_id === item.id && ['OPEN', 'CLAIMED'].includes(entry.status)); return <div className="coverage-row" key={item.id}><span className="coverage-date">{displayDate(item.start, { weekday: 'short', day: 'numeric' })}</span><span className="owner-avatar tiny">{initials(owner?.name || '?')}</span><span className="coverage-main"><strong>{owner?.name}</strong><span>{item.required_certification || 'General'} · {time(item.start)}–{time(item.end)}</span></span>{listing?.status === 'CLAIMED' ? <span className="status-badge badge-claimed">Claimed</span> : listing?.status === 'OPEN' ? <span className="status-badge badge-listed">Open</span> : <span className="status-badge badge-neutral">Covered</span>}</div>; })}</div>;
}

function ActivityList({ history, staff, full = false }) {
  if (!history.length) return <Empty title="A fresh start" detail="New roster activity will show here." />;
  return <div className="activity-list">{history.map((event) => <div className="activity-row" key={event.id}><span className="activity-avatar">{initials(event.who || personName(staff, event.actor_id))}</span><div className="activity-copy"><div><strong>{event.who || personName(staff, event.actor_id)}</strong> {activityVerb(event)} <strong>{event.shift_id}</strong></div><span>{event.outcome}{event.detail ? ` · ${event.detail}` : ''}</span></div><span className="activity-time">{relativeTime(event.at)}</span></div>)}</div>;
}

function activityVerb(event) { return ({ Posted: 'posted', Withdrew: 'withdrew', Claimed: 'claimed', Unclaimed: 'released the claim on', Approved: 'approved', Rejected: 'rejected', 'Tried to claim': 'tried to claim', 'Tried to approve': 'tried to approve' })[event.what] || event.what?.toLowerCase() || 'updated'; }
function relativeTime(value) { const date = new Date(value); if (Number.isNaN(date.getTime())) return ''; return date.toLocaleString('en-US', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' }); }

function Empty({ title, detail }) { return <div className="empty-state"><span className="empty-icon"><CalendarDays size={17} /></span><strong>{title}</strong><span>{detail}</span></div>; }

function previewReasons(data, candidateShift, candidateId) {
  const owner = candidateShift.assigned_to;
  if (candidateId === owner) return ['Rule 1: You cannot claim your own shift.'];
  const candidate = data.staff.find((person) => person.id === candidateId);
  const assigned = data.shifts.filter((item) => item.assigned_to === candidateId);
  const result = [];
  if (candidateShift.required_certification && !candidate.certifications.includes(candidateShift.required_certification)) result.push(`Rule 2: ${candidateShift.required_certification} certification required.`);
  const start = Date.parse(`${candidateShift.start}:00Z`); const end = Date.parse(`${candidateShift.end}:00Z`);
  const collisions = assigned.filter((item) => Date.parse(`${item.start}:00Z`) < end && start < Date.parse(`${item.end}:00Z`));
  collisions.forEach((item) => result.push(`Rule 3: overlaps shift ${item.id}.`));
  for (const item of assigned.filter((entry) => !collisions.includes(entry))) {
    const a = Date.parse(`${item.start}:00Z`); const b = Date.parse(`${item.end}:00Z`);
    const rest = b <= start ? start - b : a >= end ? a - end : Infinity;
    if (rest < 11 * 3600000) result.push(`Rule 4: less than 11 hours of rest from shift ${item.id}.`);
  }
  const week = weekKey(candidateShift.start);
  const weekly = assigned.filter((item) => weekKey(item.start) === week).reduce((sum, item) => sum + hoursFor(item), 0) + hoursFor(candidateShift);
  if (weekly > 40) result.push(`Rule 5: ${weekly} weekly hours exceeds 40.`);
  return result;
}

createRoot(document.getElementById('root')).render(<React.StrictMode><App /></React.StrictMode>);
