import { BarChart, Bar, XAxis, YAxis, Tooltip, Cell, ResponsiveContainer } from 'recharts';

export default function CrossStoreChart({ data, currentStore }) {
  if (!data || data.length <= 1) return null;

  return (
    <ResponsiveContainer width="100%" height={Math.max(120, data.length * 40)}>
      <BarChart data={data} layout="vertical" margin={{ top: 5, right: 40, left: 10, bottom: 5 }}>
        <XAxis type="number" tickFormatter={v => `$${v}`} tick={{ fontSize: 11 }} />
        <YAxis type="category" dataKey="store" width={110} tick={{ fontSize: 11 }} />
        <Tooltip formatter={(v) => `$${Number(v).toFixed(2)}`} />
        <Bar dataKey="price" label={{ position: 'right', formatter: v => `$${v.toFixed(2)}`, fontSize: 11 }}>
          {data.map((entry, i) => (
            <Cell key={i} fill={entry.store === currentStore ? '#16a34a' : '#94a3b8'} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
