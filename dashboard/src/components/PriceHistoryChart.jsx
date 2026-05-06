import { LineChart, Line, XAxis, YAxis, Tooltip, ReferenceLine, ResponsiveContainer } from 'recharts';

export default function PriceHistoryChart({ data, currentPrice, avgPrice }) {
  if (!data || data.length === 0) return null;

  const formatted = data.map(d => ({
    ...d,
    dateLabel: d.date ? new Date(d.date).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' }) : '',
  }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={formatted} margin={{ top: 5, right: 10, left: 0, bottom: 5 }}>
        <XAxis dataKey="dateLabel" tick={{ fontSize: 11 }} />
        <YAxis tickFormatter={v => `$${v}`} tick={{ fontSize: 11 }} domain={['auto', 'auto']} />
        <Tooltip
          formatter={(v) => [`$${Number(v).toFixed(2)}`, 'Price']}
          labelFormatter={(_, payload) => payload?.[0]?.payload?.store || ''}
        />
        {avgPrice > 0 && (
          <ReferenceLine y={avgPrice} stroke="#94a3b8" strokeDasharray="5 5" />
        )}
        {currentPrice > 0 && (
          <ReferenceLine
            y={currentPrice}
            stroke={currentPrice <= avgPrice ? '#16a34a' : '#dc2626'}
            strokeDasharray="3 3"
          />
        )}
        <Line
          type="monotone"
          dataKey="price"
          stroke="#3b82f6"
          strokeWidth={2}
          dot={{ r: 4, fill: '#3b82f6' }}
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
