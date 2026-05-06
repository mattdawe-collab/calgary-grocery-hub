const BASE = '/api';

export async function fetchInsights() {
  const res = await fetch(`${BASE}/insights`);
  return res.json();
}

export async function fetchDeals(params = {}) {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v !== null && v !== undefined && v !== '') qs.set(k, v);
  });
  const res = await fetch(`${BASE}/deals?${qs}`);
  return res.json();
}

export async function fetchDealHistory(dealId) {
  const res = await fetch(`${BASE}/deals/${dealId}/history`);
  return res.json();
}

export async function fetchStores() {
  const res = await fetch(`${BASE}/stores`);
  return res.json();
}

export async function fetchCategories() {
  const res = await fetch(`${BASE}/categories`);
  return res.json();
}
