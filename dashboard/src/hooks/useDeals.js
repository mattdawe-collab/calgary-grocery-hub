import { useState, useEffect, useCallback, useRef } from 'react';
import { fetchDeals } from '../api';

export function useDeals() {
  const [deals, setDeals] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [filters, setFilters] = useState({
    category: null,
    store: null,
    search: '',
    preset: null,
    sort: 'score_desc',
    offset: 0,
    limit: 60,
  });
  const requestId = useRef(0);

  useEffect(() => {
    setLoading(true);
    const id = ++requestId.current;
    const params = {};
    if (filters.category) params.category = filters.category;
    if (filters.store) params.store = filters.store;
    if (filters.search) params.search = filters.search;
    if (filters.preset) params.preset = filters.preset;
    params.sort = filters.sort;
    params.offset = filters.offset;
    params.limit = filters.limit;

    fetchDeals(params).then(data => {
      if (id !== requestId.current) return; // stale request, ignore
      if (filters.offset > 0) {
        setDeals(prev => [...prev, ...data.deals]);
      } else {
        setDeals(data.deals);
      }
      setTotal(data.total);
      setLoading(false);
    });
  }, [filters]);

  const updateFilter = useCallback((key, value) => {
    setFilters(prev => ({ ...prev, [key]: value, offset: 0 }));
  }, []);

  const loadMore = useCallback(() => {
    setFilters(prev => ({ ...prev, offset: prev.offset + prev.limit }));
  }, []);

  return { deals, total, loading, filters, updateFilter, setFilters, loadMore };
}
