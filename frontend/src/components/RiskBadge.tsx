interface RiskBadgeProps {
  label: 'Low' | 'Medium' | 'High' | 'Critical' | string;
}

export function RiskBadge({ label }: RiskBadgeProps) {
  const getRiskColor = (lbl: string) => {
    switch (lbl.toLowerCase()) {
      case 'low': return 'var(--color-risk-low)';
      case 'medium': return 'var(--color-risk-medium)';
      case 'high': return 'var(--color-risk-high)';
      case 'critical': return 'var(--color-risk-critical)';
      default: return 'var(--text-muted)';
    }
  };

  const color = getRiskColor(label);

  return (
    <span
      className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-semibold"
      style={{
        backgroundColor: `color-mix(in srgb, ${color} 15%, transparent)`,
        color: color,
        border: `1px solid color-mix(in srgb, ${color} 30%, transparent)`
      }}
    >
      <span className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: color }}></span>
      {label}
    </span>
  );
}
