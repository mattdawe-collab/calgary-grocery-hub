import { CATEGORY_ICONS, scoreColor, tagStyle } from '../constants';

export default function DealCard({ deal, onClick }) {
  const score = Math.round(deal.deal_score || 0);
  const borderColor = scoreColor(score);
  const icon = CATEGORY_ICONS[deal.category] || '\u{1F4E6}';

  return (
    <button
      onClick={() => onClick(deal.id)}
      className="w-full text-left bg-white rounded-lg border border-slate-200 p-4 hover:shadow-md hover:border-blue-300 cursor-pointer transition-all"
      style={{ borderLeftWidth: '4px', borderLeftColor: borderColor }}
    >
      <div className="flex justify-between items-start mb-1.5">
        <span className="text-xs text-slate-500">{icon} {deal.category}</span>
        <span
          className="text-xs font-bold text-white px-2 py-0.5 rounded-full"
          style={{ backgroundColor: borderColor }}
        >
          {score}
        </span>
      </div>

      <h3 className="font-semibold text-sm leading-tight mb-1 line-clamp-2">
        {deal.item}
      </h3>

      <div className="text-xl font-bold text-green-700 mb-1.5">
        ${deal.price.toFixed(2)}
        <span className="text-xs text-slate-500 font-normal ml-1">@ {deal.store}</span>
      </div>

      {deal.unit_price && deal.unit_type && (
        <div className="text-xs text-slate-500 mb-1.5">
          ${deal.unit_price.toFixed(2)} {deal.unit_type}
        </div>
      )}

      <div className="flex flex-wrap gap-1">
        {deal.tags.map(tag => (
          <span key={tag} className={`text-[10px] px-1.5 py-0.5 rounded-full ${tagStyle(tag)}`}>
            {tag}
          </span>
        ))}
      </div>
    </button>
  );
}
