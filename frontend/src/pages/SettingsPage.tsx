import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '../components/Sidebar';
import {
  User as UserIcon,
  Lock,
  Bell,
  Cpu,
  AlertTriangle,
  CheckCircle2,
  Loader2,
  LogOut,
  Square,
  ChevronRight,
  Shield,
  Eye,
  EyeOff,
} from 'lucide-react';
import { useAuth } from '../hooks/useAuth';
import { useNavigate } from 'react-router-dom';
import api from '../lib/axios';
import { toast } from 'react-hot-toast';

interface UserSettings {
  email_alerts_critical: boolean;
  flow_window_seconds: number;
  risk_threshold: string;
}

interface ModelInfo {
  model_version: string;
  model_timestamp: string;
  n_features: number;
  n_attack_classes: number;
  architecture: string;
  dataset: string;
  attack_classes: string[];
  stage1_hyperparams: Record<string, any>;
  stage2_hyperparams: Record<string, any>;
}

// ── Section wrapper ──────────────────────────────────────────────────────────
function Section({ title, icon, children }: { title: string; icon: React.ReactNode; children: React.ReactNode }) {
  return (
    <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)]">
      <div className="flex items-center gap-3 border-b border-[var(--border-color)] px-5 py-4">
        <span className="text-[var(--accent-primary)]">{icon}</span>
        <h2 className="font-semibold text-[var(--text-primary)]">{title}</h2>
      </div>
      <div className="p-5 space-y-4">{children}</div>
    </div>
  );
}

// ── Field row ────────────────────────────────────────────────────────────────
function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
      <div className="shrink-0 sm:w-48">
        <p className="text-sm font-medium text-[var(--text-primary)]">{label}</p>
        {hint && <p className="mt-0.5 text-xs text-[var(--text-muted)]">{hint}</p>}
      </div>
      <div className="flex-1 sm:max-w-xs">{children}</div>
    </div>
  );
}

