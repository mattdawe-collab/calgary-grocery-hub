import { useState, useEffect } from 'react';
import { fetchDealHistory } from '../api';

export function useDealDetail(dealId) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (dealId === null) {
      setData(null);
      return;
    }
    setLoading(true);
    fetchDealHistory(dealId).then(result => {
      setData(result);
      setLoading(false);
    });
  }, [dealId]);

  return {
    deal: data?.deal,
    history: data?.price_history || [],
    crossStore: data?.cross_store_prices || [],
    stats: data?.stats || {},
    aiExplanation: data?.ai_explanation || '',
    loading,
  };
}
