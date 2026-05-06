import { CATEGORY_ICONS, scoreBg } from '../constants';

function StatCard({ label, value, sub }) {
  return (
    <div className="bg-slate-800 rounded-lg p-4 text-center">
      <div className="text-2xl font-bold text-white">{value}</div>
      <div className="text-xs text-slate-400 mt-1">{label}</div>
      {sub && <div className="text-xs text-slate-500">{sub}</div>}
    </div>
  );
}

export default function HeroSection({ insights, onDealClick }) {
  if (!insights) return null;

  const validFrom = insights.valid_from ? new Date(insights.valid_from).toLocaleDateString('en-CA', { month: 'short', day: 'numeric' }) : '';
  const validUntil = insights.valid_until ? new Date(insights.valid_until).toLocaleDateString('en-CA', { month: 'short', day: 'numeric', year: 'numeric' }) : '';

  return (
    <div className="bg-slate-900 text-white p-6 rounded-xl mb-6">
      <div className="flex justify-between items-baseline mb-4">
        <h1 className="text-2xl font-bold">This Week's Deals</h1>
        {validFrom && <span className="text-sm text-slate-400">{validFrom} &ndash; {validUntil}</span>}
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-5">
        <StatCard label="Items at LOWEST PRICE EVER" value={insights.lowest_ever_count} />
        <StatCard label="Best Store This Week" value={insights.best_store?.name} sub={`Avg score ${insights.best_store?.avg_score}`} />
        <StatCard label="Hot Deals (80+)" value={insights.hot_deal_count} />
        <StatCard label="Staple Items on Sale" value={insights.kvi_on_sale} />
      </div>

      <div>
        <h3 className="text-xs font-semibold text-slate-400 uppercase tracking-wide mb-2">Top 5 Don't-Miss Deals</h3>
        <div className="space-y-1">
          {insights.top_5_deals?.map((deal, i) => (
            <button
              key={i}
              onClick={() => onDealClick(deal.id)}
              className="w-full flex items-center justify-between p-2 rounded hover:bg-slate-800 transition-colors text-left"
            >
              <div className="flex items-center gap-3 min-w-0">
                <span className={`${scoreBg(deal.deal_score)} text-white text-xs font-bold px-2 py-0.5 rounded`}>
                  {Math.round(deal.deal_score)}
                </span>
                <span className="text-sm truncate">{CATEGORY_ICONS[deal.category] || ''} {deal.item}</span>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-3">
                <span className="text-green-400 font-bold">${deal.price.toFixed(2)}</span>
                <span className="text-xs text-slate-500">{deal.store}</span>
              </div>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}