export function SettingsPage() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  // ── Change Password state ──────────────────────────────────────────────────
  const [currentPw, setCurrentPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [confirmPw, setConfirmPw] = useState('');
  const [showPw, setShowPw] = useState(false);
  const [pwLoading, setPwLoading] = useState(false);

  // ── User settings state ────────────────────────────────────────────────────
  const [settings, setSettings] = useState<UserSettings>({
    email_alerts_critical: false,
    flow_window_seconds: 5,
    risk_threshold: 'Medium',
  });
  const [settingsLoading, setSettingsLoading] = useState(true);
  const [settingsSaving, setSettingsSaving] = useState(false);

  // ── Model info state ───────────────────────────────────────────────────────
  const [modelInfo, setModelInfo] = useState<ModelInfo | null>(null);
  const [modelLoading, setModelLoading] = useState(true);
  const [showAttackClasses, setShowAttackClasses] = useState(false);

  // ── Monitoring stop ────────────────────────────────────────────────────────
  const [stopLoading, setStopLoading] = useState(false);

  // ── Fetch settings and model info on mount ─────────────────────────────────
  const fetchSettings = useCallback(async () => {
    try {
      const res = await api.get<UserSettings>('/user/settings');
      setSettings(res.data);
    } catch { /* not critical */ }
    finally { setSettingsLoading(false); }
  }, []);

  const fetchModelInfo = useCallback(async () => {
    try {
      const res = await api.get<ModelInfo>('/system/model-info');
      setModelInfo(res.data);
    } catch { /* not critical */ }
    finally { setModelLoading(false); }
  }, []);

  useEffect(() => {
    void fetchSettings();
    void fetchModelInfo();
  }, [fetchSettings, fetchModelInfo]);

  // ── Handlers ──────────────────────────────────────────────────────────────

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!currentPw || !newPw || !confirmPw) {
      toast.error('All password fields are required.');
      return;
    }
    setPwLoading(true);
    try {
      await api.post('/auth/change-password', {
        current_password: currentPw,
        new_password: newPw,
        confirm_password: confirmPw,
      });
      toast.success('Password updated successfully.');
      setCurrentPw(''); setNewPw(''); setConfirmPw('');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to change password.');
    } finally {
      setPwLoading(false);
    }
  };

  const saveSettings = async (partial: Partial<UserSettings>) => {
    const next = { ...settings, ...partial };
    setSettings(next);
    setSettingsSaving(true);
    try {
      await api.post('/user/settings', partial);
      toast.success('Settings saved.');
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to save settings.');
      setSettings(settings); // revert
    } finally {
      setSettingsSaving(false);
    }
  };

  const handleStopMonitoring = async () => {
    setStopLoading(true);
    try {
      await api.post('/monitoring/stop', {});
      toast.success('All active monitoring stopped.');
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to stop monitoring.';
      if (detail.includes('No device')) {
        toast('No active monitoring session to stop.', { icon: 'ℹ️' });
      } else {
        toast.error(detail);
      }
    } finally {
      setStopLoading(false);
    }
  };

  const handleLogout = () => {
    logout();
    navigate('/login', { replace: true });
  };

  // ── Input / Toggle helpers ─────────────────────────────────────────────────
  const inputCls = 'w-full rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none focus:ring-1 focus:ring-[var(--accent-primary)]';

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <Sidebar />
      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="flex h-16 shrink-0 items-center border-b border-[var(--border-color)] bg-[var(--bg-surface)] px-5 pr-24 sm:px-8 sm:pr-24">
          <h1 className="text-lg font-semibold">Settings</h1>
        </header>

        <div className="flex-1 overflow-auto p-5 sm:p-8 space-y-6 max-w-3xl">

          {/* ── 1. Profile ── */}
          <Section title="Profile" icon={<UserIcon size={18} />}>
            <Field label="Email address" hint="Your registered account email">
              <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2 text-sm text-[var(--text-muted)]">
                {user?.email ?? '—'}
              </div>
            </Field>
          </Section>

          {/* ── 2. Change Password ── */}
          <Section title="Change Password" icon={<Lock size={18} />}>
            <form onSubmit={handleChangePassword} className="space-y-3">
              <Field label="Current password">
                <div className="relative">
                  <input
                    type={showPw ? 'text' : 'password'}
                    value={currentPw}
                    onChange={e => setCurrentPw(e.target.value)}
                    placeholder="Current password"
                    className={inputCls + ' pr-9'}
                    autoComplete="current-password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPw(p => !p)}
                    className="absolute right-2.5 top-1/2 -translate-y-1/2 text-[var(--text-muted)] hover:text-[var(--text-primary)]"
                  >
                    {showPw ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </Field>
              <Field label="New password">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={newPw}
                  onChange={e => setNewPw(e.target.value)}
                  placeholder="New password (min 8 chars)"
                  className={inputCls}
                  autoComplete="new-password"
                />
              </Field>
              <Field label="Confirm new password">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={confirmPw}
                  onChange={e => setConfirmPw(e.target.value)}
                  placeholder="Confirm new password"
                  className={inputCls}
                  autoComplete="new-password"
                />
              </Field>
              <div className="flex justify-end">
                <button
                  type="submit"
                  disabled={pwLoading}
                  className="flex items-center gap-2 rounded-md bg-[var(--accent-primary)] px-4 py-2 text-sm font-semibold text-[var(--button-text)] transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {pwLoading ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
                  Update Password
                </button>
              </div>
            </form>
          </Section>

          {/* ── 3. Monitoring Defaults ── */}
          <Section title="Monitoring Defaults" icon={<Shield size={18} />}>
            {settingsLoading ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
                <Loader2 size={16} className="animate-spin" /> Loading settings...
              </div>
            ) : (
              <>
                <Field label="Flow window (seconds)" hint="Duration of each captured network flow window">
                  <div className="flex items-center gap-3">
                    <input
                      type="number"
                      min={1}
                      max={120}
                      value={settings.flow_window_seconds}
                      onChange={e => setSettings(s => ({ ...s, flow_window_seconds: Number(e.target.value) }))}
                      onBlur={() => saveSettings({ flow_window_seconds: settings.flow_window_seconds })}
                      className={inputCls}
                    />
                    <span className="shrink-0 text-xs text-[var(--text-muted)]">s</span>
                  </div>
                </Field>

                <Field label="Incident alert threshold" hint="Minimum risk label required to record an incident (Medium, High, or Critical)">
                  <select
                    value={settings.risk_threshold}
                    onChange={e => saveSettings({ risk_threshold: e.target.value })}
                    className={inputCls + ' cursor-pointer'}
                  >
                    <option value="Medium">Medium (Recommended)</option>
                    <option value="High">High</option>
                    <option value="Critical">Critical only</option>
                  </select>
                </Field>
              </>
            )}
          </Section>

          {/* ── 4. Notifications ── */}
          <Section title="Notifications" icon={<Bell size={18} />}>
            {settingsLoading ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
                <Loader2 size={16} className="animate-spin" /> Loading settings...
              </div>
            ) : (
              <Field
                label="Email on Critical incidents"
                hint="Send an email via Resend when a Critical-risk incident is detected during live monitoring"
              >
                <button
                  type="button"
                  disabled={settingsSaving}
                  onClick={() => saveSettings({ email_alerts_critical: !settings.email_alerts_critical })}
                  className={`relative inline-flex h-6 w-11 items-center rounded-full transition-colors focus:outline-none ${
                    settings.email_alerts_critical ? 'bg-[var(--accent-primary)]' : 'bg-[var(--border-color)]'
                  } ${settingsSaving ? 'opacity-50' : ''}`}
                >
                  <span
                    className={`inline-block h-4 w-4 transform rounded-full bg-white shadow transition-transform ${
                      settings.email_alerts_critical ? 'translate-x-6' : 'translate-x-1'
                    }`}
                  />
                </button>
                <p className="mt-1.5 text-xs text-[var(--text-muted)]">
                  {settings.email_alerts_critical ? (
                    <span className="text-emerald-400">Enabled — you'll receive email alerts for Critical detections.</span>
                  ) : (
                    'Disabled — no alert emails will be sent.'
                  )}
                </p>
              </Field>
            )}
          </Section>

          {/* ── 5. System / Model Info ── */}
          <Section title="System Information" icon={<Cpu size={18} />}>
            {modelLoading ? (
              <div className="flex items-center gap-2 text-sm text-[var(--text-muted)]">
                <Loader2 size={16} className="animate-spin" /> Loading model info...
              </div>
            ) : modelInfo ? (
              <div className="space-y-3">
                <div className="grid grid-cols-2 gap-3 text-sm">
                  {[
                    ['Model Version', modelInfo.model_version],
                    ['Trained', modelInfo.model_timestamp.replace('_', ' ')],
                    ['Feature Count', String(modelInfo.n_features)],
                    ['Attack Classes', String(modelInfo.n_attack_classes)],
                    ['Dataset', modelInfo.dataset],
                  ].map(([k, v]) => (
                    <div key={k} className="rounded border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2">
                      <p className="text-[10px] uppercase tracking-wide text-[var(--text-muted)]">{k}</p>
                      <p className="mt-0.5 font-mono text-xs font-semibold text-[var(--text-primary)] break-all">{v}</p>
                    </div>
                  ))}
                </div>
                <div className="rounded border border-[var(--border-color)] bg-[var(--bg-primary)] px-3 py-2 text-xs text-[var(--text-muted)]">
                  <p className="mb-1 text-[10px] uppercase tracking-wide">Architecture</p>
                  <p>{modelInfo.architecture}</p>
                </div>
                {modelInfo.attack_classes.length > 0 && (
                  <div>
                    <button
                      type="button"
                      onClick={() => setShowAttackClasses(p => !p)}
                      className="flex items-center gap-1 text-xs text-[var(--accent-primary)] hover:underline"
                    >
                      {showAttackClasses ? 'Hide' : 'Show'} all {modelInfo.n_attack_classes} attack classes
                      <ChevronRight size={12} className={`transition-transform ${showAttackClasses ? 'rotate-90' : ''}`} />
                    </button>
                    {showAttackClasses && (
                      <div className="mt-2 flex flex-wrap gap-1.5">
                        {modelInfo.attack_classes.map(cls => (
                          <span
                            key={cls}
                            className="rounded-full border border-[var(--border-color)] bg-[var(--bg-primary)] px-2 py-0.5 font-mono text-[10px] text-[var(--text-muted)]"
                          >
                            {cls}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-[var(--text-muted)]">Could not load model information.</p>
            )}
          </Section>

          {/* ── 6. Danger Zone ── */}
          <Section title="Danger Zone" icon={<AlertTriangle size={18} className="text-red-500" />}>
            <div className="space-y-3">
              <Field
                label="Stop All Monitoring"
                hint="Immediately terminates any active ARP redirection and traffic capture — useful between demo runs"
              >
                <button
                  type="button"
                  disabled={stopLoading}
                  onClick={handleStopMonitoring}
                  className="flex items-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-4 py-2 text-sm font-semibold text-red-500 transition-colors hover:bg-red-500 hover:text-white disabled:opacity-50"
                >
                  {stopLoading ? <Loader2 size={15} className="animate-spin" /> : <Square size={15} />}
                  Stop Monitoring
                </button>
              </Field>

              <div className="border-t border-[var(--border-color)] pt-3">
                <Field label="Logout" hint="End your session on this device">
                  <button
                    type="button"
                    onClick={handleLogout}
                    className="flex items-center gap-2 rounded-md border border-[var(--border-color)] px-4 py-2 text-sm font-medium text-[var(--text-muted)] transition-colors hover:border-red-500/40 hover:bg-red-500/10 hover:text-red-500"
                  >
                    <LogOut size={15} />
                    Logout
                  </button>
                </Field>
              </div>
            </div>
          </Section>

        </div>
      </main>
    </div>
  );
}
