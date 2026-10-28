import { useEffect, useRef, useState, useCallback } from 'react';
import type { ReactNode, FormEvent } from 'react';
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  Box,
  Check,
  CheckCheck,
  ChevronLeft,
  ChevronRight,
  ChevronsUpDown,
  CircleCheck,
  Clock3,
  Database,
  Eye,
  FileImage,
  Flag,
  Focus,
  GitBranch,
  Grid2X2,
  History,
  Layers3,
  Loader2,
  Menu,
  MoreHorizontal,
  Plus,
  ScanLine,
  Search,
  Settings2,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Trash2,
  UploadCloud,
  X,
  XCircle,
  ZoomIn,
} from 'lucide-react';
import { api, download, imageUrl, setToken, upload } from './api';
import type { Evaluation, Inspection, Workspace } from './types';

const date = (value: number) =>
  new Date(value * 1000).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
const percent = (value: number | undefined) =>
  value === undefined ? '—' : `${(value * 100).toFixed(1)}%`;
const score = (value: number | null | undefined) => (value == null ? '—' : value.toFixed(2));
const decisionLabel = (value: string | null) =>
  ({
    clear: 'Within reference',
    suspect: 'Anomaly detected',
    review: 'Borderline · review',
  })[value || ''] || 'Awaiting inspection';
const reviewLabel = (value: string) =>
  ({
    pending: 'Not reviewed',
    accepted: 'Accepted',
    rejected: 'Rejected',
    needs_attention: 'Escalated',
  })[value] || value;

function Photo({
  item,
  heatmap = false,
  className = '',
  onLoad,
}: {
  item: Inspection;
  heatmap?: boolean;
  className?: string;
  onLoad?: () => void;
}) {
  const [url, setUrl] = useState('');
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let current = '';
    let active = true;
    const controller = new AbortController();
    setUrl('');
    setFailed(false);
    imageUrl(item.id, heatmap, controller.signal)
      .then((value) => {
        current = value;
        if (active) setUrl(value);
        else URL.revokeObjectURL(value);
      })
      .catch((error) => {
        if (error.name !== 'AbortError' && active) setFailed(true);
      });
    return () => {
      active = false;
      controller.abort();
      if (current) URL.revokeObjectURL(current);
    };
  }, [item.id, heatmap]);
  return url ? (
    <img
      className={className}
      src={url}
      alt={`${heatmap ? 'Anomaly overlay for' : 'Surface image'} ${item.filename}`}
      onLoad={onLoad}
    />
  ) : (
    <div className={`photo-placeholder ${className}`}>
      {failed ? <FileImage size={22} /> : <Loader2 className="spin" size={20} />}
    </div>
  );
}
function Modal({
  title,
  description,
  children,
  close,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  close: () => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    ref.current?.querySelector<HTMLElement>('button,input,textarea')?.focus();
    const handler = (event: KeyboardEvent) => {
      if (event.key === 'Escape') close();
      if (event.key === 'Tab') {
        const nodes = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled),input,textarea,select,a[href]',
          ) || [],
        );
        if (!nodes.length) return;
        const first = nodes[0],
          last = nodes[nodes.length - 1];
        if (event.shiftKey && document.activeElement === first) {
          event.preventDefault();
          last.focus();
        } else if (!event.shiftKey && document.activeElement === last) {
          event.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => {
      document.removeEventListener('keydown', handler);
      previous?.focus();
    };
  }, [close]);
  return (
    <div
      className="modal-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) close();
      }}
    >
      <div className="modal" role="dialog" aria-modal="true" aria-label={title} ref={ref}>
        <header>
          <div>
            <span className="eyebrow">VISIONGUARD WORKSPACE</span>
            <h2>{title}</h2>
            {description && <p>{description}</p>}
          </div>
          <button className="icon-button" aria-label="Close dialog" onClick={close}>
            <X size={19} />
          </button>
        </header>
        {children}
      </div>
    </div>
  );
}

