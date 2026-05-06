import { useState, useEffect } from 'react';
import { fetchStores } from '../api';
import { STORE_COLORS, scoreColor } from '../constants';

export default function StoreComparison() {
  const [stores, setStores] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchStores().then(data => {
      setStores(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="text-center py-8 text-slate-500">Loading stores...</div>;
  if (stores.length === 0) return null;

  const maxScore = Math.max(...stores.map(s => s.avg_score));

  return (
    <div>
      <h2 className="text-lg font-bold text-slate-800 mb-4">Store Rankings</h2>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {stores.map((s, i) => {
          const barWidth = `${(s.avg_score / maxScore) * 100}%`;
          const color = STORE_COLORS[s.name] || '#64748b';

          return (
            <div key={s.name} className="bg-white border border-slate-200 rounded-lg p-4">
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg font-bold text-slate-300">#{i + 1}</span>
                  <span className="font-semibold text-slate-800">{s.name}</span>
                </div>
                <span
                  className="text-sm font-bold px-2 py-0.5 rounded text-white"
                  style={{ backgroundColor: scoreColor(s.avg_score) }}
                >
                  {s.avg_score}
                </span>
              </div>

              {/* Score bar */}
              <div className="h-2 bg-slate-100 rounded-full mb-3 overflow-hidden">
                <div className="h-full rounded-full" style={{ width: barWidth, backgroundColor: color }} />
              </div>

              <div className="grid grid-cols-4 gap-2 text-center text-xs">
                <div>
                  <div className="font-bold text-slate-800">{s.deal_count}</div>
                  <div className="text-slate-500">Deals</div>
                </div>
                <div>
                  <div className="font-bold text-slate-800">{s.hot_deals}</div>
                  <div className="text-slate-500">Hot</div>
                </div>
                <div>
                  <div className="font-bold text-amber-600">{s.lowest_ever}</div>
                  <div className="text-slate-500">Lowest Ever</div>
                </div>
                <div>
                  <div className="font-bold text-green-600">{s.avg_savings > 0 ? `${s.avg_savings}%` : '—'}</div>
                  <div className="text-slate-500">Avg Savings</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
