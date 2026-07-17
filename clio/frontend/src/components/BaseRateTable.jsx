export default function BaseRateTable({ table }) {
  if (!table || table.n_cases === 0) {
    return (
      <div className="text-sm text-parchment/60 italic">
        No base-rate data available. {table?.query_definition}
      </div>
    );
  }

  return (
    <div>
      <table className="w-full text-sm border-collapse">
        <thead>
          <tr className="text-left border-b border-parchment/20">
            <th className="py-1 pr-2">Outcome</th>
            <th className="py-1 pr-2 text-right">N</th>
            <th className="py-1 text-right">%</th>
          </tr>
        </thead>
        <tbody>
          {table.rows.map((row) => (
            <tr key={row.outcome} className="border-b border-parchment/10">
              <td className="py-1 pr-2">{row.outcome}</td>
              <td className="py-1 pr-2 text-right font-mono">{row.count}</td>
              <td className="py-1 text-right font-mono">{row.pct}%</td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="mt-2 text-xs text-parchment/60 space-y-1">
        <div>N = {table.n_cases} matching disputes ({table.source})</div>
        {table.mean_duration_days != null && (
          <div>Mean duration (approx.): {Math.round(table.mean_duration_days)} days</div>
        )}
        {table.escalation_to_war_rate != null && (
          <div>Escalation-to-war rate: {Math.round(table.escalation_to_war_rate * 100)}%</div>
        )}
        <details className="mt-1">
          <summary className="cursor-pointer text-parchment/50">Query definition</summary>
          <p className="mt-1">{table.query_definition}</p>
        </details>
      </div>
    </div>
  );
}
