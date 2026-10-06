import { Incident } from '../components/IncidentDetail';

/**
 * Normalize an incident payload – handles two formats:
 *   1. Full pipeline report from /incident or /testing/run (has nested detection/risk_assessment/etc.)
 *   2. Compact DB summary from GET /incidents (has flat fields: attack_type, risk_label, etc.)
 */
export function normalizeIncident(data: any): Incident {
  const detection = data?.detection || {};
  const risk = data?.risk_assessment || {};
  const context = data?.context || {};
  const mitigation = data?.mitigation || {};
  const evidence = data?.evidence || {};
  const latencies = data?.agent_latencies_ms || data?.latency_ms || {};

  // For DB summary rows the full_report may be embedded; extract if present
  const fullReport = data?.full_report || {};
  const frDetection = fullReport?.detection || {};
  const frRisk = fullReport?.risk_assessment || {};
  const frContext = fullReport?.context || {};
  const frMitigation = fullReport?.mitigation || {};
  const frEvidence = fullReport?.evidence || {};
  const frLatencies = fullReport?.agent_latencies_ms || {};

  const rawScore = risk?.risk_score ?? frRisk?.risk_score ?? data?.risk_score;
  const scoreNumber = typeof rawScore === 'number'
    ? (rawScore <= 1.0 ? Math.round(rawScore * 100) : Math.round(rawScore))
    : 0;

  const rawEvidence = evidence?.evidence_statements ?? frEvidence?.evidence_statements ?? data?.evidence;
  const evidenceList: string[] = Array.isArray(rawEvidence)
    ? rawEvidence.map((e: any) => (typeof e === 'string' ? e : JSON.stringify(e)))
    : data?.evidence_summary
    ? [data.evidence_summary]
    : [];

  const effectiveLatencies = Object.keys(latencies).length > 0 ? latencies : frLatencies;

  return {
    id: data?.id?.toString() || data?.request_id || `inc-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    timestamp: data?.timestamp || detection?.timestamp || frDetection?.timestamp || new Date().toISOString(),
    attack_type: data?.attack_type || detection?.prediction || frDetection?.prediction || 'Unknown',
    risk_label: data?.risk_label || risk?.risk_label || frRisk?.risk_label || 'Low',
    risk_score: scoreNumber,
    confidence: typeof detection?.confidence === 'number'
      ? detection.confidence
      : typeof frDetection?.confidence === 'number'
      ? frDetection.confidence
      : (data?.confidence ?? 0),
    evidence: evidenceList.length > 0 ? evidenceList : ['Traffic behavior baseline recorded.'],
    mitre_technique_id: data?.mitre_technique_id || context?.mitre_technique || frContext?.mitre_technique || 'UNKNOWN',
    mitre_technique_name: data?.mitre_technique_name || context?.technique_name || frContext?.technique_name || 'Unrecognized Technique',
    mitre_description: data?.mitre_description || context?.description || frContext?.description || 'No detailed MITRE ATT&CK profile available for this detection.',
    mitigation: typeof data?.mitigation === 'string'
      ? data.mitigation
      : (mitigation?.recommended_action || frMitigation?.recommended_action || 'No specific containment action indicated.'),
    latency_ms: {
      rag: effectiveLatencies?.rag || 0,
      risk: effectiveLatencies?.risk || 0,
      evidence: effectiveLatencies?.evidence || 0,
      mitigation: effectiveLatencies?.mitigation || 0,
      total: effectiveLatencies?.total || data?.pipeline_latency_ms || 0,
    },
  };
}
