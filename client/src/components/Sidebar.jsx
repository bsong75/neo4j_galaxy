import { useState, useEffect, useRef } from 'react';
import SearchBar from './SearchBar';
import FilterPanel from './FilterPanel';
import DateFilter from './DateFilter';
import api from '../api';

export default function Sidebar({ upid, replaceGraphData, mergeGraphData, filters, onFilterChange, onSummary, graphSummary, style }) {
  const [limit, setLimit] = useState(500);
  const [detailsLoaded, setDetailsLoaded] = useState(false);
  const [hasSummary, setHasSummary] = useState(false);
  const [summaryVisible, setSummaryVisible] = useState(false);
  const autoLoaded = useRef(false);
  const lastSummary = useRef('');

  // Sync summaryVisible when the overlay is dismissed via the X button in App
  useEffect(() => {
    setSummaryVisible(!!graphSummary);
  }, [graphSummary]);

  const upidParam = upid ? `upid=${encodeURIComponent(upid)}` : '';

  const fetchSummary = async (graphData) => {
    if (!onSummary) return;
    try {
      const res = await api.post('/graph/summarize', graphData);
      const summary = res.data.summary || '';
      lastSummary.current = summary;
      setHasSummary(!!summary);
      setSummaryVisible(!!summary);
      onSummary(summary);
    } catch (err) {
      console.error('Summary error:', err);
    }
  };

  const handleToggleSummary = () => {
    if (!onSummary || !lastSummary.current) return;
    if (summaryVisible) {
      onSummary('');
      setSummaryVisible(false);
    } else {
      onSummary(lastSummary.current);
      setSummaryVisible(true);
    }
  };

  const handleLoadGraph = async () => {
    try {
      const res = await api.get(`/graph/core?${upidParam}`);
      replaceGraphData(res.data);
      setDetailsLoaded(false);
      fetchSummary(res.data);
    } catch (err) {
      console.error('Load error:', err);
    }
  };

  const handleShowDetails = async () => {
    try {
      const res = await api.get(`/graph/details?${upidParam}`);
      mergeGraphData(res.data);
      setDetailsLoaded(true);
    } catch (err) {
      console.error('Details error:', err);
    }
  };

  const handleHideDetails = async () => {
    try {
      const res = await api.get(`/graph/core?${upidParam}`);
      replaceGraphData(res.data);
      setDetailsLoaded(false);
    } catch (err) {
      console.error('Load error:', err);
    }
  };

  const handleApplyFilters = async () => {
    try {
      const params = new URLSearchParams();
      if (upid) params.set('upid', upid);
      if (filters.nodeTypes?.length) params.set('nodeTypes', filters.nodeTypes.join(','));
      if (filters.relTypes?.length) params.set('relTypes', filters.relTypes.join(','));
      if (filters.dateFrom) params.set('dateFrom', filters.dateFrom);
      if (filters.dateTo) params.set('dateTo', filters.dateTo);
      if (limit) params.set('limit', limit);

      const res = await api.get(`/graph/filter?${params.toString()}`);
      replaceGraphData(res.data);
    } catch (err) {
      console.error('Filter error:', err);
    }
  };

  // Auto-load core graph when UPID is in the URL
  useEffect(() => {
    if (upid && !autoLoaded.current) {
      autoLoaded.current = true;
      handleLoadGraph();
    }
  }, [upid]);

  return (
    <div style={{
      background: 'var(--bg-sidebar)',
      borderRight: '1px solid var(--border-color)',
      padding: '16px',
      overflowY: 'auto',
      display: 'flex',
      flexDirection: 'column',
      flexShrink: 0,
      ...style,
    }}>
      <h2 style={{ color: 'var(--text-primary)', fontSize: '16px', margin: '0 0 16px 0' }}>
        Graph Explorer
      </h2>

      <button
        onClick={handleLoadGraph}
        style={{
          width: '100%',
          padding: '8px',
          background: '#607D8B',
          border: 'none',
          borderRadius: '4px',
          color: '#fff',
          cursor: 'pointer',
          fontSize: '13px',
          marginBottom: '8px',
        }}
      >
        Load PAX Network
      </button>

      {hasSummary && (
        <button
          onClick={handleToggleSummary}
          style={{
            width: '100%',
            padding: '8px',
            background: summaryVisible ? '#E91E63' : '#5C6BC0',
            border: 'none',
            borderRadius: '4px',
            color: '#fff',
            cursor: 'pointer',
            fontSize: '13px',
            marginBottom: '8px',
          }}
        >
          {summaryVisible ? 'Hide Summary' : 'Show Summary'}
        </button>
      )}

      <button
        onClick={detailsLoaded ? handleHideDetails : handleShowDetails}
        style={{
          width: '100%',
          padding: '8px',
          background: detailsLoaded ? '#E91E63' : '#4CAF50',
          border: 'none',
          borderRadius: '4px',
          color: '#fff',
          cursor: 'pointer',
          fontSize: '13px',
          marginBottom: '16px',
        }}
      >
        {detailsLoaded ? 'Hide Details' : 'Show All Details'}
      </button>

      <SearchBar upid={upid} replaceGraphData={replaceGraphData} />

      {detailsLoaded && (
        <>
          <hr style={{ border: 'none', borderTop: '1px solid var(--border-color)', margin: '8px 0 16px' }} />

          <div style={{ marginBottom: '12px' }}>
            <label style={{ fontSize: '12px', color: 'var(--text-muted)', marginBottom: '4px', display: 'block' }}>
              Result Limit (empty = all)
            </label>
            <input
              type="number"
              value={limit}
              onChange={(e) => setLimit(e.target.value ? parseInt(e.target.value) : '')}
              placeholder="No limit"
              style={{
                width: '100%',
                padding: '6px 8px',
                background: 'var(--bg-input)',
                border: '1px solid var(--border-light)',
                borderRadius: '4px',
                color: 'var(--text-primary)',
                fontSize: '13px',
                boxSizing: 'border-box',
              }}
            />
          </div>

          <FilterPanel filters={filters} onFilterChange={onFilterChange} />
          <DateFilter filters={filters} onFilterChange={onFilterChange} />

          <button
            onClick={handleApplyFilters}
            style={{
              width: '100%',
              padding: '6px',
              background: '#FF9800',
              border: 'none',
              borderRadius: '4px',
              color: '#fff',
              cursor: 'pointer',
              fontSize: '13px',
              marginBottom: '16px',
            }}
          >
            Apply Filters
          </button>
        </>
      )}

    </div>
  );
}
