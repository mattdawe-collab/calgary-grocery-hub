import { useState, useEffect } from 'react';
import { useInsights } from './hooks/useInsights';
import { useDeals } from './hooks/useDeals';
import { fetchStores } from './api';
import HeroSection from './components/HeroSection';
import FilterBar from './components/FilterBar';
import DealGrid from './components/DealGrid';
import DealDetail from './components/DealDetail';
import StoreComparison from './components/StoreComparison';
import CategoryBrowser from './components/CategoryBrowser';

const TABS = [
  { key: 'deals', label: 'Deals' },
  { key: 'stores', label: 'Stores' },
  { key: 'categories', label: 'Categories' },
];

export default function App() {
  const { insights, loading: insightsLoading } = useInsights();
  const { deals, total, loading: dealsLoading, filters, updateFilter, setFilters, loadMore } = useDeals();
  const [selectedDealId, setSelectedDealId] = useState(null);
  const [activeTab, setActiveTab] = useState('deals');
  const [storeNames, setStoreNames] = useState([]);

  useEffect(() => {
    fetchStores().then(data => {
      setStoreNames(data.map(s => s.name));
    });
  }, []);

  const handleDealClick = (id) => setSelectedDealId(id);
  const handleCloseDetail = () => setSelectedDealId(null);

  const handleSelectCategory = (name) => {
    setActiveTab('deals');
    // Clear all other filters so category count matches expectation
    setFilters(prev => ({
      ...prev,
      category: name,
      store: null,
      search: '',
      preset: null,
      offset: 0,
    }));
  };

  return (
    <div className="min-h-screen bg-slate-50">
      <div className="max-w-6xl mx-auto px-4 py-6">
        {/* Hero */}
        {!insightsLoading && (
          <HeroSection insights={insights} onDealClick={handleDealClick} />
        )}

        {/* Tabs */}
        <div className="flex gap-1 mb-5 border-b border-slate-200">
          {TABS.map(tab => (
            <button
              key={tab.key}
              onClick={() => setActiveTab(tab.key)}
              className={`px-4 py-2 text-sm font-medium border-b-2 transition-colors ${
                activeTab === tab.key
                  ? 'border-blue-600 text-blue-600'
                  : 'border-transparent text-slate-500 hover:text-slate-700'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>

        {/* Deals View */}
        {activeTab === 'deals' && (
          <>
            <FilterBar filters={filters} updateFilter={updateFilter} stores={storeNames} />
            <DealGrid
              deals={deals}
              total={total}
              loading={dealsLoading}
              onDealClick={handleDealClick}
              onLoadMore={loadMore}
            />
          </>
        )}

        {/* Stores View */}
        {activeTab === 'stores' && <StoreComparison />}

        {/* Categories View */}
        {activeTab === 'categories' && <CategoryBrowser onSelectCategory={handleSelectCategory} />}
      </div>

      {/* Deal Detail Slide-out */}
      {selectedDealId !== null && (
        <DealDetail dealId={selectedDealId} onClose={handleCloseDetail} />
      )}
    </div>
  );
}