export default function App() {
  const [view, setView] = useState<'inspect' | 'queue' | 'model' | 'activity'>('inspect');
  useEffect(() => {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [view]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [items, setItems] = useState<Inspection[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [selectedId, setSelectedId] = useState('');
  const [filter, setFilter] = useState('all');
  const [batch, setBatch] = useState('');
  const [search, setSearch] = useState('');
  const [heatmap, setHeatmap] = useState(false);
  const [boxes, setBoxes] = useState(true);
  const [zoom, setZoom] = useState(false);
  const [mobileNav, setMobileNav] = useState(false);
  const [evaluation, setEvaluation] = useState<Evaluation | null>(null);
  const [audits, setAudits] = useState<
    {
      id: number;
      action: string;
      inspection_id: string;
      user: string;
      detail: Record<string, unknown>;
      created_at: number;
    }[]
  >([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [connectionOpen, setConnectionOpen] = useState(false);
  const [files, setFiles] = useState<File[]>([]);
  const [batchName, setBatchName] = useState('Inspection batch ' + new Date().toLocaleDateString());
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState('');
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [deleteOpen, setDeleteOpen] = useState(false);
  const [accessToken, setAccessToken] = useState('');
  const uploadInput = useRef<HTMLInputElement>(null);
  const searchInput = useRef<HTMLInputElement>(null);
  const busy = useRef(false);
  const selected = items.find((item) => item.id === selectedId) || items[0];
  const canEdit = workspace?.identity.role !== 'viewer';
  const refresh = useCallback(async () => {
    try {
      const params = new URLSearchParams({
        limit: '30',
        offset: String(offset),
      });
      if (batch) params.set('batch', batch);
      if (search) params.set('search', search);
      if (filter === 'suspect') params.set('decision', 'suspect');
      if (filter === 'pending') params.set('review', 'pending');
      if (filter === 'reviewed') params.set('review', 'accepted');
      const [w, list, e] = await Promise.all([
        api<Workspace>('/workspace'),
        api<{ items: Inspection[]; total: number }>(`/inspections?${params}`),
        api<Evaluation>('/evaluation'),
      ]);
      setWorkspace(w);
      setItems(list.items);
      setTotal(list.total);
      setEvaluation(e);
      setError('');
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Could not load workspace');
    }
  }, [batch, search, filter, offset]);
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 4000);
    return () => clearInterval(timer);
  }, [refresh]);
  useEffect(() => {
    setNote(selected?.review_note || '');
  }, [selected?.id, selected?.revision, selected?.review_note]);
  useEffect(() => {
    if (view === 'activity')
      api<typeof audits>('/audit')
        .then(setAudits)
        .catch((e) => setError(e.message));
  }, [view]);
  useEffect(() => {
    const key = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'k') {
        event.preventDefault();
        searchInput.current?.focus();
      }
    };
    window.addEventListener('keydown', key);
    return () => window.removeEventListener('keydown', key);
  }, []);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(''), 5000);
    return () => clearTimeout(timer);
  }, [notice]);
  const navigate = (next: typeof view) => {
    setView(next);
    setMobileNav(false);
  };
  const chooseFiles = (incoming: File[]) => {
    if (incoming.length > 20) {
      setError('Choose at most 20 images per upload.');
      return;
    }
    if (incoming.some((f) => f.size > 10 * 1024 * 1024)) {
      setError('Each image must be 10 MB or smaller.');
      return;
    }
    setFiles(incoming);
  };
  async function startUpload(event: FormEvent) {
    event.preventDefault();
    if (busy.current || !files.length) return;
    busy.current = true;
    setUploading(true);
    setError('');
    try {
      let duplicates = 0;
      for (let i = 0; i < files.length; i++) {
        setProgress(`Uploading ${i + 1} of ${files.length}`);
        const result = await upload(files[i], batchName);
        if (result.duplicate) duplicates++;
        setSelectedId(result.id);
      }
      setUploadOpen(false);
      setFiles([]);
      setBatch('');
      setFilter('all');
      setOffset(0);
      setView('inspect');
      setNotice(
        `${files.length - duplicates} images queued${duplicates ? `; ${duplicates} duplicates already present` : ''}.`,
      );
      await refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Upload failed');
    } finally {
      busy.current = false;
      setUploading(false);
      setProgress('');
    }
  }
  async function saveReview(decision: string) {
    if (!selected || saving) return;
    setSaving(true);
    try {
      const updated = await api<Inspection>(`/inspections/${selected.id}/review`, 'PATCH', {
        decision,
        note,
        revision: selected.revision,
      });
      setItems((items) => items.map((i) => (i.id === updated.id ? updated : i)));
      setNotice('Review saved to the audit trail.');
      await refresh();
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Review failed');
    } finally {
      setSaving(false);
    }
  }
  async function deleteInspection() {
    if (!selected) return;
    try {
      await api(`/inspections/${selected.id}`, 'DELETE');
      setDeleteOpen(false);
      setSelectedId('');
      await refresh();
      setNotice('Inspection and image files removed.');
    } catch (error) {
      setError(error instanceof Error ? error.message : 'Delete failed');
    }
  }
  const nav = [
    { id: 'inspect', label: 'Inspection studio', icon: ScanLine },
    { id: 'queue', label: 'Review queue', icon: Layers3 },
    { id: 'model', label: 'Model & evaluation', icon: Box },
    { id: 'activity', label: 'Activity log', icon: History },
  ] as const;
  const stats = workspace?.stats;
  return (
    <div className="app-shell">
      {mobileNav && (
        <button
          className="nav-scrim"
          aria-label="Close navigation"
          onClick={() => setMobileNav(false)}
        />
      )}
      <aside className={`sidebar ${mobileNav ? 'open' : ''}`}>
        <a className="brand" href="/" aria-label="VisionGuard home">
          <span className="brand-mark">
            <ScanLine size={25} />
          </span>
          <div>
            visionguard<span>SEE THE DIFFERENCE.</span>
          </div>
        </a>
        <button className="workspace-switch" onClick={() => setConnectionOpen(true)}>
          <span className="workspace-avatar">N</span>
          <span>
            <strong>{workspace?.name || 'Quality workspace'}</strong>
            <small>Surface inspection</small>
          </span>
          <ChevronsUpDown size={14} />
        </button>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map((n) => (
            <button
              key={n.id}
              className={`nav-item ${view === n.id ? 'active' : ''}`}
              onClick={() => navigate(n.id)}
            >
              <n.icon size={18} />
              <span>{n.label}</span>
              {n.id === 'queue' && !!stats?.pending_review && <b>{stats.pending_review}</b>}
              {n.id === 'inspect' && <kbd>⌘ K</kbd>}
            </button>
          ))}
        </nav>
        <div className="nav-label batch-label">
          COLLECTIONS
          <button
            className="icon-button"
            aria-label="Create batch"
            onClick={() => setUploadOpen(true)}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="batch-nav">
          <button
            className={!batch ? 'selected' : ''}
            onClick={() => {
              setBatch('');
              setOffset(0);
              navigate('inspect');
            }}
          >
            <span className="collection-dot" />
            All inspections<span>{stats?.images || 0}</span>
          </button>
          {workspace?.batches.map((b, i) => (
            <button
              className={batch === b ? 'selected' : ''}
              key={b}
              onClick={() => {
                setBatch(b);
                setOffset(0);
                navigate('inspect');
              }}
            >
              <span className={`collection-dot dot-${i % 3}`} />
              <span className="truncate">{b}</span>
            </button>
          ))}
        </div>
        <div className="sidebar-footer">
          <div className="model-status">
            <div className={`live-dot ${workspace?.model.ready ? '' : 'loading'}`} />
            <div>
              <strong>
                {workspace?.model.ready ? 'Inspection engine online' : 'Engine initializing'}
              </strong>
              <small>
                {workspace?.model.ready
                  ? 'surface-v1 · CPU runtime'
                  : 'Your images stay in the queue'}
              </small>
            </div>
          </div>
          <div className="research-note">
            <ShieldCheck size={17} />
            <span>
              Research reference model
              <small>Human decisions stay in control.</small>
            </span>
          </div>
          <button className="profile" onClick={() => setConnectionOpen(true)}>
            <span className="avatar">QA</span>
            <span>
              <strong>
                {workspace?.identity.role === 'viewer' ? 'Quality viewer' : 'Quality operator'}
              </strong>
              <small>
                {workspace?.identity.auth_mode === 'oidc'
                  ? 'Organization workspace'
                  : 'Local workspace'}
              </small>
            </span>
            <Settings2 size={17} />
          </button>
        </div>
      </aside>
      <div className="app-body">
        <header className="topbar">
          <div className="breadcrumbs">
            <button
              className="icon-button mobile-menu"
              aria-label="Open navigation"
              onClick={() => setMobileNav(true)}
            >
              <Menu size={21} />
            </button>
            <span className="breadcrumb-icon">
              <Box size={14} />
            </span>
            <span>Surface operations</span>
            <ChevronRight size={13} />
            <strong>{nav.find((n) => n.id === view)?.label}</strong>
          </div>
          <div className="topbar-right">
            <span className="system-pill">
              <span className={`live-dot ${workspace?.model.ready ? '' : 'loading'}`} />
              {workspace?.model.ready ? 'All systems operational' : 'Model initializing'}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label="Workspace settings"
              onClick={() => setConnectionOpen(true)}
            >
              <SlidersHorizontal size={17} />
            </button>
            <span className="avatar small">QA</span>
          </div>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            <XCircle size={18} />
            <span>{error}</span>
            <button onClick={() => setError('')} aria-label="Dismiss error">
              <X size={16} />
            </button>
          </div>
        )}
        {notice && (
          <div className="toast" role="status">
            <CircleCheck size={17} />
            {notice}
          </div>
        )}
        {(view === 'inspect' || view === 'queue') && (
          <main className="main">
            <section className="page-heading">
              <div>
                <div className="eyebrow">
                  <span className="tiny-line" /> THE QUALITY WORKSPACE
                </div>
                <h1>
                  {view === 'inspect' ? (
                    <>
                      Quality, in <em>focus.</em>
                    </>
                  ) : (
                    <>
                      A second look.<em> A better decision.</em>
                    </>
                  )}
                </h1>
                <p>
                  {view === 'inspect'
                    ? 'Turn surface images into evidence. Inspect, understand, and review.'
                    : 'Model predictions are a starting point. Your review closes the loop.'}
                </p>
              </div>
              <div className="heading-actions">
                <button
                  className="button secondary"
                  onClick={() => download().catch((e) => setError(e.message))}
                >
                  <ArrowDownToLine size={16} />
                  Export results
                </button>
                <button
                  className="button primary"
                  disabled={!canEdit}
                  onClick={() => setUploadOpen(true)}
                >
                  <Plus size={18} />
                  New inspection
                </button>
              </div>
            </section>
            <section className="stats-grid">
              <Stat
                icon={<ScanLine size={17} />}
                title="IMAGES INSPECTED"
                value={stats?.complete ?? '—'}
                note={`${stats?.queued || 0} in processing queue`}
                accent="green"
              />
              <Stat
                icon={<Focus size={17} />}
                title="FLAGGED FOR REVIEW"
                value={stats?.suspect ?? '—'}
                note="Anomalous or borderline surfaces"
                accent="orange"
              />
              <Stat
                icon={<CheckCheck size={17} />}
                title="HUMAN REVIEWED"
                value={stats?.reviewed ?? '—'}
                note={`${stats?.pending_review || 0} awaiting a decision`}
                accent="purple"
              />
              <Stat
                icon={<Clock3 size={17} />}
                title="MEAN INFERENCE"
                value={
                  stats?.mean_latency_ms == null ? '—' : `${Math.round(stats.mean_latency_ms)} ms`
                }
                note="Actual image-level model time"
                accent="blue"
              />
            </section>
            <div className="inspection-controls">
              <div className="filter-tabs">
                {[
                  ['all', 'All inspections'],
                  ['suspect', 'Anomalies'],
                  ['pending', 'Unreviewed'],
                ].map(([id, label]) => (
                  <button
                    key={id}
                    className={filter === id ? 'selected' : ''}
                    onClick={() => {
                      setFilter(id);
                      setOffset(0);
                    }}
                  >
                    {label}
                    {id === 'all' && <span>{stats?.images || 0}</span>}
                  </button>
                ))}
              </div>
              <div className="search-tools">
                <label className="search">
                  <Search size={15} />
                  <input
                    ref={searchInput}
                    aria-label="Search inspections"
                    placeholder="Search images..."
                    value={search}
                    onChange={(e) => {
                      setSearch(e.target.value);
                      setOffset(0);
                    }}
                  />
                  <kbd>⌘ K</kbd>
                </label>
                <button
                  className="icon-button"
                  aria-label="Switch inspection view"
                  onClick={() => setView(view === 'inspect' ? 'queue' : 'inspect')}
                >
                  {view === 'inspect' ? <Layers3 size={18} /> : <Grid2X2 size={18} />}
                </button>
              </div>
            </div>
            {view === 'inspect' && selected ? (
              <div className="inspection-workspace">
                <div className="viewer-column">
                  <section className="viewer-card">
                    <header className="viewer-heading">
                      <span className="image-icon">
                        <FileImage size={17} />
                      </span>
                      <div>
                        <strong>{selected.filename}</strong>
                        <small>
                          {selected.batch}
                          <span>·</span>
                          {selected.width} × {selected.height} px
                        </small>
                      </div>
                      <span className={`state-tag ${selected.state}`}>
                        <span className="status-dot" />
                        {selected.state === 'complete' ? 'Inspection complete' : selected.state}
                      </span>
                      <button
                        className="icon-button"
                        aria-label="Delete selected inspection"
                        onClick={() => setDeleteOpen(true)}
                        disabled={!canEdit}
                      >
                        <MoreHorizontal size={18} />
                      </button>
                    </header>
                    <div className="viewer-toolbar">
                      <div className="segmented">
                        <button
                          className={!heatmap ? 'active' : ''}
                          onClick={() => setHeatmap(false)}
                        >
                          <FileImage size={14} />
                          Original
                        </button>
                        <button
                          disabled={selected.state !== 'complete'}
                          className={heatmap ? 'active' : ''}
                          onClick={() => setHeatmap(true)}
                        >
                          <Sparkles size={14} />
                          Anomaly map
                        </button>
                      </div>
                      <div>
                        <button
                          className={`tool-button ${boxes ? 'on' : ''}`}
                          onClick={() => setBoxes(!boxes)}
                          title="Show detected regions"
                          aria-label="Toggle detected regions"
                        >
                          <Focus size={16} />
                        </button>
                        <span className="toolbar-line" />
                        <button
                          className="tool-button"
                          onClick={() => setZoom(!zoom)}
                          aria-label="Toggle image zoom"
                        >
                          <ZoomIn size={16} />
                          <small>{zoom ? '150%' : 'Fit'}</small>
                        </button>
                      </div>
                    </div>
                    <div className={`image-canvas ${zoom ? 'zoomed' : ''}`}>
                      <span className="canvas-corner tl" />
                      <span className="canvas-corner tr" />
                      <span className="canvas-corner bl" />
                      <span className="canvas-corner br" />
                      {selected.state === 'complete' || !heatmap ? (
                        <div
                          className="image-stage"
                          style={{
                            aspectRatio: `${selected.width}/${selected.height}`,
                          }}
                        >
                          <Photo item={selected} heatmap={heatmap} />
                          {boxes &&
                            selected.state === 'complete' &&
                            selected.regions.map((r, i) => (
                              <div
                                className="region-box"
                                key={i}
                                style={{
                                  left: `${(r.x / selected.width) * 100}%`,
                                  top: `${(r.y / selected.height) * 100}%`,
                                  width: `${(r.width / selected.width) * 100}%`,
                                  height: `${(r.height / selected.height) * 100}%`,
                                }}
                              >
                                <span>{String(i + 1).padStart(2, '0')}</span>
                              </div>
                            ))}
                        </div>
                      ) : (
                        <Loader2 className="spin" />
                      )}
                      <span className="canvas-label">
                        <span className="live-dot" />
                        {heatmap ? 'FIXED-SCALE ANOMALY OVERLAY' : 'ORIGINAL SURFACE CAPTURE'}
                      </span>
                      {selected.state !== 'complete' && (
                        <div className="processing-overlay">
                          {selected.state === 'failed' ? (
                            <XCircle size={25} />
                          ) : (
                            <Loader2 className="spin" size={25} />
                          )}
                          <strong>
                            {selected.state === 'failed'
                              ? 'Inspection failed'
                              : 'Your image is in the inspection queue'}
                          </strong>
                          <p>
                            {selected.error ||
                              'The model will analyze this image when the engine is available.'}
                          </p>
                          {selected.state === 'failed' && (
                            <button
                              className="button secondary"
                              onClick={() =>
                                api(`/inspections/${selected.id}/retry`, 'POST')
                                  .then(() => refresh())
                                  .catch((e) => setError(e.message))
                              }
                            >
                              Retry inspection
                            </button>
                          )}
                        </div>
                      )}
                    </div>
                    <footer className="viewer-footer">
                      <span>
                        <ShieldCheck size={14} />
                        Source image preserved · overlay generated by model
                      </span>
                      <span>
                        {selected.model_version || 'Model pending'}
                        <span>·</span>
                        {selected.latency_ms == null
                          ? '—'
                          : `${Math.round(selected.latency_ms)} ms`}
                      </span>
                    </footer>
                  </section>
                  <section className="filmstrip-card">
                    <div className="section-heading">
                      <h3>
                        In this collection <span>{total}</span>
                      </h3>
                      <small>
                        Select an image to inspect
                        <ArrowRight size={13} />
                      </small>
                    </div>
                    <div className="filmstrip">
                      {items.slice(0, 12).map((item) => (
                        <button
                          key={item.id}
                          className={`film-card ${selected.id === item.id ? 'active' : ''}`}
                          onClick={() => {
                            setSelectedId(item.id);
                            setZoom(false);
                          }}
                        >
                          <div>
                            <Photo item={item} />
                            <span className={`film-dot ${item.decision || item.state}`} />
                          </div>
                          <strong>{item.filename}</strong>
                          <small>
                            {item.state === 'complete'
                              ? `${item.regions.length} regions`
                              : item.state}
                          </small>
                        </button>
                      ))}
                    </div>
                  </section>
                </div>
                <aside className="insight-panel">
                  <div className="insight-heading">
                    <h2>Inspection insights</h2>
                    <span className="ai-pill">
                      <Sparkles size={11} />
                      MODEL OUTPUT
                    </span>
                  </div>
                  <div className={`decision-card ${selected.decision || 'waiting'}`}>
                    <span className="decision-icon">
                      {selected.decision === 'clear' ? (
                        <CircleCheck size={21} />
                      ) : (
                        <Focus size={21} />
                      )}
                    </span>
                    <div>
                      <small>MODEL ASSESSMENT</small>
                      <h3>{decisionLabel(selected.decision)}</h3>
                      <p>
                        {selected.decision === 'clear'
                          ? 'The score falls below the learned reference threshold.'
                          : 'Review the highlighted regions before deciding on this item.'}
                      </p>
                    </div>
                  </div>
                  <div className="score-section">
                    <div>
                      <span>Anomaly score</span>
                      <strong>
                        {score(selected.score)}
                        <small> / {score(selected.threshold)} threshold</small>
                      </strong>
                    </div>
                    <div className="score-meter">
                      <span
                        style={{
                          width: `${Math.min(100, ((selected.score || 0) / ((selected.threshold || 1) * 2)) * 100)}%`,
                        }}
                      />
                      <i />
                    </div>
                    <div className="meter-labels">
                      <span>Within reference</span>
                      <span>Unusual</span>
                    </div>
                    <p>
                      A distance from learned normal surfaces.
                      <br />
                      This score is not a defect probability.
                    </p>
                  </div>
                  <div className="panel-divider" />
                  <div className="section-heading">
                    <h3>Detected regions</h3>
                    <span className="count-pill">{selected.regions.length}</span>
                  </div>
                  {selected.regions.length ? (
                    <div className="region-list">
                      {selected.regions.slice(0, 5).map((r, i) => (
                        <button
                          key={i}
                          onClick={() => {
                            setBoxes(true);
                            setHeatmap(true);
                          }}
                        >
                          <span className="region-number">{String(i + 1).padStart(2, '0')}</span>
                          <span>
                            <strong>Surface anomaly</strong>
                            <small>
                              {(r.area_fraction * 100).toFixed(2)}% of surface · score{' '}
                              {r.peak_score.toFixed(1)}
                            </small>
                          </span>
                          <ArrowUpRight size={14} />
                        </button>
                      ))}
                    </div>
                  ) : (
                    <div className="empty-regions">
                      <ScanLine size={21} />
                      <span>
                        {selected.state === 'complete'
                          ? 'No regions above the localization threshold.'
                          : 'Regions appear after inspection.'}
                      </span>
                    </div>
                  )}
                  <div className="panel-divider" />
                  <div className="section-heading">
                    <h3>Human review</h3>
                    <span className={`review-tag ${selected.review}`}>
                      {reviewLabel(selected.review)}
                    </span>
                  </div>
                  <p className="panel-copy">
                    Confirm the item’s disposition. Reviews are recorded separately from model
                    predictions.
                  </p>
                  <label className="note-label">
                    Review note
                    <textarea
                      aria-label="Review note"
                      placeholder="What did you observe?"
                      value={note}
                      disabled={!canEdit}
                      onChange={(e) => setNote(e.target.value)}
                    />
                  </label>
                  <div className="review-actions">
                    <button
                      className="button accept"
                      disabled={!canEdit || saving || selected.state !== 'complete'}
                      onClick={() => saveReview('accepted')}
                    >
                      <Check size={15} />
                      Accept item
                    </button>
                    <button
                      className="button reject"
                      disabled={!canEdit || saving || selected.state !== 'complete'}
                      onClick={() => saveReview('rejected')}
                    >
                      <X size={15} />
                      Reject item
                    </button>
                  </div>
                  <button
                    className="escalate"
                    disabled={!canEdit || saving || selected.state !== 'complete'}
                    onClick={() => saveReview('needs_attention')}
                  >
                    <Flag size={13} />
                    Escalate for a second look
                    <ArrowUpRight size={12} />
                  </button>
                  <div className="panel-footnote">
                    <ShieldCheck size={14} />
                    <span>
                      Decision support, with a human in the loop.
                      <br />
                      Predictions can miss defects and flag normal areas.
                    </span>
                  </div>
                </aside>
              </div>
            ) : view === 'queue' && items.length ? (
              <section className="table-card">
                <table>
                  <thead>
                    <tr>
                      <th>Surface image</th>
                      <th>Batch</th>
                      <th>Model assessment</th>
                      <th>Anomaly score</th>
                      <th>Human review</th>
                      <th>Inspected</th>
                      <th />
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item) => (
                      <tr key={item.id}>
                        <td>
                          <button
                            className="table-image"
                            onClick={() => {
                              setSelectedId(item.id);
                              setView('inspect');
                            }}
                          >
                            <Photo item={item} />
                            <span>
                              <strong>{item.filename}</strong>
                              <small>
                                {item.width} × {item.height} px
                              </small>
                            </span>
                          </button>
                        </td>
                        <td>{item.batch}</td>
                        <td>
                          <span className={`assessment-tag ${item.decision}`}>
                            {item.state === 'complete' ? decisionLabel(item.decision) : item.state}
                          </span>
                        </td>
                        <td>{score(item.score)}</td>
                        <td>
                          <span className={`review-tag ${item.review}`}>
                            {reviewLabel(item.review)}
                          </span>
                        </td>
                        <td>{date(item.created_at)}</td>
                        <td>
                          <button
                            className="icon-button"
                            aria-label={`Inspect ${item.filename}`}
                            onClick={() => {
                              setSelectedId(item.id);
                              setView('inspect');
                            }}
                          >
                            <ArrowUpRight size={17} />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            ) : (
              <section className="empty-state">
                <span className="empty-icon">
                  <ScanLine size={39} />
                </span>
                <span className="eyebrow">YOUR NEXT DETAIL STARTS HERE</span>
                <h2>
                  {search || filter !== 'all'
                    ? 'No matching inspections.'
                    : 'A clearer picture of quality.'}
                </h2>
                <p>
                  {search || filter !== 'all'
                    ? 'Try another search or filter.'
                    : 'Upload surface images to find unusual regions and review the evidence.'}
                </p>
                <button
                  className="button primary"
                  disabled={!canEdit}
                  onClick={() => setUploadOpen(true)}
                >
                  <UploadCloud size={18} />
                  Upload your first images
                </button>
                <small>PNG, JPEG, WebP · up to 10 MB per image</small>
              </section>
            )}
            <footer className="page-footer">
              <span>
                <span className="live-dot" />{' '}
                {workspace?.model.ready
                  ? 'Connected to real model inference'
                  : 'Model is not ready'}
                <span className="footer-divider" />
                Local inspection workspace
              </span>
              <div>
                <span>
                  {total ? `${offset + 1}–${Math.min(offset + 30, total)} of ${total}` : '0 images'}
                </span>
                <button
                  className="icon-button"
                  disabled={offset === 0}
                  aria-label="Previous page"
                  onClick={() => setOffset(Math.max(0, offset - 30))}
                >
                  <ChevronLeft size={15} />
                </button>
                <button
                  className="icon-button"
                  disabled={offset + 30 >= total}
                  aria-label="Next page"
                  onClick={() => setOffset(offset + 30)}
                >
                  <ChevronRight size={15} />
                </button>
              </div>
            </footer>
          </main>
        )}
        {view === 'model' && (
          <main className="main model-page">
            <section className="page-heading">
              <div>
                <div className="eyebrow">
                  <span className="tiny-line" /> MEASURED, NOT ASSUMED
                </div>
                <h1>
                  Know your <em>model.</em>
                </h1>
                <p>Trace the reference data, understand the threshold, inspect the results.</p>
              </div>
              <span className="model-version">
                <GitBranch size={15} />
                {workspace?.model.metadata?.version || 'No model loaded'}
              </span>
            </section>
            {evaluation?.available ? (
              <>
                <section className="stats-grid">
                  <Stat
                    icon={<Activity size={17} />}
                    title="IMAGE AUROC"
                    value={percent(evaluation.test.auroc)}
                    note={`${evaluation.test.images} official test images`}
                    accent="green"
                  />
                  <Stat
                    icon={<Focus size={17} />}
                    title="DEFECT RECALL"
                    value={percent(evaluation.test.recall)}
                    note="At the validation-selected threshold"
                    accent="orange"
                  />
                  <Stat
                    icon={<CheckCheck size={17} />}
                    title="DEFECT PRECISION"
                    value={percent(evaluation.test.precision)}
                    note="Flagged images that contain defects"
                    accent="purple"
                  />
                  <Stat
                    icon={<Clock3 size={17} />}
                    title="BATCHED MODEL TIME"
                    value={`${Math.round(evaluation.latency_ms.mean)} ms`}
                    note={`Per image · batch size ${evaluation.latency_ms.batch_size}`}
                    accent="blue"
                  />
                </section>
                <div className="model-grid">
                  <section className="card model-profile">
                    <div className="section-heading">
                      <h2>The normal-reference model</h2>
                      <Box size={20} />
                    </div>
                    <p>
                      PaDiM-style anomaly localization uses a pretrained ResNet18 to describe local
                      texture, then learns normal patch distributions from reference images.
                    </p>
                    <div className="model-flow">
                      {[
                        ['01', 'Extract', 'Frozen vision features'],
                        ['02', 'Learn', 'Normal-patch statistics'],
                        ['03', 'Compare', 'Mahalanobis distance'],
                        ['04', 'Localize', 'Heatmap + regions'],
                      ].map(([n, title, text]) => (
                        <div key={n}>
                          <span>{n}</span>
                          <strong>{title}</strong>
                          <small>{text}</small>
                        </div>
                      ))}
                    </div>
                    <dl>
                      {[
                        ['Backbone', evaluation.model.backbone],
                        ['Reference images', String(evaluation.fitted_normal_images)],
                        ['Input resolution', evaluation.model.input_size.join(' × ') + ' px'],
                        ['Image threshold', evaluation.model.image_threshold.toFixed(3)],
                        ['Localization threshold', evaluation.model.pixel_threshold.toFixed(3)],
                        ['Feature dimensions', String(evaluation.model.dimensions)],
                      ].map(([k, v]) => (
                        <div key={k}>
                          <dt>{k}</dt>
                          <dd>{v}</dd>
                        </div>
                      ))}
                    </dl>
                  </section>
                  <section className="card confusion-card">
                    <div className="section-heading">
                      <h2>Where it gets things right—and wrong</h2>
                      <Focus size={19} />
                    </div>
                    <p>
                      Official test split. The image threshold was selected using validation images
                      only.
                    </p>
                    <div className="matrix">
                      <span />
                      <span>Predicted normal</span>
                      <span>Predicted anomaly</span>
                      <span>Actually normal</span>
                      <div className="correct">
                        <strong>{evaluation.test.confusion.true_negative}</strong>
                        <small>True negatives</small>
                      </div>
                      <div className="incorrect">
                        <strong>{evaluation.test.confusion.false_positive}</strong>
                        <small>False alarms</small>
                      </div>
                      <span>Actually defective</span>
                      <div className="incorrect">
                        <strong>{evaluation.test.confusion.false_negative}</strong>
                        <small>Missed defects</small>
                      </div>
                      <div className="correct">
                        <strong>{evaluation.test.confusion.true_positive}</strong>
                        <small>True positives</small>
                      </div>
                    </div>
                    <div className="metric-pairs">
                      <span>
                        Image average precision
                        <strong>{percent(evaluation.test.average_precision)}</strong>
                      </span>
                      <span>
                        Pixel AUROC, sampled
                        <strong>{percent(evaluation.pixel_test_auroc)}</strong>
                      </span>
                    </div>
                  </section>
                  <section className="card dataset-card">
                    <div className="section-heading">
                      <h2>Real surfaces. Recorded provenance.</h2>
                      <Database size={19} />
                    </div>
                    <p>
                      KolektorSDD2 · industrial images and pixel annotations from Kolektor Group and
                      ViCoS Lab.
                    </p>
                    <div className="split-grid">
                      <div>
                        <strong>{evaluation.train_images}</strong>
                        <span>Training partition</span>
                      </div>
                      <div>
                        <strong>{evaluation.validation.images}</strong>
                        <span>Validation images</span>
                      </div>
                      <div>
                        <strong>{evaluation.test.images}</strong>
                        <span>Official test images</span>
                      </div>
                    </div>
                    <div className="callout">
                      <ShieldCheck size={19} />
                      <p>
                        The reference statistics use normal training images only. Validation chooses
                        the operating thresholds. Test images are reserved for measurement.
                      </p>
                    </div>
                    <p className="license-note">
                      Data: CC BY-NC-SA 4.0 · noncommercial reference benchmark. The model is
                      specific to this surface family and capture setup.
                    </p>
                  </section>
                  <section className="card limitations-card">
                    <div className="section-heading">
                      <h2>Read the limits with the results</h2>
                      <Eye size={19} />
                    </div>
                    <ul>
                      <li>
                        Surface anomalies are localized, not classified into named defect types.
                      </li>
                      <li>Anomaly scores are distances, not calibrated probabilities.</li>
                      <li>
                        Different products, lighting, and camera positions need their own normal
                        reference and evaluation.
                      </li>
                      <li>{evaluation.pixel_evaluation}.</li>
                      <li>{evaluation.limits}</li>
                    </ul>
                    <div className="callout neutral">
                      <Clock3 size={18} />
                      <p>
                        Timing covers {evaluation.latency_ms.includes}. It does not establish
                        concurrent API capacity or a factory SLA.
                      </p>
                    </div>
                  </section>
                </div>
              </>
            ) : (
              <section className="empty-state">
                <Box size={39} />
                <h2>No evaluation has been recorded.</h2>
                <p>
                  Fit a model with python -m visionguard.training, then restart the app to load the
                  artifact.
                </p>
              </section>
            )}
          </main>
        )}
        {view === 'activity' && (
          <main className="main">
            <section className="page-heading">
              <div>
                <div className="eyebrow">
                  <span className="tiny-line" /> A TRACEABLE WORKSPACE
                </div>
                <h1>
                  Every decision,<em> recorded.</em>
                </h1>
                <p>Uploads, human reviews, and deletions in this workspace.</p>
              </div>
              <button
                className="button secondary"
                onClick={() =>
                  api<typeof audits>('/audit')
                    .then(setAudits)
                    .catch((e) => setError(e.message))
                }
              >
                <History size={16} />
                Refresh activity
              </button>
            </section>
            <section className="card activity-list">
              {audits.length ? (
                audits.map((row) => (
                  <div key={row.id}>
                    <span className="activity-icon">
                      {row.action === 'review' ? (
                        <CheckCheck size={18} />
                      ) : row.action === 'delete' ? (
                        <Trash2 size={18} />
                      ) : (
                        <UploadCloud size={18} />
                      )}
                    </span>
                    <div>
                      <strong>
                        {row.action === 'review'
                          ? `Item ${String(row.detail.after).replace('_', ' ')}`
                          : row.action === 'upload'
                            ? 'Image added to inspection queue'
                            : 'Inspection deleted'}
                      </strong>
                      <p>
                        {row.user} · {row.inspection_id.slice(0, 8)}
                      </p>
                      {typeof row.detail.note === 'string' && row.detail.note && (
                        <blockquote>{row.detail.note}</blockquote>
                      )}
                    </div>
                    <time>{date(row.created_at)}</time>
                  </div>
                ))
              ) : (
                <div className="activity-empty">
                  Activity will appear after images are uploaded or reviewed.
                </div>
              )}
            </section>
          </main>
        )}
      </div>
      {uploadOpen && (
        <Modal
          title="Bring the details into focus."
          description="Add surface images to a named batch. The original capture is preserved and processed by the inspection engine."
          close={() => {
            if (!uploading) setUploadOpen(false);
          }}
        >
          <form onSubmit={startUpload}>
            <label className="form-label">
              Batch name
              <input
                required
                maxLength={120}
                value={batchName}
                onChange={(e) => setBatchName(e.target.value)}
              />
            </label>
            <div
              className="dropzone"
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                e.preventDefault();
                chooseFiles(Array.from(e.dataTransfer.files));
              }}
            >
              <span className="upload-symbol">
                <UploadCloud size={31} />
              </span>
              <h3>Drop your surface images here</h3>
              <p>or choose files from your computer</p>
              <button
                className="button secondary"
                type="button"
                onClick={() => uploadInput.current?.click()}
              >
                <Plus size={15} />
                Choose images
              </button>
              <input
                ref={uploadInput}
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                aria-label="Choose surface images"
                onChange={(e) => chooseFiles(Array.from(e.target.files || []))}
              />
              <small>PNG, JPEG, WebP · 10 MB each · up to 20 images</small>
            </div>
            {files.length > 0 && (
              <div className="selected-files">
                {files.slice(0, 5).map((file, i) => (
                  <div key={i}>
                    <FileImage size={16} />
                    <span>{file.name}</span>
                    <small>{(file.size / 1024).toFixed(0)} KB</small>
                  </div>
                ))}
                {files.length > 5 && <small>+ {files.length - 5} more images</small>}
              </div>
            )}
            <div className="upload-note">
              <ShieldCheck size={16} />
              <span>
                New products need a matching normal-reference model. This model was fitted on
                KolektorSDD2 surfaces.
              </span>
            </div>
            <footer className="modal-actions">
              <button
                className="button secondary"
                type="button"
                disabled={uploading}
                onClick={() => setUploadOpen(false)}
              >
                Cancel
              </button>
              <button
                className="button primary"
                type="submit"
                disabled={!files.length || uploading || !batchName.trim()}
              >
                {uploading ? <Loader2 className="spin" size={16} /> : <ScanLine size={17} />}{' '}
                {uploading
                  ? progress
                  : `Inspect ${files.length || ''} ${files.length === 1 ? 'image' : 'images'}`}
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {connectionOpen && (
        <Modal
          title="Workspace connection"
          description="Local access is restricted to this computer. Hosted workspaces require an organization-issued access token."
          close={() => setConnectionOpen(false)}
        >
          <div className="connection-summary">
            <span className="live-dot" />
            <strong>
              {workspace?.identity.auth_mode === 'local'
                ? 'Local workspace · no token required'
                : 'Organization identity'}
            </strong>
            <small>{workspace?.name || 'Not connected'}</small>
          </div>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              setToken(accessToken);
              setItems([]);
              setConnectionOpen(false);
              void refresh();
            }}
          >
            <label className="form-label">
              Organization access token
              <input
                type="password"
                value={accessToken}
                onChange={(e) => setAccessToken(e.target.value)}
                autoComplete="off"
                placeholder="Paste an access token for hosted mode"
              />
            </label>
            <p className="token-note">
              Kept in browser memory only. Your server verifies issuer, audience, signature, expiry,
              workspace and roles.
            </p>
            <footer className="modal-actions">
              <button
                className="button secondary"
                type="button"
                onClick={() => {
                  setToken('');
                  setAccessToken('');
                  setConnectionOpen(false);
                  void refresh();
                }}
              >
                Clear token
              </button>
              <button className="button primary" type="submit">
                Connect workspace
                <ArrowRight size={16} />
              </button>
            </footer>
          </form>
        </Modal>
      )}
      {deleteOpen && selected && (
        <Modal
          title="Delete this inspection?"
          description="This removes the source image and overlay. A deletion event remains in the workspace audit trail."
          close={() => setDeleteOpen(false)}
        >
          <p className="delete-name">{selected.filename}</p>
          <footer className="modal-actions">
            <button className="button secondary" onClick={() => setDeleteOpen(false)}>
              Keep inspection
            </button>
            <button className="button danger" onClick={() => void deleteInspection()}>
              <Trash2 size={16} />
              Delete inspection
            </button>
          </footer>
        </Modal>
      )}
    </div>
  );
}
function Stat({
  icon,
  title,
  value,
  note,
  accent,
}: {
  icon: ReactNode;
  title: string;
  value: string | number;
  note: string;
  accent: string;
}) {
  return (
    <div className={`stat-card ${accent}`}>
      <div>
        <span>{title}</span>
        <i>{icon}</i>
      </div>
      <strong>{value}</strong>
      <p>
        <span className="mini-dot" />
        {note}
      </p>
    </div>
  );
}
