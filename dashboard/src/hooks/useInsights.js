import { useState, useEffect } from 'react';
import { fetchInsights } from '../api';

export function useInsights() {
  const [insights, setInsights] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchInsights().then(data => {
      setInsights(data);
      setLoading(false);
    });
  }, []);

  return { insights, loading };
}
