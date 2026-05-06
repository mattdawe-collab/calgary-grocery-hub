export const CATEGORY_ICONS = {
  Produce: '\u{1F96C}',
  Beef: '\u{1F969}',
  Pork: '\u{1F437}',
  Poultry: '\u{1F357}',
  Lamb: '\u{1F411}',
  Seafood: '\u{1F41F}',
  'Dairy & Eggs': '\u{1F95B}',
  Bakery: '\u{1F956}',
  Pantry: '\u{1F35D}',
  Frozen: '\u{2744}\u{FE0F}',
  Beverages: '\u{1F964}',
  'Household & Personal': '\u{1F9F9}',
  Snacks: '\u{1F37F}',
  Other: '\u{1F4E6}',
};

export const STORE_COLORS = {
  'Walmart': '#0071CE',
  'Sobeys': '#E31837',
  'Real Canadian Superstore': '#E31937',
  'Safeway': '#E21A2C',
  'Calgary Co-op': '#DA291C',
  'No Frills': '#FDB813',
  'Save-On-Foods': '#ED1C24',
};

export function scoreColor(score) {
  if (score >= 80) return '#16a34a';
  if (score >= 60) return '#2563eb';
  if (score >= 40) return '#d97706';
  return '#94a3b8';
}

export function scoreBg(score) {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-blue-500';
  if (score >= 40) return 'bg-amber-500';
  return 'bg-slate-400';
}

export const TAG_STYLES = {
  'LOWEST EVER': 'bg-amber-100 text-amber-800 border border-amber-300',
  'Staple': 'bg-purple-100 text-purple-800 border border-purple-300',
  'Hot Deal': 'bg-red-100 text-red-800 border border-red-300',
};

export function tagStyle(tag) {
  if (TAG_STYLES[tag]) return TAG_STYLES[tag];
  if (tag.includes('below avg')) return 'bg-green-100 text-green-800 border border-green-300';
  if (tag.includes('Best of')) return 'bg-blue-100 text-blue-800 border border-blue-300';
  return 'bg-slate-100 text-slate-700 border border-slate-300';
}
