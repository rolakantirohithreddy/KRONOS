import { useState, useEffect, useCallback } from 'react';
import { Sidebar } from '../components/Sidebar';
import {
  Cpu,
  Wifi,
  WifiOff,
  Play,
  Square,
  RefreshCw,
  Loader2,
  AlertTriangle,
  Camera,
  Smartphone,
  Router,
  CheckCircle2,
  Radio,
  HelpCircle,
  ShieldAlert,
} from 'lucide-react';
import api from '../lib/axios';
import { toast } from 'react-hot-toast';

interface MonitoringStatus {
  monitoring_active: boolean;
  current_target_ip: string | null;
  arp_redirect: {
    active_targets: string[];
    count: number;
  };
}

interface DiscoveredDevice {
  id: string;
  ip: string;
  mac: string;
  name: string;
  device_type: 'ip_camera_phone' | 'ip_camera' | 'unknown';
  confidence: 'high' | 'medium' | 'low';
  is_gateway: boolean;
  description: string;
}

export function DevicesPage() {
  const [devices, setDevices] = useState<DiscoveredDevice[]>([]);
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('');
  const [customIp, setCustomIp] = useState('');
  const [status, setStatus] = useState<MonitoringStatus | null>(null);
  const [isStarting, setIsStarting] = useState(false);
  const [isStopping, setIsStopping] = useState(false);
  const [isLoadingStatus, setIsLoadingStatus] = useState(true);
  const [isScanning, setIsScanning] = useState(false);

  // Fetch monitoring daemon status
  const fetchStatus = useCallback(async () => {
    try {
      const res = await api.get('/monitoring/status');
      setStatus(res.data);
    } catch {
      setStatus(null);
    } finally {
      setIsLoadingStatus(false);
    }
  }, []);

  // Fetch real discovered LAN devices from GET /devices
  const fetchDevices = useCallback(async () => {
    setIsScanning(true);
    try {
      const res = await api.get('/devices');
      const data: DiscoveredDevice[] = Array.isArray(res.data) ? res.data : (res.data?.devices || []);
      setDevices(data);

      // Pre-select first non-gateway device or first device if none selected
      setSelectedDeviceId(prev => {
        if (prev === 'custom') return 'custom';
        if (prev) {
          const exists = data.some(d => d.id === prev || d.ip === prev);
          if (exists) return prev;
        }
        const nonGateway = data.find(d => !d.is_gateway);
        if (nonGateway) return nonGateway.id;
        return data.length > 0 ? data[0].id : 'custom';
      });
    } catch (err: any) {
      console.error('Failed to discover devices:', err);
      toast.error('Failed to scan local network for devices.');
    } finally {
      setIsScanning(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    fetchDevices();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus, fetchDevices]);

  // Determine current active IP from selected device
  const getSelectedIp = (): string => {
    if (selectedDeviceId === 'custom') {
      return customIp.trim();
    }
    const found = devices.find(d => d.id === selectedDeviceId || d.ip === selectedDeviceId);
    return found ? found.ip : '';
  };

  const getSelectedDevice = (): DiscoveredDevice | undefined => {
    if (selectedDeviceId === 'custom') return undefined;
    return devices.find(d => d.id === selectedDeviceId || d.ip === selectedDeviceId);
  };

  const handleStart = async () => {
    const ip = getSelectedIp();
    const selected = getSelectedDevice();

    if (!ip) {
      toast.error('Select a device or enter a valid target IP.');
      return;
    }

    // Safety guard: prevent targeting the gateway router
    if (selected?.is_gateway) {
      toast.error(
        `Target IP (${ip}) is your LAN gateway / router. In ARP traffic monitoring, the target must be an endpoint device (such as your smartphone, an IoT device, or another computer on the same WiFi/LAN) whose traffic to/from the gateway you want to inspect, rather than the gateway itself.`
      );
      return;
    }

    setIsStarting(true);
    try {
      await api.post('/monitoring/start', { target_ip: ip });
      toast.success(`Monitoring started for ${ip}`);
      setStatus(prev =>
        prev ? { ...prev, monitoring_active: true, current_target_ip: ip } : prev
      );
      await fetchStatus();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to start monitoring.';
      toast.error(detail);
    } finally {
      setIsStarting(false);
    }
  };

  const handleStop = async () => {
    setIsStopping(true);
    try {
      await api.post('/monitoring/stop', {});
      toast.success('Monitoring stopped. Traffic redirection terminated.');
      setStatus(prev =>
        prev ? { ...prev, monitoring_active: false, current_target_ip: null } : prev
      );
      await fetchStatus();
    } catch (err: any) {
      const detail = err.response?.data?.detail || 'Failed to stop monitoring.';
      toast.error(detail);
    } finally {
      setIsStopping(false);
    }
  };

  const handleRefresh = async () => {
    await Promise.all([fetchStatus(), fetchDevices()]);
    toast.success('Scan complete. Device inventory updated.');
  };

  const isActive = status?.monitoring_active ?? false;
  const activeIp = status?.current_target_ip;
  const currentTargetIp = getSelectedIp();
  const selectedDevice = getSelectedDevice();

  const getDeviceIcon = (device: DiscoveredDevice) => {
    if (device.device_type === 'ip_camera_phone' || device.device_type === 'ip_camera') {
      return <Camera size={20} className="text-cyan-400" />;
    }
    if (device.is_gateway) {
      return <Router size={20} className="text-amber-400" />;
    }
    return <Smartphone size={20} className="text-emerald-400" />;
  };

  return (
    <div className="flex h-screen overflow-hidden bg-[var(--bg-primary)] text-[var(--text-primary)]">
      <Sidebar />
      <main className="flex-1 flex flex-col relative">
        <header className="flex h-16 shrink-0 items-center justify-between border-b border-[var(--border-color)] bg-[var(--bg-surface)] px-5 pr-24 sm:px-8 sm:pr-24">
          <div className="flex items-center gap-3">
            <Radio className="text-[var(--accent-primary)] animate-pulse" size={20} />
            <h1 className="text-lg font-semibold">Device Monitoring & Traffic Inspection</h1>
          </div>
          <button
            onClick={handleRefresh}
            disabled={isLoadingStatus || isScanning}
            className="flex items-center gap-1.5 rounded-md border border-[var(--border-color)] px-3 py-1.5 text-xs text-[var(--text-muted)] transition-colors hover:bg-[var(--bg-primary)] hover:text-[var(--text-primary)] disabled:opacity-50"
          >
            <RefreshCw size={14} className={isLoadingStatus || isScanning ? 'animate-spin' : ''} />
            {isScanning ? 'Scanning LAN...' : 'Refresh'}
          </button>
        </header>

        <div className="flex-1 overflow-auto p-5 sm:p-8 space-y-6">
          {/* Status Banner */}
          <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] p-5 sm:p-6">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
              <div className="flex items-center gap-4">
                {isActive ? (
                  <div className="flex h-12 w-12 items-center justify-center rounded-full bg-emerald-500/15 text-emerald-500 border border-emerald-500/30">
                    <Wifi size={24} />
                  </div>
                ) : (
                  <div className="flex h-12 w-12 items-center justify-center rounded-full border border-[var(--border-color)] bg-[var(--bg-primary)] text-[var(--text-muted)]">
                    <WifiOff size={24} />
                  </div>
                )}
                <div>
                  <div className="flex items-center gap-2">
                    <h2 className="text-base font-semibold">
                      {isLoadingStatus
                        ? 'Connecting to monitoring daemon...'
                        : isActive
                        ? 'On-Path Traffic Monitoring Active'
                        : 'Traffic Monitoring Inactive'}
                    </h2>
                    {isActive && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-500/20 text-emerald-400">
                        LIVE
                      </span>
                    )}
                  </div>
                  <p className="mt-1 text-xs text-[var(--text-muted)]">
                    {isActive
                      ? `Traffic from ${activeIp} is currently routed through this inspection host.`
                      : 'Select a discovered IoT endpoint device below and initiate network monitoring.'}
                  </p>
                </div>
              </div>

              {isActive && (
                <button
                  onClick={handleStop}
                  disabled={isStopping}
                  className="flex shrink-0 items-center justify-center gap-2 rounded-md border border-red-500/40 bg-red-500/10 px-5 py-2.5 text-sm font-semibold text-red-500 transition-colors hover:bg-red-500 hover:text-white disabled:opacity-50"
                >
                  {isStopping ? <Loader2 size={16} className="animate-spin" /> : <Square size={16} />}
                  Stop Monitoring
                </button>
              )}
            </div>

            {/* ARP Redirection Details */}
            {status?.arp_redirect && status.arp_redirect.count > 0 && (
              <div className="mt-4 rounded border border-[var(--border-color)] bg-[var(--bg-primary)] px-4 py-3">
                <p className="text-xs font-medium text-[var(--text-muted)] uppercase tracking-wide mb-2">
                  Active ARP Redirection Tables
                </p>
                <div className="flex flex-wrap gap-2">
                  {status.arp_redirect.active_targets.map(ip => (
                    <span
                      key={ip}
                      className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-mono text-emerald-400 border border-emerald-500/20"
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                      {ip}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Authorization Notice */}
          <div className="flex items-start gap-3 rounded border border-amber-500/30 bg-amber-500/5 px-4 py-3 text-sm text-amber-300">
            <AlertTriangle size={18} className="mt-0.5 shrink-0 text-amber-400" />
            <div className="text-xs leading-relaxed">
              <strong className="font-semibold text-amber-200">Authorized Lab Use Only:</strong> Traffic
              redirection requires OS Administrator/root privileges for packet forwarding. Inspect only devices
              in your own testbed/LAN. Clean ARP restoration is triggered automatically on stop and server shutdown.
            </div>
          </div>

          {/* Discovered Devices Section */}
          <div className="rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)] p-5 sm:p-6 space-y-5">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--text-muted)]">
                  Discovered LAN Devices ({devices.length})
                </h2>
                <p className="mt-1 text-xs text-[var(--text-muted)]">
                  Real-time network scan results with automatic IoT & phone camera fingerprinting.
                </p>
              </div>
              {isScanning && (
                <div className="flex items-center gap-2 text-xs text-[var(--accent-primary)] font-medium">
                  <Loader2 size={14} className="animate-spin" />
                  <span>Scanning local subnet...</span>
                </div>
              )}
            </div>

            {/* Device Cards Grid */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
              {devices.map(device => {
                const isSelected = selectedDeviceId === device.id || selectedDeviceId === device.ip;
                const isDeviceActive = isActive && activeIp === device.ip;
                const isCamera = device.device_type === 'ip_camera_phone' || device.device_type === 'ip_camera';

                return (
                  <div
                    key={device.id}
                    onClick={() => {
                      if (!isActive) setSelectedDeviceId(device.id);
                    }}
                    className={`cursor-pointer rounded-lg border p-4 transition-all flex flex-col justify-between ${
                      isSelected
                        ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 shadow-sm ring-1 ring-[var(--accent-primary)]/50'
                        : 'border-[var(--border-color)] bg-[var(--bg-primary)] hover:border-[var(--border-color)]/80 hover:bg-[var(--bg-surface)]'
                    } ${isActive && !isDeviceActive ? 'opacity-50 cursor-not-allowed' : ''}`}
                  >
                    <div>
                      {/* Card Header with Badges */}
                      <div className="flex items-center justify-between mb-3">
                        <div className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)]">
                          {getDeviceIcon(device)}
                        </div>

                        <div className="flex items-center gap-1.5">
                          {isCamera && (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-cyan-500/15 text-cyan-400 border border-cyan-500/30">
                              <Camera size={11} />
                              IoT Camera
                            </span>
                          )}
                          {device.is_gateway && (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-amber-500/15 text-amber-400 border border-amber-500/30">
                              <Router size={11} />
                              Gateway
                            </span>
                          )}
                          {!isCamera && !device.is_gateway && (
                            <span className="inline-flex items-center gap-1 text-[11px] font-medium px-2 py-0.5 rounded bg-[var(--border-color)]/50 text-[var(--text-muted)] border border-[var(--border-color)]">
                              <HelpCircle size={11} />
                              Unknown Device
                            </span>
                          )}
                          {isSelected && (
                            <CheckCircle2 size={18} className="text-[var(--accent-primary)]" />
                          )}
                        </div>
                      </div>

                      {/* Device Title & Description */}
                      <h3 className="text-sm font-medium text-[var(--text-primary)] flex items-center gap-2">
                        {device.name}
                        {isDeviceActive && (
                          <span className="text-[10px] font-mono font-medium px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-400">
                            Active
                          </span>
                        )}
                      </h3>
                      <p className="mt-1 text-xs text-[var(--text-muted)] leading-relaxed">
                        {device.description}
                      </p>
                    </div>

                    {/* Network Details */}
                    <div className="mt-4 pt-3 border-t border-[var(--border-color)] space-y-1.5">
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-[var(--text-muted)]">IP Address:</span>
                        <span className="font-mono text-xs font-semibold text-[var(--accent-primary)]">
                          {device.ip}
                        </span>
                      </div>
                      <div className="flex items-center justify-between">
                        <span className="text-[11px] text-[var(--text-muted)]">MAC Address:</span>
                        <span className="font-mono text-[11px] text-[var(--text-muted)]">
                          {device.mac && device.mac !== 'Unresolved' ? device.mac : 'Not resolved'}
                        </span>
                      </div>

                      {/* Select Action Button */}
                      <div className="pt-2">
                        <button
                          type="button"
                          disabled={isActive}
                          onClick={(e) => {
                            e.stopPropagation();
                            if (!isActive) setSelectedDeviceId(device.id);
                          }}
                          className={`w-full py-1 text-xs rounded font-medium transition-colors ${
                            isSelected
                              ? 'bg-[var(--accent-primary)] text-[var(--button-text)]'
                              : 'bg-[var(--bg-surface)] text-[var(--text-muted)] border border-[var(--border-color)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-primary)]'
                          }`}
                        >
                          {isSelected ? 'Selected' : 'Select for Monitoring'}
                        </button>
                      </div>

                      {device.is_gateway && (
                        <p className="text-[10px] text-amber-400/80 italic text-center pt-0.5">
                          LAN Gateway Router (Protected)
                        </p>
                      )}
                    </div>
                  </div>
                );
              })}

              {/* Custom Device Option Card (Manual fallback/override) */}
              <div
                onClick={() => {
                  if (!isActive) setSelectedDeviceId('custom');
                }}
                className={`cursor-pointer rounded-lg border p-4 transition-all flex flex-col justify-between ${
                  selectedDeviceId === 'custom'
                    ? 'border-[var(--accent-primary)] bg-[var(--accent-primary)]/5 shadow-sm ring-1 ring-[var(--accent-primary)]/50'
                    : 'border-[var(--border-color)] bg-[var(--bg-primary)] hover:border-[var(--border-color)]/80 hover:bg-[var(--bg-surface)]'
                } ${isActive ? 'opacity-50 cursor-not-allowed' : ''}`}
              >
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <div className="flex h-9 w-9 items-center justify-center rounded-md border border-[var(--border-color)] bg-[var(--bg-surface)]">
                      <Cpu size={20} className="text-purple-400" />
                    </div>
                    {selectedDeviceId === 'custom' && (
                      <CheckCircle2 size={18} className="text-[var(--accent-primary)]" />
                    )}
                  </div>
                  <h3 className="text-sm font-medium text-[var(--text-primary)]">Custom IP Target</h3>
                  <p className="mt-1 text-xs text-[var(--text-muted)] leading-relaxed">
                    Manual override: specify an arbitrary LAN host or IoT device IP
                  </p>
                </div>
                <div className="mt-4 pt-3 border-t border-[var(--border-color)]">
                  {selectedDeviceId === 'custom' ? (
                    <input
                      type="text"
                      disabled={isActive}
                      value={customIp}
                      onChange={e => setCustomIp(e.target.value)}
                      placeholder="e.g. 10.17.144.50"
                      onClick={e => e.stopPropagation()}
                      className="w-full rounded border border-[var(--border-color)] bg-[var(--bg-surface)] px-2 py-1 font-mono text-xs text-[var(--text-primary)] focus:border-[var(--accent-primary)] focus:outline-none"
                    />
                  ) : (
                    <span className="text-xs text-[var(--text-muted)] italic">Click to enter custom IP</span>
                  )}
                  <div className="pt-2">
                    <button
                      type="button"
                      disabled={isActive}
                      onClick={(e) => {
                        e.stopPropagation();
                        if (!isActive) setSelectedDeviceId('custom');
                      }}
                      className={`w-full py-1 text-xs rounded font-medium transition-colors ${
                        selectedDeviceId === 'custom'
                          ? 'bg-[var(--accent-primary)] text-[var(--button-text)]'
                          : 'bg-[var(--bg-surface)] text-[var(--text-muted)] border border-[var(--border-color)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-primary)]'
                      }`}
                    >
                      {selectedDeviceId === 'custom' ? 'Selected' : 'Use Custom IP'}
                    </button>
                  </div>
                </div>
              </div>
            </div>

            {/* Empty scan state */}
            {devices.length === 0 && !isScanning && (
              <div className="rounded border border-dashed border-[var(--border-color)] p-8 text-center text-xs text-[var(--text-muted)]">
                No active devices discovered on the LAN yet. Click <span className="font-semibold text-[var(--text-primary)]">Refresh</span> above to scan again, or enter a Custom IP Target.
              </div>
            )}

            {/* Launch Control Section */}
            {!isActive && (
              <div className="mt-6 pt-5 border-t border-[var(--border-color)] flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
                <div className="flex items-center gap-3">
                  <span className="text-xs text-[var(--text-muted)]">Selected Target IP:</span>
                  <span className="font-mono text-sm font-bold text-[var(--text-primary)]">
                    {currentTargetIp || '(None selected)'}
                  </span>
                  {selectedDevice?.is_gateway && (
                    <span className="inline-flex items-center gap-1 text-[11px] font-medium text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded border border-amber-500/20">
                      <ShieldAlert size={12} />
                      LAN Gateway Protected
                    </span>
                  )}
                </div>

                <button
                  onClick={handleStart}
                  disabled={isStarting || !currentTargetIp}
                  className="flex shrink-0 items-center justify-center gap-2 rounded-md bg-[var(--accent-primary)] px-6 py-2.5 text-sm font-semibold text-[var(--button-text)] transition-all hover:opacity-90 disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                >
                  {isStarting ? <Loader2 size={16} className="animate-spin" /> : <Play size={16} />}
                  Start Monitoring
                </button>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  );
}
