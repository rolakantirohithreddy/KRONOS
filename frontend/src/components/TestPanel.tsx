import { useState, useEffect } from 'react';
import {
  FlaskConical,
  Play,
  Loader2,
  ShieldCheck,
  Flame,
  Search,
  Cpu,
  ChevronDown,
  ChevronUp,
  Code2,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import api from '../lib/axios';
import { toast } from 'react-hot-toast';
import { Incident } from './IncidentDetail';
import { normalizeIncident } from '../lib/incidentAdapter';

interface Preset {
  name: string;
  description: string;
  features: Record<string, number>;
}

interface TestPanelProps {
  onIncidentCreated: (incident: Incident) => void;
  onSelectIncident: (incident: Incident) => void;
}

export function TestPanel({ onIncidentCreated, onSelectIncident }: TestPanelProps) {
  const [isExpanded, setIsExpanded] = useState(true);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [isLoadingPresets, setIsLoadingPresets] = useState(false);
  const [presetLoadError, setPresetLoadError] = useState<string | null>(null);

  // Execution states
  const [runningPreset, setRunningPreset] = useState<string | null>(null);
  const [isCustomRunning, setIsCustomRunning] = useState(false);

  // Custom JSON editor state
  const [isCustomOpen, setIsCustomOpen] = useState(false);
  const [customJson, setCustomJson] = useState<string>('');
  const [customError, setCustomError] = useState<string | null>(null);

  useEffect(() => {
    fetchPresets();
  }, []);

  const fetchPresets = async () => {
    setIsLoadingPresets(true);
    setPresetLoadError(null);
    try {
      const res = await api.get<Preset[]>('/testing/presets');
      setPresets(res.data);
      if (res.data.length > 0 && !customJson) {
        // Pre-fill custom editor with first preset
        setCustomJson(JSON.stringify(res.data[0].features, null, 2));
      }
    } catch (err: any) {
      const msg = err.response?.data?.detail || 'Failed to load test presets from backend.';
      setPresetLoadError(msg);
      toast.error(msg);
    } finally {
      setIsLoadingPresets(false);
    }
  };

  const handleRunPreset = async (preset: Preset) => {
    setRunningPreset(preset.name);
    setCustomError(null);
    try {
      const res = await api.post('/testing/run', { preset_name: preset.name });
      const incident = normalizeIncident(res.data);
      onIncidentCreated(incident);
      onSelectIncident(incident);
      toast.success(
        `Test complete: ${incident.attack_type} (${(incident.confidence * 100).toFixed(0)}% conf)`
      );
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to run test pipeline.';
      toast.error(detail);
    } finally {
      setRunningPreset(null);
    }
  };

  const handleRunCustom = async () => {
    setCustomError(null);
    let parsedFeatures: Record<string, any>;
    try {
      parsedFeatures = JSON.parse(customJson);
    } catch (e: any) {
      setCustomError(`Malformed JSON syntax: ${e.message}`);
      return;
    }

    if (typeof parsedFeatures !== 'object' || parsedFeatures === null || Array.isArray(parsedFeatures)) {
      setCustomError('Custom payload must be a JSON object mapping feature names to numbers.');
      return;
    }

    setIsCustomRunning(true);
    try {
      const res = await api.post('/testing/run', { features: parsedFeatures });
      const incident = normalizeIncident(res.data);
      onIncidentCreated(incident);
      onSelectIncident(incident);
      toast.success(`Custom test complete: ${incident.attack_type} (${incident.risk_label})`);
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to execute custom test.';
      setCustomError(detail);
      toast.error(detail);
    } finally {
      setIsCustomRunning(false);
    }
  };

  const loadPresetIntoEditor = (preset: Preset) => {
    setCustomJson(JSON.stringify(preset.features, null, 2));
    setCustomError(null);
    toast.success(`Loaded "${preset.name}" features into editor`);
  };

  const getPresetIcon = (name: string) => {
    const lower = name.toLowerCase();
    if (lower.includes('benign')) {
      return <ShieldCheck className="text-[var(--accent-safe)]" size={20} />;
    }
    if (lower.includes('ddos')) {
      return <Flame className="text-[var(--accent-danger)]" size={20} />;
    }
    if (lower.includes('recon') || lower.includes('port scan')) {
      return <Search className="text-[var(--accent-warn)]" size={20} />;
    }
    return <Cpu className="text-[var(--accent-primary)]" size={20} />;
  };

  return (
    <div className="rounded-lg border-2 border-dashed border-[var(--accent-primary)]/35 bg-[var(--bg-surface)] p-5 sm:p-6 transition-all">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[var(--border-color)]/60 pb-4">
        <div className="flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-md bg-[var(--accent-primary)]/15 text-[var(--accent-primary)]">
            <FlaskConical size={20} />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-[var(--text-primary)]">Pipeline Test Panel</h2>
              <span className="inline-flex items-center gap-1.5 rounded-full border border-amber-500/40 bg-amber-500/10 px-2.5 py-0.5 font-mono text-[11px] font-semibold text-amber-500">
                <span className="h-1.5 w-1.5 rounded-full bg-amber-500 animate-pulse" />
                TEST MODE
              </span>
            </div>
            <p className="mt-0.5 text-xs text-[var(--text-muted)]">
              Simulate realistic attack scenarios and custom feature values without live traffic capture.
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={() => setIsExpanded(prev => !prev)}
          className="flex items-center gap-1.5 rounded-md border border-[var(--border-color)] px-3 py-1.5 text-xs font-medium text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)]"
        >
          {isExpanded ? (
            <>
              Hide Panel <ChevronUp size={14} />
            </>
          ) : (
            <>
              Show Panel <ChevronDown size={14} />
            </>
          )}
        </button>
      </div>

      {/* Collapsible Content */}
      {isExpanded && (
        <div className="pt-2 space-y-6">
          {/* Preset Cards Grid */}
          <div>
            <div className="mb-3 flex items-center justify-between">
              <span className="text-xs font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                One-Click Attack Presets
              </span>
              <button
                type="button"
                onClick={fetchPresets}
                disabled={isLoadingPresets}
                className="inline-flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline disabled:opacity-50"
              >
                <RotateCcw size={12} className={isLoadingPresets ? 'animate-spin' : ''} />
                Refresh Presets
              </button>
            </div>

            {isLoadingPresets && presets.length === 0 ? (
              <div className="flex items-center justify-center p-8 text-sm text-[var(--text-muted)]">
                <Loader2 size={18} className="mr-2 animate-spin text-[var(--accent-primary)]" />
                Loading feature presets from backend...
              </div>
            ) : presetLoadError ? (
              <div className="rounded-md border border-[var(--accent-danger)]/40 bg-[var(--accent-danger)]/10 p-4 text-xs text-[var(--accent-danger)]">
                {presetLoadError}
              </div>
            ) : (
              <div className="grid grid-cols-1 gap-3.5 sm:grid-cols-2 lg:grid-cols-4">
                {presets.map(preset => {
                  const isRunning = runningPreset === preset.name;
                  return (
                    <div
                      key={preset.name}
                      onClick={() => !isRunning && handleRunPreset(preset)}
                      className={`group relative flex flex-col justify-between rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] p-4 text-left transition-all hover:border-[var(--accent-primary)]/80 hover:shadow-md cursor-pointer ${
                        isRunning ? 'opacity-70 pointer-events-none' : ''
                      }`}
                    >
                      <div>
                        <div className="mb-2 flex items-center justify-between">
                          <div className="flex items-center gap-2">
                            {getPresetIcon(preset.name)}
                            <h3 className="font-semibold text-sm text-[var(--text-primary)] group-hover:text-[var(--accent-primary)] transition-colors">
                              {preset.name}
                            </h3>
                          </div>
                        </div>
                        <p className="text-xs leading-relaxed text-[var(--text-muted)] line-clamp-3">
                          {preset.description}
                        </p>
                      </div>

                      <div className="mt-4 pt-3 border-t border-[var(--border-color)]/50 flex items-center justify-between">
                        <span className="font-mono text-[10px] text-[var(--text-muted)]">
                          {Object.keys(preset.features || {}).length} features
                        </span>
                        <button
                          type="button"
                          disabled={isRunning}
                          className="flex items-center gap-1.5 rounded px-2.5 py-1 text-xs font-semibold bg-[var(--accent-primary)]/10 text-[var(--accent-primary)] group-hover:bg-[var(--accent-primary)] group-hover:text-[var(--button-text)] transition-colors"
                        >
                          {isRunning ? (
                            <>
                              <Loader2 size={12} className="animate-spin" /> Running...
                            </>
                          ) : (
                            <>
                              <Play size={12} /> Test
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Advanced / Custom JSON Editor Collapsible */}
          <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)]/60">
            <button
              type="button"
              onClick={() => setIsCustomOpen(prev => !prev)}
              className="flex w-full items-center justify-between px-4 py-3 text-left text-xs font-semibold text-[var(--text-primary)] transition-colors hover:bg-[var(--bg-primary)]"
            >
              <div className="flex items-center gap-2">
                <Code2 size={16} className="text-[var(--accent-primary)]" />
                <span>Advanced / Custom Feature Editor</span>
                <span className="rounded bg-[var(--border-color)] px-1.5 py-0.5 font-mono text-[10px] text-[var(--text-muted)]">
                  JSON Mode
                </span>
              </div>
              <div className="flex items-center gap-1 text-[var(--text-muted)]">
                {isCustomOpen ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
              </div>
            </button>

            {isCustomOpen && (
              <div className="border-t border-[var(--border-color)] p-4 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <p className="text-xs text-[var(--text-muted)]">
                    Modify individual numerical feature values to observe SHAP explanations and risk scores in real time.
                  </p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <span className="text-[11px] text-[var(--text-muted)] mr-1">Load preset:</span>
                    {presets.map(p => (
                      <button
                        key={p.name}
                        type="button"
                        onClick={() => loadPresetIntoEditor(p)}
                        className="rounded border border-[var(--border-color)] bg-[var(--bg-surface)] px-2 py-0.5 text-[11px] text-[var(--text-primary)] hover:border-[var(--accent-primary)] hover:text-[var(--accent-primary)] transition-colors"
                      >
                        {p.name.split(' ')[0]}
                      </button>
                    ))}
                  </div>
                </div>

                {customError && (
                  <div className="flex items-start gap-2 rounded-md border border-[var(--accent-danger)]/40 bg-[var(--accent-danger)]/10 p-3 text-xs text-[var(--accent-danger)]">
                    <AlertTriangle size={15} className="mt-0.5 shrink-0" />
                    <span>{customError}</span>
                  </div>
                )}

                <div className="relative">
                  <textarea
                    rows={12}
                    value={customJson}
                    onChange={e => {
                      setCustomJson(e.target.value);
                      if (customError) setCustomError(null);
                    }}
                    placeholder='{\n  "Header_Length": 32.0,\n  "Protocol Type": 6.0,\n  "Rate": 15000.0\n}'
                    className="w-full rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] p-3 font-mono text-xs text-[var(--text-primary)] leading-relaxed transition-colors focus:border-[var(--accent-primary)] focus:outline-none"
                    spellCheck={false}
                  />
                </div>

                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] text-[var(--text-muted)]">
                    Tip: Keys must match feature_columns.json exactly.
                  </span>
                  <button
                    type="button"
                    onClick={handleRunCustom}
                    disabled={isCustomRunning}
                    className="flex items-center gap-2 rounded-md px-4 py-2 text-sm font-semibold transition-opacity disabled:opacity-50"
                    style={{
                      backgroundColor: 'var(--accent-primary)',
                      color: 'var(--button-text)',
                    }}
                  >
                    {isCustomRunning ? (
                      <>
                        <Loader2 size={16} className="animate-spin" />
                        Running Pipeline...
                      </>
                    ) : (
                      <>
                        <Play size={16} />
                        Run Custom Test
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
