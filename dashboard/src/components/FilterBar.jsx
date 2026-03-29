import { useState, useEffect, useRef } from 'react';
import { CATEGORY_ICONS } from '../constants';
import { fetchCategories } from '../api';

const PRESETS = [
  { key: null, label: 'All Deals' },
  { key: 'lowest_ever', label: 'Lowest Ever' },
  { key: 'best_protein', label: 'Best Protein' },
  { key: 'under_5', label: 'Under $5' },
  { key: 'hot_deals', label: 'Hot Deals' },
  { key: 'staples', label: 'Staples' },
];

const SORT_OPTIONS = [
  { value: 'score_desc', label: 'Best Score' },
  { value: 'price_asc', label: 'Price: Low \u2192 High' },
  { value: 'price_desc', label: 'Price: High \u2192 Low' },
  { value: 'pct_below_desc', label: 'Biggest Savings' },
];

export default function FilterBar({ filters, updateFilter, stores }) {
  const [categories, setCategories] = useState([]);
  const [searchInput, setSearchInput] = useState('');
  const isFirstRender = useRef(true);

  useEffect(() => {
    fetchCategories().then(setCategories);
  }, []);

  // Debounce search — skip initial render to avoid duplicate API call
  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    const timer = setTimeout(() => {
      updateFilter('search', searchInput);
    }, 300);
    return () => clearTimeout(timer);
  }, [searchInput]);

  return (
    <div className="space-y-3 mb-5">
      {/* Row 1: Search + Sort */}
      <div className="flex gap-3">
        <input
          type="text"
          value={searchInput}
          onChange={e => setSearchInput(e.target.value)}
          placeholder="Search deals..."
          className="flex-1 px-3 py-2 border border-slate-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <select
          value={filters.sort}
          onChange={e => updateFilter('sort', e.target.value)}
          className="px-3 py-2 border border-slate-300 rounded-lg text-sm bg-white"
        >
          {SORT_OPTIONS.map(o => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>
      </div>

      {/* Row 2: Presets */}
      <div className="flex gap-2 flex-wrap">
        {PRESETS.map(p => (
          <button
            key={p.key || 'all'}
            onClick={() => updateFilter('preset', filters.preset === p.key ? null : p.key)}
            className={`px-3 py-1.5 rounded-full text-xs font-medium transition-colors ${
              filters.preset === p.key
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-700 hover:bg-slate-200'
            }`}
          >
            {p.label}
          </button>
        ))}
      </div>

      {/* Row 3: Category chips */}
      <div className="flex gap-1.5 flex-wrap">
        {categories.map(cat => (
          <button
            key={cat.name}
            onClick={() => updateFilter('category', filters.category === cat.name ? null : cat.name)}
            className={`px-2.5 py-1 rounded-full text-xs transition-colors ${
              filters.category === cat.name
                ? 'bg-blue-600 text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {CATEGORY_ICONS[cat.name] || ''} {cat.name}{!filters.search && !filters.store && !filters.preset ? ` (${cat.count})` : ''}
          </button>
        ))}
      </div>

      {/* Row 4: Store toggles */}
      <div className="flex gap-2 flex-wrap">
        {stores.map(s => (
          <button
            key={s}
            onClick={() => updateFilter('store', filters.store === s ? null : s)}
            className={`px-3 py-1 rounded-full text-xs font-medium transition-colors ${
              filters.store === s
                ? 'bg-slate-800 text-white'
                : 'bg-white text-slate-600 border border-slate-300 hover:bg-slate-50'
            }`}
          >
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}
