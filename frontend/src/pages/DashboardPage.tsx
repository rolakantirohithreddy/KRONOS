import { useState, useEffect, useCallback, useRef } from 'react';
import { Sidebar } from '../components/Sidebar';
import { IncidentDetail, Incident } from '../components/IncidentDetail';
import { RiskBadge } from '../components/RiskBadge';
import { TestPanel } from '../components/TestPanel';
import {
  Play,
  Activity,
  ShieldAlert,
  ShieldCheck,
  Clock,
  Loader2,
  Radio,
  WifiOff,
  RefreshCw,
  AlertTriangle,
  Terminal,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import api from '../lib/axios';
import { toast } from 'react-hot-toast';
import { normalizeIncident } from '../lib/incidentAdapter';

interface Stats {
  total_incidents: number;
  high_critical_count: number;
  avg_pipeline_latency_ms: number;
}

interface MonitoringStatus {
  monitoring_active: boolean;
  current_target_ip: string | null;
  arp_redirect_active: boolean;
  capture_loop_alive: boolean;
  last_cycle_at: string | null;
  packets_seen_last_window: number;
  arp_redirect?: any;
}

interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
}

interface RawIncident {
  id: number;
  request_id: string;
  timestamp: string;
  source_ip: string | null;
  attack_type: string;
  risk_label: string;
  confidence: number;
  mitigated: boolean;
  source: 'live' | 'test' | 'manual_simulate';
  evidence_summary: string | null;
  pipeline_latency_ms: number | null;
  occurrence_count: number;
  last_seen_at: string | null;
}

