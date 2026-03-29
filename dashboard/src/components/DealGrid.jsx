import DealCard from './DealCard';

export default function DealGrid({ deals, total, loading, onDealClick, onLoadMore }) {
  if (loading && deals.length === 0) {
    return <div className="text-center py-12 text-slate-500">Loading deals...</div>;
  }

  if (deals.length === 0) {
    return (
      <div className="text-center py-12 text-slate-500">
        <p className="text-xs text-slate-500 mb-3">Showing 0 of 0 deals</p>
        No deals match your filters.
      </div>
    );
  }

  return (
    <div>
      <p className="text-xs text-slate-500 mb-3">
        Showing {deals.length} of {total.toLocaleString()} deals
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {deals.map(deal => (
          <DealCard key={deal.id} deal={deal} onClick={onDealClick} />
        ))}
      </div>

      {deals.length < total && (
        <div className="text-center mt-6">
          <button
            onClick={onLoadMore}
            disabled={loading}
            className="px-6 py-2 bg-slate-800 text-white rounded-lg text-sm hover:bg-slate-700 disabled:opacity-50"
          >
            {loading ? 'Loading...' : `Load More (${total - deals.length} remaining)`}
          </button>
        </div>
      )}
    </div>
  );
}
