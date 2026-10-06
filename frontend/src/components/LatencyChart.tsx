interface LatencyData {
  rag: number;
  risk: number;
  evidence: number;
  mitigation: number;
  total: number;
}

interface LatencyChartProps {
  data: LatencyData;
}

export function LatencyChart({ data }: LatencyChartProps) {
  const maxVal = Math.max(data.rag, data.risk, data.evidence, data.mitigation, data.total);
  
  const items = [
    { label: 'RAG Retrieval', value: data.rag, color: 'var(--accent-primary)' },
    { label: 'Risk Analysis', value: data.risk, color: 'var(--accent-primary)' },
    { label: 'Evidence Gen', value: data.evidence, color: 'var(--accent-primary)' },
    { label: 'Mitigation Gen', value: data.mitigation, color: 'var(--accent-primary)' },
    { label: 'Total', value: data.total, color: 'var(--accent-secondary)' },
  ];

  return (
    <div className="space-y-3 font-mono text-sm">
      {items.map((item) => (
        <div key={item.label} className="flex flex-col gap-1">
          <div className="flex justify-between text-[var(--text-muted)] text-xs">
            <span>{item.label}</span>
            <span>{item.value.toFixed(2)} ms</span>
          </div>
          <div className="w-full bg-[var(--border-color)] h-2 rounded-full overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-1000 ease-out"
              style={{
                width: `${(item.value / maxVal) * 100}%`,
                backgroundColor: item.color
              }}
            />
          </div>
        </div>
      ))}
    </div>
  );
}