const SOURCE_BADGE: Record<string, { label: string; cls: string }> = {
  test: { label: 'TEST', cls: 'bg-amber-500/15 text-amber-400 border-amber-500/30' },
  manual_simulate: { label: 'SIMULATED', cls: 'bg-purple-500/15 text-purple-400 border-purple-500/30' },
  live: { label: 'LIVE', cls: 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30' },
};

export function DashboardPage() {
  const { user } = useAuth();

  // --- Stats ---
  const [stats, setStats] = useState<Stats>({ total_incidents: 0, high_critical_count: 0, avg_pipeline_latency_ms: 0 });
  const [isLoadingStats, setIsLoadingStats] = useState(true);

  // --- Monitoring status ---
  const [monitoringStatus, setMonitoringStatus] = useState<MonitoringStatus>({
    monitoring_active: false,
    current_target_ip: null,
    arp_redirect_active: false,
    capture_loop_alive: false,
    last_cycle_at: null,
    packets_seen_last_window: 0,
  });

  // --- Incident feed ---
  const [liveIncidents, setLiveIncidents] = useState<RawIncident[]>([]);
  const [isLoadingIncidents, setIsLoadingIncidents] = useState(true);

  // --- Selected for detail drawer ---
  const [selectedIncident, setSelectedIncident] = useState<Incident | null>(null);

  // --- Quick simulate ---
  const [isSimulating, setIsSimulating] = useState(false);

  // --- Refresh spin ---
  const [isRefreshing, setIsRefreshing] = useState(false);

  // --- Live Logs ---
  const [logEntries, setLogEntries] = useState<LogEntry[]>([]);
  const [isLogsExpanded, setIsLogsExpanded] = useState(true);
  const logsEndRef = useRef<HTMLDivElement>(null);
  const logSeenCount = useRef(0);

  const pollingRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const logPollingRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // ─── Fetchers ─────────────────────────────────────────────────────────────

  const fetchStats = useCallback(async () => {
    try {
      const res = await api.get<Stats>('/incidents/stats');
      setStats(res.data);
    } catch { /* non-fatal */ }
    finally { setIsLoadingStats(false); }
  }, []);

  const fetchMonitoringStatus = useCallback(async () => {
    try {
      const res = await api.get<MonitoringStatus>('/monitoring/status');
      setMonitoringStatus(res.data);
    } catch { /* non-fatal */ }
  }, []);

  const fetchLiveIncidents = useCallback(async () => {
    try {
      const res = await api.get<RawIncident[]>('/incidents', { params: { limit: 50 } });
      setLiveIncidents(res.data);
    } catch { /* non-fatal */ }
    finally { setIsLoadingIncidents(false); }
  }, []);

  const fetchLogs = useCallback(async () => {
    try {
      const res = await api.get<LogEntry[]>('/monitoring/logs');
      const newEntries = res.data;
      if (newEntries.length > logSeenCount.current) {
        setLogEntries(newEntries);
        logSeenCount.current = newEntries.length;
        // Auto-scroll to bottom
        setTimeout(() => {
          logsEndRef.current?.scrollIntoView({ behavior: 'smooth' });
        }, 50);
      }
    } catch { /* non-fatal */ }
  }, []);

  const refreshAll = useCallback(async () => {
    await Promise.all([fetchStats(), fetchMonitoringStatus(), fetchLiveIncidents()]);
  }, [fetchStats, fetchMonitoringStatus, fetchLiveIncidents]);

  // ─── Polling ──────────────────────────────────────────────────────────────

  useEffect(() => {
    void refreshAll();
  }, [refreshAll]);

  // Main polling: 2.5s when monitoring active, no auto-poll when idle
  useEffect(() => {
    if (pollingRef.current) clearInterval(pollingRef.current);

    if (monitoringStatus.monitoring_active) {
      pollingRef.current = setInterval(() => {
        void fetchLiveIncidents();
        void fetchStats();
        void fetchMonitoringStatus();
      }, 2500);
    }

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [monitoringStatus.monitoring_active, fetchLiveIncidents, fetchStats, fetchMonitoringStatus]);

  // Log polling: every 2s while monitoring active
  useEffect(() => {
    if (logPollingRef.current) clearInterval(logPollingRef.current);

    if (monitoringStatus.monitoring_active) {
      // Fetch immediately
      void fetchLogs();
      logPollingRef.current = setInterval(() => {
        void fetchLogs();
      }, 2000);
    }

    return () => {
      if (logPollingRef.current) clearInterval(logPollingRef.current);
    };
  }, [monitoringStatus.monitoring_active, fetchLogs]);

  // ─── Quick Simulate ───────────────────────────────────────────────────────

  const simulateIncident = async () => {
    setIsSimulating(true);
    try {
      const res = await api.post('/testing/run', { preset_name: 'DDoS-like' });
      const newIncident = normalizeIncident(res.data);
      setSelectedIncident(newIncident);
      toast.success(`Simulated incident: ${newIncident.attack_type}`);
      // Refresh DB feed + stats since testing/run now persists
      void fetchLiveIncidents();
      void fetchStats();
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to simulate incident');
    } finally {
      setIsSimulating(false);
    }
  };

  // ─── Handlers ─────────────────────────────────────────────────────────────

  const handleRowClick = (raw: RawIncident) => {
    // Use the raw data — incidentAdapter handles both formats
    setSelectedIncident(normalizeIncident(raw));
  };

  const handleTestPanelIncident = (_inc: Incident) => {
    // /testing/run now persists to DB; just refresh the feed
    void fetchLiveIncidents();
    void fetchStats();
  };

  // ─── Monitoring badge logic ───────────────────────────────────────────────

  const renderMonitoringBadge = () => {
    const { monitoring_active, arp_redirect_active, capture_loop_alive, current_target_ip } = monitoringStatus;

    if (!monitoring_active) {
      return (
        <span className="hidden sm:inline-flex items-center gap-1.5 rounded-full border border-[var(--border-color)] px-2.5 py-1 text-[11px] font-medium text-[var(--text-muted)]">
          <WifiOff size={11} />
          Monitoring Off
        </span>
      );
    }

    // Both ARP redirect and capture loop alive → fully green
    if (arp_redirect_active && capture_loop_alive) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2.5 py-1 text-[11px] font-semibold text-emerald-400">
          <Radio size={12} className="animate-pulse" />
          LIVE · {current_target_ip}
        </span>
      );
    }

    // ARP redirect active but capture loop NOT alive → amber warning
    if (arp_redirect_active && !capture_loop_alive) {
      return (
        <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-400">
          <AlertTriangle size={12} className="animate-pulse" />
          Redirect Active, Capture Not Responding · {current_target_ip}
        </span>
      );
    }

    // Monitoring active but no ARP redirect (shouldn't normally happen)
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-[11px] font-semibold text-amber-400">
        <AlertTriangle size={12} />
        Starting · {current_target_ip}
      </span>
    );
  };

  // ─── Log level color ──────────────────────────────────────────────────────

  const logLevelColor = (level: string) => {
    switch (level.toUpperCase()) {
      case 'ERROR': return 'text-red-400';
      case 'WARNING': return 'text-amber-400';
      default: return 'text-emerald-400';
    }
  };

  // ─── Render ───────────────────────────────────────────────────────────────

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <Sidebar />

      <main className="flex-1 flex flex-col relative">
        {/* ── Header ── */}
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--border-color)] bg-[var(--bg-surface)] px-5 pr-24 sm:px-8 sm:pr-24">
          <div className="flex items-center gap-3">
            <span className="truncate text-sm text-[var(--text-muted)]">
              Logged in as{' '}
              <span className="font-medium text-[var(--text-primary)]">{user?.email}</span>
            </span>
            {/* Monitoring indicator */}
            {renderMonitoringBadge()}
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                setIsRefreshing(true);
                setTimeout(() => setIsRefreshing(false), 400);
                void refreshAll();
              }}
              className="flex items-center gap-1.5 rounded-md border border-[var(--border-color)] px-2.5 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
            >
              <RefreshCw
                size={13}
                style={{
                  transition: 'transform 0.35s ease',
                  transform: isRefreshing ? 'rotate(180deg)' : 'rotate(0deg)',
                }}
              />
              Refresh
            </button>
            <button
              onClick={simulateIncident}
              disabled={isSimulating}
              className="ml-1 flex shrink-0 items-center gap-2 rounded-md border border-[var(--accent-primary)]/40 bg-[var(--accent-primary)]/10 px-3 py-2 text-sm font-semibold text-[var(--accent-primary)] transition-colors hover:bg-[var(--accent-primary)] hover:text-[var(--button-text)] disabled:opacity-50 sm:px-4"
            >
              {isSimulating ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
              Quick Simulate
            </button>
          </div>
        </header>

        <div className="flex-1 space-y-6 overflow-auto p-5 sm:p-8">
          {/* ── KPI Cards ── */}
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <div className="flex flex-col gap-3 rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] p-5 sm:p-6">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-muted)]">
                <Activity size={18} />
                Total Incidents
              </div>
              <div className="font-mono text-3xl font-semibold">
                {isLoadingStats ? <Loader2 size={22} className="animate-spin text-[var(--text-muted)]" /> : stats.total_incidents}
              </div>
            </div>
            <div className="flex flex-col gap-3 rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] p-5 sm:p-6">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-muted)]">
                <ShieldAlert size={18} className="text-[var(--color-risk-high)]" />
                High / Critical Risk
              </div>
              <div className="font-mono text-3xl font-semibold text-[var(--color-risk-high)]">
                {isLoadingStats ? <Loader2 size={22} className="animate-spin text-[var(--text-muted)]" /> : stats.high_critical_count}
              </div>
            </div>
            <div className="flex flex-col gap-3 rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] p-5 sm:p-6">
              <div className="flex items-center gap-2 text-sm font-medium text-[var(--text-muted)]">
                <Clock size={18} />
                Avg Pipeline Latency
              </div>
              <div className="font-mono text-3xl font-semibold">
                {isLoadingStats
                  ? <Loader2 size={22} className="animate-spin text-[var(--text-muted)]" />
                  : `${stats.avg_pipeline_latency_ms.toFixed(1)} ms`}
              </div>
            </div>
          </div>

          {/* ── Test Panel ── */}
          <TestPanel
            onIncidentCreated={handleTestPanelIncident}
            onSelectIncident={setSelectedIncident}
          />

          {/* ── Live Logs Panel ── */}
          {monitoringStatus.monitoring_active && (
            <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] overflow-hidden">
              <button
                type="button"
                onClick={() => setIsLogsExpanded(prev => !prev)}
                className="flex w-full items-center justify-between px-5 py-3 text-left transition-colors hover:bg-[var(--bg-primary)]"
              >
                <div className="flex items-center gap-2">
                  <Terminal size={16} className="text-emerald-400" />
                  <span className="text-sm font-semibold text-[var(--text-primary)]">Live Logs</span>
                  <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-400 border border-emerald-500/30">
                    {logEntries.length} entries
                  </span>
                  {monitoringStatus.capture_loop_alive && (
                    <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] text-emerald-400">
                      {monitoringStatus.packets_seen_last_window} pkts last window
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1 text-[var(--text-muted)]">
                  {isLogsExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                </div>
              </button>

              {isLogsExpanded && (
                <div
                  className="max-h-[300px] overflow-auto border-t border-[var(--border-color)] bg-gray-950 p-3"
                  style={{ fontFamily: "'JetBrains Mono', 'Fira Code', 'Cascadia Code', monospace" }}
                >
                  {logEntries.length === 0 ? (
                    <p className="text-xs text-gray-500 py-4 text-center">
                      Waiting for capture loop to produce logs...
                    </p>
                  ) : (
                    logEntries.map((entry, i) => (
                      <div key={i} className="text-xs leading-5 whitespace-pre-wrap break-all">
                        <span className="text-gray-500">
                          {new Date(entry.timestamp).toLocaleTimeString()}
                        </span>
                        {' '}
                        <span className={`font-semibold ${logLevelColor(entry.level)}`}>
                          [{entry.level}]
                        </span>
                        {' '}
                        <span className="text-gray-300">{entry.message}</span>
                      </div>
                    ))
                  )}
                  <div ref={logsEndRef} />
                </div>
              )}
            </div>
          )}

          {/* ── Incident Feed ── */}
          <div className="flex min-h-[360px] flex-col overflow-hidden rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)]">
            <div className="flex items-center justify-between border-b border-[var(--border-color)] px-5 py-4">
              <div>
                <h2 className="font-semibold">Recent Detections</h2>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  All incidents from DB — live, test, and simulated.
                  {monitoringStatus.monitoring_active && (
                    <span className="ml-1 text-emerald-400">Auto-refreshing every 2.5 s while monitoring is active.</span>
                  )}
                </p>
              </div>
              <span className="font-mono text-xs text-[var(--text-muted)]">
                {liveIncidents.length} total
              </span>
            </div>

            {isLoadingIncidents ? (
              <div className="flex flex-1 items-center justify-center py-14">
                <Loader2 size={22} className="animate-spin text-[var(--accent-primary)]" />
              </div>
            ) : liveIncidents.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center px-6 py-14 text-center text-[var(--text-muted)]">
                <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--accent-primary)]">
                  <ShieldCheck size={26} strokeWidth={1.7} />
                </div>
                <p className="font-medium text-[var(--text-primary)]">No incidents detected yet</p>
                <p className="mt-1 max-w-sm text-sm">
                  Run a preset from the Test Panel above, or go to{' '}
                  <span className="text-[var(--accent-primary)]">Devices</span>{' '}
                  and start live monitoring to see real detections here.
                </p>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b border-[var(--border-color)] bg-[var(--bg-primary)] text-xs uppercase tracking-wide text-[var(--text-muted)]">
                      <th className="p-4 font-medium">Timestamp</th>
                      <th className="p-4 font-medium">Source IP</th>
                      <th className="p-4 font-medium">Attack Type</th>
                      <th className="p-4 font-medium">Risk</th>
                      <th className="p-4 font-medium">Confidence</th>
                      <th className="p-4 font-medium">Source</th>
                      <th className="p-4 font-medium">Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {liveIncidents.map(inc => {
                      const badge = SOURCE_BADGE[inc.source] ?? SOURCE_BADGE['test'];
                      return (
                        <tr
                          key={inc.id}
                          onClick={() => handleRowClick(inc)}
                          className="cursor-pointer border-b border-[var(--border-color)] transition-colors last:border-0 hover:bg-[var(--bg-primary)]"
                        >
                          <td className="whitespace-nowrap p-4 font-mono text-xs text-[var(--text-muted)]">
                            {new Date(inc.timestamp).toLocaleString()}
                          </td>
                          <td className="p-4 font-mono text-xs text-[var(--text-muted)]">
                            {inc.source_ip || '—'}
                          </td>
                          <td className="p-4 font-medium text-[var(--text-primary)]">
                            {inc.attack_type}
                            {(inc.occurrence_count ?? 1) > 1 && (
                              <span className="ml-1.5 inline-flex items-center rounded bg-sky-500/15 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-sky-400 border border-sky-500/30">
                                ×{inc.occurrence_count}
                              </span>
                            )}
                          </td>
                          <td className="p-4">
                            <RiskBadge label={inc.risk_label} />
                          </td>
                          <td className="p-4 font-mono text-sm">
                            {(inc.confidence * 100).toFixed(1)}%
                          </td>
                          <td className="p-4">
                            <span className={`inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] font-semibold ${badge.cls}`}>
                              {badge.label}
                            </span>
                          </td>
                          <td className="p-4">
                            {inc.mitigated ? (
                              <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[10px] font-semibold text-emerald-400">
                                Mitigated
                              </span>
                            ) : (
                              <span className="text-xs text-[var(--text-muted)]">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>

        <IncidentDetail incident={selectedIncident} onClose={() => setSelectedIncident(null)} />
      </main>
    </div>
  );
}
