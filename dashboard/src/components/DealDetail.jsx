import { useEffect } from 'react';
import { useDealDetail } from '../hooks/useDealDetail';
import { CATEGORY_ICONS, scoreColor, tagStyle } from '../constants';
import PriceHistoryChart from './PriceHistoryChart';
import CrossStoreChart from './CrossStoreChart';

function StatBox({ label, value }) {
  return (
    <div className="bg-slate-50 rounded-lg p-3 text-center">
      <div className="text-lg font-bold text-slate-800">{value ?? '—'}</div>
      <div className="text-[11px] text-slate-500">{label}</div>
    </div>
  );
}

export default function DealDetail({ dealId, onClose }) {
  const { deal, history, crossStore, stats, aiExplanation, loading } = useDealDetail(dealId);

  useEffect(() => {
    const handler = (e) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, [onClose]);

  // Prevent body scroll when panel is open
  useEffect(() => {
    document.body.style.overflow = 'hidden';
    return () => { document.body.style.overflow = ''; };
  }, []);

  if (dealId === null) return null;

  const score = Math.round(deal?.deal_score || 0);
  const color = scoreColor(score);
  const icon = CATEGORY_ICONS[deal?.category] || '';

  return (
    <>
      {/* Backdrop */}
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />

      {/* Panel */}
      <div className="fixed inset-y-0 right-0 w-full max-w-2xl bg-white shadow-2xl z-50 overflow-y-auto animate-slide-in">
        {loading || !deal ? (
          <div className="flex items-center justify-center h-full text-slate-500">Loading...</div>
        ) : (
          <div className="p-6">
            {/* Header */}
            <div className="flex items-start justify-between mb-4">
              <div className="flex-1 min-w-0 pr-4">
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-xs text-slate-500">{icon} {deal.category}</span>
                  {deal.sub_category && <span className="text-xs text-slate-400">/ {deal.sub_category}</span>}
                </div>
                <h2 className="text-xl font-bold leading-tight mb-1">{deal.item}</h2>
                <div className="flex items-baseline gap-3">
                  <span className="text-3xl font-bold text-green-700">${deal.price.toFixed(2)}</span>
                  <span className="text-sm text-slate-500">@ {deal.store}</span>
                </div>
                {deal.unit_price && deal.unit_type && (
                  <div className="text-xs text-slate-500 mt-1">${deal.unit_price.toFixed(2)} {deal.unit_type}</div>
                )}
              </div>
              <div className="flex items-center gap-3">
                <span
                  className="text-xl font-bold text-white px-3 py-1 rounded-lg"
                  style={{ backgroundColor: color }}
                >
                  {score}
                </span>
                <button
                  onClick={onClose}
                  className="text-slate-400 hover:text-slate-700 text-2xl leading-none p-1"
                >
                  &times;
                </button>
              </div>
            </div>

            {/* Tags */}
            {deal.tags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mb-5">
                {deal.tags.map(tag => (
                  <span key={tag} className={`text-xs px-2 py-0.5 rounded-full ${tagStyle(tag)}`}>
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {/* Price History Chart */}
            {history.length > 0 && (
              <div className="mb-5">
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Price History</h3>
                <PriceHistoryChart
                  data={history}
                  currentPrice={deal.price}
                  avgPrice={stats.historical_avg || 0}
                />
              </div>
            )}

            {/* Cross-Store Comparison */}
            {crossStore.length > 1 && (
              <div className="mb-5">
                <h3 className="text-sm font-semibold text-slate-700 mb-2">Cross-Store Prices</h3>
                <CrossStoreChart data={crossStore} currentStore={deal.store} />
              </div>
            )}

            {/* Stats Grid */}
            <div className="grid grid-cols-3 gap-2 mb-5">
              <StatBox
                label="All-Time Low"
                value={stats.historical_min != null ? `$${stats.historical_min.toFixed(2)}` : null}
              />
              <StatBox
                label="Average"
                value={stats.historical_avg != null ? `$${stats.historical_avg.toFixed(2)}` : null}
              />
              <StatBox
                label="All-Time High"
                value={stats.historical_max != null ? `$${stats.historical_max.toFixed(2)}` : null}
              />
              <StatBox
                label="Price Percentile"
                value={stats.price_percentile != null ? `${Math.round(stats.price_percentile)}th` : null}
              />
              <StatBox
                label="Times Seen"
                value={stats.historical_count || null}
              />
              <StatBox
                label="Sales/Month"
                value={stats.sale_frequency_per_month != null ? `~${stats.sale_frequency_per_month}x` : null}
              />
            </div>

            {/* Last on Sale */}
            {stats.last_on_sale && (
              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 mb-5 text-sm">
                <span className="font-medium text-blue-800">Last on sale:</span>{' '}
                <span className="text-blue-700">
                  {new Date(stats.last_on_sale.date).toLocaleDateString('en-CA', {
                    month: 'short', day: 'numeric', year: 'numeric'
                  })}
                  {' '}at ${stats.last_on_sale.price?.toFixed(2)} ({stats.last_on_sale.store})
                </span>
              </div>
            )}

            {/* AI Explanation — hide generic/empty messages */}
            {aiExplanation && !/no (historical|cross-store|data)|neutral score/i.test(aiExplanation) && (
              <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-5">
                <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wide mb-2">AI Analysis</h3>
                <p className="text-sm text-slate-700 leading-relaxed">{aiExplanation}</p>
              </div>
            )}

            {/* Additional Info */}
            <div className="border-t border-slate-200 pt-4 text-xs text-slate-500 space-y-1">
              {deal.brand && <div><span className="font-medium">Brand:</span> {deal.brand}</div>}
              {deal.normalized_name && <div><span className="font-medium">Normalized:</span> {deal.normalized_name}</div>}
              {deal.price_text && <div><span className="font-medium">Price Text:</span> {deal.price_text}</div>}
              {deal.price_basis && <div><span className="font-medium">Pricing:</span> {deal.price_basis}</div>}
            </div>
          </div>
        )}
      </div>
    </>
  );
}
