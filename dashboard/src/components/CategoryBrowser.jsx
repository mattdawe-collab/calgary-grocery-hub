import { useState, useEffect } from 'react';
import { fetchCategories } from '../api';
import { CATEGORY_ICONS, scoreColor } from '../constants';

export default function CategoryBrowser({ onSelectCategory }) {
  const [categories, setCategories] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchCategories().then(data => {
      setCategories(data);
      setLoading(false);
    });
  }, []);

  if (loading) return <div className="text-center py-8 text-slate-500">Loading categories...</div>;
  if (categories.length === 0) return null;

  return (
    <div>
      <h2 className="text-lg font-bold text-slate-800 mb-4">Browse by Category</h2>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
        {categories.map(cat => (
          <button
            key={cat.name}
            onClick={() => onSelectCategory(cat.name)}
            className="bg-white border border-slate-200 rounded-lg p-4 text-left hover:shadow-md hover:border-blue-300 transition-all"
          >
            <div className="text-3xl mb-2">{CATEGORY_ICONS[cat.name] || ''}</div>
            <div className="font-semibold text-sm text-slate-800">{cat.name}</div>
            <div className="flex items-center justify-between mt-2">
              <span className="text-xs text-slate-500">{cat.count} deals</span>
              <span
                className="text-xs font-bold text-white px-1.5 py-0.5 rounded"
                style={{ backgroundColor: scoreColor(cat.avg_score) }}
              >
                {cat.avg_score}
              </span>
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
