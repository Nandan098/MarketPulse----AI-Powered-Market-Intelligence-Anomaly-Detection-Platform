import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Activity, AlertTriangle, ArrowDownRight, ArrowUpRight, BarChart3,
  BellRing, CheckCircle2, ChevronDown, CircleHelp, Database, ExternalLink,
  FileUp, Gauge, RefreshCw, Search, ShieldAlert, Sparkles, TrendingUp,
} from 'lucide-react';
import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';

const API_BASE = (import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000').replace(/\/$/, '');
const FALLBACK_SYMBOLS = ['AAPL', 'MSFT', 'NVDA', 'TSLA'];
const fmtCurrency = (n) => Number.isFinite(Number(n)) ? new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 2 }).format(Number(n)) : '—';
const fmtNumber = (n) => Number.isFinite(Number(n)) ? new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 }).format(Number(n)) : '—';
const fmtPercent = (n) => `${Number(n) > 0 ? '+' : ''}${Number(n || 0).toFixed(2)}%`;
const fmtDate = (value) => new Date(`${value}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });

async function getJson(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(payload.detail || `Request failed (${response.status})`);
  return payload;
}

function MetricCard({ label, value, sub, icon: Icon, trend, tone = 'neutral' }) {
  return (
    <div className="metric-card">
      <div className="metric-top">
        <span className="metric-label">{label}</span>
        <span className={`metric-icon ${tone}`}><Icon size={18} /></span>
      </div>
      <div className="metric-value">{value}</div>
      <div className="metric-footer">
        {trend && <span className={`metric-trend ${trend > 0 ? 'up' : trend < 0 ? 'down' : ''}`}>{trend > 0 ? <ArrowUpRight size={13} /> : trend < 0 ? <ArrowDownRight size={13} /> : null}{fmtPercent(trend)}</span>}
        <span>{sub}</span>
      </div>
    </div>
  );
}

function PriceTooltip({ active, payload, label }) {
  if (!active || !payload?.length) return null;
  const row = payload[0].payload;
  return (
    <div className="chart-tooltip">
      <div className="tooltip-date">{label ? new Date(`${label}T12:00:00`).toLocaleDateString('en-US', { month: 'long', day: 'numeric', year: 'numeric' }) : ''}</div>
      <div className="tooltip-price">{fmtCurrency(row.close)}</div>
      <div className="tooltip-volume">Volume {Number(row.volume).toLocaleString('en-US')}</div>
      {row.hasAnomaly && <span className="tooltip-flag"><AlertTriangle size={12} /> Anomaly flagged</span>}
    </div>
  );
}

function SentimentBadge({ sentiment }) {
  const label = sentiment || 'Neutral';
  return <span className={`sentiment-badge ${label.toLowerCase()}`}><span />{label}</span>;
}

function App() {
  const [symbol, setSymbol] = useState('AAPL');
  const [symbols, setSymbols] = useState(FALLBACK_SYMBOLS);
  const [market, setMarket] = useState(null);
  const [summary, setSummary] = useState(null);
  const [anomalies, setAnomalies] = useState([]);
  const [news, setNews] = useState([]);
  const [busy, setBusy] = useState(false);
  const [liveBusy, setLiveBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [period, setPeriod] = useState('6M');
  const [activeNav, setActiveNav] = useState('Overview');

  const loadData = useCallback(async () => {
    setBusy(true);
    setError('');
    try {
      const [symbolRows, marketData, summaryData, anomalyData, newsData] = await Promise.all([
        getJson('/api/symbols'),
        getJson(`/api/market/${encodeURIComponent(symbol)}?days=220`),
        getJson(`/api/summary?symbol=${encodeURIComponent(symbol)}&days=220`),
        getJson(`/api/anomalies?symbol=${encodeURIComponent(symbol)}&days=220&limit=50`),
        getJson(`/api/news?symbol=${encodeURIComponent(symbol)}&limit=10`),
      ]);
      const nextSymbols = symbolRows.map((row) => row.symbol);
      if (nextSymbols.length) setSymbols(nextSymbols);
      setMarket(marketData);
      setSummary(summaryData);
      setAnomalies(anomalyData.anomalies || []);
      setNews(newsData || []);
      setNotice('');
    } catch (err) {
      setError(`${err.message}. Make sure the backend is running at ${API_BASE}.`);
    } finally {
      setBusy(false);
    }
  }, [symbol]);

  useEffect(() => { loadData(); }, [loadData]);

  const chartData = useMemo(() => {
    const prices = market?.prices || [];
    const days = period === '1M' ? 22 : period === '3M' ? 66 : period === '6M' ? 132 : prices.length;
    const selected = prices.slice(-days);
    const anomalyDates = new Set(anomalies.map((a) => a.date));
    return selected.map((point) => ({ ...point, hasAnomaly: anomalyDates.has(point.date), shortDate: fmtDate(point.date) }));
  }, [market, anomalies, period]);

  const chartStats = useMemo(() => {
    if (!chartData.length) return { first: null, last: null, pct: 0 };
    const first = chartData[0].close;
    const last = chartData[chartData.length - 1].close;
    return { first, last, pct: first ? ((last / first) - 1) * 100 : 0 };
  }, [chartData]);

  const liveIngest = async () => {
    setLiveBusy(true);
    setError('');
    setNotice('');
    try {
      const result = await getJson(`/api/ingest/${encodeURIComponent(symbol)}?period=1y`, { method: 'POST' });
      setNotice(`${result.message} Source: ${result.source}.`);
      await loadData();
    } catch (err) {
      setError(`${err.message}. Live ingestion requires the optional yfinance package and internet access.`);
    } finally {
      setLiveBusy(false);
    }
  };

  const importNews = async (event) => {
    const file = event.target.files?.[0];
    if (!file) return;
    const form = new FormData();
    form.append('file', file);
    setNotice('');
    setError('');
    try {
      const result = await getJson('/api/news/import', { method: 'POST', body: form });
      setNotice(result.message);
      await loadData();
    } catch (err) {
      setError(err.message);
    } finally {
      event.target.value = '';
    }
  };

  const sourceLabel = summary?.source_label || 'Connecting to data source';

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-lockup">
          <div className="brand-mark"><Activity size={21} strokeWidth={2.6} /></div>
          <div><div className="brand-name">marketpulse<span>.</span></div><div className="brand-caption">MARKET INTELLIGENCE</div></div>
        </div>
        <div className="workspace-label">WORKSPACE</div>
        <nav className="side-nav" aria-label="Primary navigation">
          {[['Overview', BarChart3], ['Market Monitor', TrendingUp], ['Risk Signals', ShieldAlert], ['News Sentiment', Sparkles]].map(([label, Icon]) => (
            <button className={`nav-item ${activeNav === label ? 'selected' : ''}`} key={label} onClick={() => { setActiveNav(label); const targetId = ({ 'Overview': 'overview', 'Market Monitor': 'market-monitor', 'Risk Signals': 'risk-signals', 'News Sentiment': 'news-sentiment' })[label]; document.getElementById(targetId)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }}>
              <Icon size={17} /><span>{label}</span>{label === 'Risk Signals' && <span className="nav-count">{anomalies.length}</span>}
            </button>
          ))}
        </nav>
        <div className="sidebar-spacer" />
        <div className="sidebar-info">
          <div className="sidebar-info-icon"><CircleHelp size={17} /></div>
          <div><strong>Exploratory analytics</strong><p>Signals are not investment advice or proof of wrongdoing.</p></div>
        </div>
        <div className="sidebar-user">
          <div className="avatar">MP</div><div><strong>MarketPulse Demo</strong><span>Local workspace</span></div><ChevronDown size={15} className="user-chevron" />
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span className="crumb-slash">/</span><strong>{activeNav}</strong></div>
          <div className="topbar-actions">
            <span className="market-status"><span className="status-dot" /> DEMO ENVIRONMENT</span>
            <button className="icon-button" title="Refresh dashboard" onClick={loadData} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /></button>
            <button className="avatar small-avatar" title="MarketPulse demo">MP</button>
          </div>
        </header>

        <div className="page-wrap">
          <section className="page-heading" id="overview">
            <div>
              <div className="eyebrow">MARKET SURVEILLANCE / OVERVIEW</div>
              <h1>Market intelligence, <span>at a glance.</span></h1>
              <p className="page-subtitle">Monitor price movement, detect unusual activity, and review sentiment signals in one workspace.</p>
            </div>
            <div className="heading-actions">
              <label className="select-wrap" aria-label="Select market symbol">
                <Search size={16} />
                <select value={symbol} onChange={(e) => setSymbol(e.target.value)}>
                  {[...new Set([...symbols, symbol])].map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
                <ChevronDown size={14} />
              </label>
              <button className="button-primary" onClick={liveIngest} disabled={liveBusy || busy}><RefreshCw size={15} className={liveBusy ? 'spin' : ''} />{liveBusy ? 'Syncing…' : 'Sync live data'}</button>
            </div>
          </section>

          {(error || notice) && <div className={`notice ${error ? 'error' : 'success'}`} role="status">{error ? <AlertTriangle size={17} /> : <CheckCircle2 size={17} />}{error || notice}<button onClick={() => { setError(''); setNotice(''); }} aria-label="Dismiss message">×</button></div>}

          <div className="source-banner"><Database size={15} /><span><strong>{sourceLabel}</strong> <span className="source-detail">— bundled values are synthetic examples; sync live data to fetch Yahoo Finance history.</span></span><span className="source-badge">SOURCE AWARE</span></div>

          <section className="metric-grid" aria-label="Market summary">
            <MetricCard label="LATEST CLOSE" value={fmtCurrency(summary?.latest_close)} sub={summary?.latest_date ? `As of ${fmtDate(summary.latest_date)}` : 'Waiting for data'} icon={Activity} tone="blue" />
            <MetricCard label="DAILY CHANGE" value={fmtPercent(summary?.day_change_pct || 0)} sub="vs. previous session" icon={summary?.day_change_pct >= 0 ? ArrowUpRight : ArrowDownRight} trend={summary?.day_change_pct || 0} tone={summary?.day_change_pct >= 0 ? 'green' : 'red'} />
            <MetricCard label="AVG. DAILY VOLUME" value={fmtNumber(summary?.average_volume_20d)} sub="20-session average" icon={BarChart3} tone="violet" />
            <MetricCard label="RISK SIGNALS" value={summary?.anomaly_count ?? '—'} sub="detected in selected window" icon={BellRing} tone="amber" />
          </section>

          <section className="content-grid">
            <div className="panel price-panel" id="market-monitor">
              <div className="panel-heading">
                <div><div className="panel-kicker"><span className="live-indicator" /> PRICE EXPLORER</div><h2>{symbol} <span className="panel-unit">/ USD</span></h2></div>
                <div className="period-tabs" role="group" aria-label="Chart period">
                  {['1M', '3M', '6M', '1Y'].map((p) => <button key={p} onClick={() => setPeriod(p)} className={period === p ? 'active' : ''}>{p}</button>)}
                </div>
              </div>
              <div className="chart-summary"><span className="chart-main-price">{fmtCurrency(chartStats.last)}</span><span className={`chart-change ${chartStats.pct >= 0 ? 'positive' : 'negative'}`}>{chartStats.pct >= 0 ? '+' : ''}{chartStats.pct.toFixed(2)}% <span>for selected period</span></span></div>
              <div className="chart-container">
                {chartData.length ? <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 10, right: 12, left: -12, bottom: 0 }}>
                    <defs><linearGradient id="priceFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#5a83f6" stopOpacity={0.26} /><stop offset="96%" stopColor="#5a83f6" stopOpacity={0.01} /></linearGradient></defs>
                    <CartesianGrid strokeDasharray="3 5" vertical={false} stroke="#e9edf4" />
                    <XAxis dataKey="date" tickFormatter={fmtDate} axisLine={false} tickLine={false} tick={{ fill: '#8c96a8', fontSize: 11 }} minTickGap={35} />
                    <YAxis domain={['auto', 'auto']} orientation="right" axisLine={false} tickLine={false} tick={{ fill: '#8c96a8', fontSize: 11 }} tickFormatter={(v) => `$${Number(v).toFixed(0)}`} width={52} />
                    <Tooltip content={<PriceTooltip />} />
                    <Area type="monotone" dataKey="close" stroke="#4e74e8" strokeWidth={2.25} fill="url(#priceFill)" activeDot={{ r: 4, fill: '#4e74e8', stroke: '#fff', strokeWidth: 2 }} dot={(props) => {
                      const point = chartData[props.index];
                      if (!point?.hasAnomaly) return <g key={`dot-${props.index}`} />;
                      return <circle key={`dot-${props.index}`} cx={props.cx} cy={props.cy} r={4} fill="#ed9c42" stroke="#fff" strokeWidth={2} />;
                    }} />
                  </AreaChart>
                </ResponsiveContainer> : <div className="empty-state"><Activity size={24} /><span>Price history will appear here when the API is connected.</span></div>}
              </div>
              <div className="chart-legend"><span><i className="legend-line" /> Closing price</span><span><i className="legend-dot" /> Flagged session</span><span className="chart-legend-note">Daily data · exploratory only</span></div>
            </div>

            <div className="panel signal-panel" id="risk-signals">
              <div className="panel-heading"><div><div className="panel-kicker"><ShieldAlert size={13} /> DETECTION ENGINE</div><h2>Risk signals</h2></div><span className="signal-count">{anomalies.length} <span>found</span></span></div>
              <p className="panel-description">Sessions marked by statistical thresholds and an Isolation Forest model.</p>
              <div className="signal-list">
                {anomalies.slice(0, 5).map((item) => (
                  <div className="signal-item" key={`${item.symbol}-${item.date}`}>
                    <div className={`signal-severity ${item.severity.toLowerCase()}`}><AlertTriangle size={15} /></div>
                    <div className="signal-copy"><div className="signal-title-row"><strong>{item.symbol} · {fmtDate(item.date)}</strong><span className={`severity-label ${item.severity.toLowerCase()}`}>{item.severity}</span></div><p>{item.reason}</p><span className="signal-method">{item.detector}</span></div>
                  </div>
                ))}
                {!anomalies.length && <div className="empty-state compact"><CheckCircle2 size={22} /><span>No flagged sessions in this window.</span></div>}
              </div>
              <div className="panel-footnote"><CircleHelp size={14} /> Flags indicate unusual values, not wrongdoing.</div>
            </div>
          </section>

          <section className="bottom-grid">
            <div className="panel table-panel">
              <div className="panel-heading"><div><div className="panel-kicker"><Gauge size={13} /> ALERT LOG</div><h2>Recent anomaly events</h2></div><span className="small-muted">{symbol} · newest first</span></div>
              <div className="table-scroll"><table><thead><tr><th>SESSION</th><th>TYPE / REASON</th><th>CLOSE</th><th>VOL. VS BASELINE</th><th>SEVERITY</th></tr></thead><tbody>
                {anomalies.slice(0, 8).map((item) => <tr key={`${item.symbol}-${item.date}-table`}><td className="date-cell">{fmtDate(item.date)}, {new Date(`${item.date}T12:00:00`).getFullYear()}</td><td><div className="event-title">Unusual market activity</div><div className="event-detail">{item.reason}</div></td><td className="numeric-cell">{fmtCurrency(item.close)}</td><td className="numeric-cell">{Number(item.volume_ratio).toFixed(1)}×</td><td><span className={`severity-pill ${item.severity.toLowerCase()}`}>{item.severity}</span></td></tr>)}
                {!anomalies.length && <tr><td colSpan="5" className="empty-table">No anomaly events found for this symbol.</td></tr>}
              </tbody></table></div>
              <div className="table-footer"><span>Showing {Math.min(8, anomalies.length)} of {anomalies.length} detected events</span><span className="table-footer-note">Computed from selected history</span></div>
            </div>

            <div className="panel news-panel" id="news-sentiment">
              <div className="panel-heading"><div><div className="panel-kicker"><Sparkles size={13} /> TEXT ANALYTICS</div><h2>News sentiment</h2></div><label className="upload-news" title="Import news CSV"><FileUp size={15} /><span>Import CSV</span><input type="file" accept=".csv,text/csv" onChange={importNews} /></label></div>
              <p className="panel-description">Lexicon-based sentiment scoring over headlines and summaries.</p>
              <div className="news-list">
                {news.slice(0, 4).map((item) => <article className="news-item" key={item.id}>
                  <div className="news-meta"><span>{item.source.includes('DEMO') ? 'DEMO SAMPLE' : item.source}</span><span>{new Date(item.published_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span></div>
                  <div className="news-title">{item.url ? <a href={item.url} target="_blank" rel="noreferrer">{item.title} <ExternalLink size={12} /></a> : item.title}</div>
                  <div className="news-bottom"><SentimentBadge sentiment={item.sentiment} /><span className="score-label">Score {Number(item.sentiment_score).toFixed(2)}</span></div>
                </article>)}
                {!news.length && <div className="empty-state compact"><Sparkles size={22} /><span>No articles imported for {symbol}. Use Import CSV to load news data.</span></div>}
              </div>
              <div className="news-disclaimer">Sentiment is a rough text signal; it does not establish causation or forecast returns.</div>
            </div>
          </section>

          <footer className="page-footer"><span>MarketPulse <span className="footer-dot">•</span> Internship portfolio project</span><span><span className="footer-dot">●</span> API status: {error ? 'Needs attention' : busy ? 'Loading' : 'Connected if data is visible'}</span></footer>
        </div>
      </main>
    </div>
  );
}

export default App;
