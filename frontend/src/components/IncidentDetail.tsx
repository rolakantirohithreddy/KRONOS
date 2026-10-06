import { motion, AnimatePresence } from 'framer-motion';
import { X, ShieldAlert, Activity, FileText, Wrench } from 'lucide-react';
import { RiskBadge } from './RiskBadge';
import { LatencyChart } from './LatencyChart';

export interface Incident {
  id: string;
  timestamp: string;
  attack_type: string;
  risk_label: string;
  risk_score: number;
  confidence: number;
  evidence: string[];
  mitre_technique_id: string;
  mitre_technique_name: string;
  mitre_description: string;
  mitigation: string;
  latency_ms: {
    rag: number;
    risk: number;
    evidence: number;
    mitigation: number;
    total: number;
  };
}

interface Props {
  incident: Incident | null;
  onClose: () => void;
}

export function IncidentDetail({ incident, onClose }: Props) {
  return (
    <AnimatePresence>
      {incident && (
        <>
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 0.5 }}
            exit={{ opacity: 0 }}
            onClick={onClose}
            className="fixed inset-0 bg-black z-40"
          />
          <motion.div
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 200 }}
            className="fixed top-0 right-0 h-full w-full max-w-md bg-[var(--bg-surface)] border-l border-[var(--border-color)] shadow-2xl z-50 overflow-y-auto"
          >
            <div className="p-6 flex flex-col h-full">
              <div className="flex items-center justify-between border-b border-[var(--border-color)] pb-4 mb-6">
                <div className="flex items-center gap-3">
                  <ShieldAlert className="text-[var(--accent-primary)]" />
                  <h2 className="text-xl font-bold">Incident Details</h2>
                </div>
                <button
                  onClick={onClose}
                  className="p-2 hover:bg-[var(--border-color)] rounded-full transition-colors text-[var(--text-muted)]"
                >
                  <X size={20} />
                </button>
              </div>

              <div className="space-y-8 flex-1">
                {/* Summary */}
                <section>
                  <div className="flex items-center justify-between mb-4">
                    <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider flex items-center gap-2">
                      <Activity size={16} /> Analysis
                    </h3>
                    <RiskBadge label={incident.risk_label} />
                  </div>
                  <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border-color)] space-y-3">
                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)]">Attack Type</span>
                      <span className="font-mono text-[var(--accent-secondary)]">{incident.attack_type}</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)]">Risk Score</span>
                      <span className="font-mono">{incident.risk_score}/100</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-[var(--text-muted)]">Confidence</span>
                      <span className="font-mono">{(incident.confidence * 100).toFixed(1)}%</span>
                    </div>
                  </div>
                </section>

                {/* Evidence */}
                <section>
                  <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-4 flex items-center gap-2">
                    <FileText size={16} /> Evidence
                  </h3>
                  <ul className="space-y-2">
                    {incident.evidence.map((ev, i) => (
                      <li key={i} className="flex gap-3 text-sm bg-[var(--bg-primary)] p-3 rounded-lg border border-[var(--border-color)]">
                        <span className="text-[var(--accent-primary)] mt-0.5">•</span>
                        <span>{ev}</span>
                      </li>
                    ))}
                  </ul>
                </section>

                {/* MITRE context */}
                <section>
                  <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-4 flex items-center gap-2">
                    <ShieldAlert size={16} /> MITRE ATT&CK
                  </h3>
                  <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border-color)]">
                    <div className="flex items-center gap-2 mb-2">
                      <span className="font-mono text-xs bg-[var(--border-color)] px-2 py-1 rounded text-[var(--text-primary)]">
                        {incident.mitre_technique_id}
                      </span>
                      <span className="font-semibold">{incident.mitre_technique_name}</span>
                    </div>
                    <p className="text-sm text-[var(--text-muted)]">{incident.mitre_description}</p>
                  </div>
                </section>

                {/* Mitigation */}
                <section>
                  <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-4 flex items-center gap-2">
                    <Wrench size={16} /> Recommendation
                  </h3>
                  <div className="bg-[var(--color-risk-low)]/10 border border-[var(--color-risk-low)]/30 p-4 rounded-lg">
                    <p className="text-sm text-[var(--text-primary)]">{incident.mitigation}</p>
                  </div>
                </section>

                {/* Latency */}
                <section>
                  <h3 className="text-sm font-semibold text-[var(--text-muted)] uppercase tracking-wider mb-4">
                    Agent Latency Breakdown
                  </h3>
                  <div className="bg-[var(--bg-primary)] p-4 rounded-lg border border-[var(--border-color)]">
                    <LatencyChart data={incident.latency_ms} />
                  </div>
                </section>
              </div>
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
