import { useState, useEffect, useRef } from 'react';
import SearchBar from './SearchBar';
import FilterPanel from './FilterPanel';
import DateFilter from './DateFilter';
import api from '../api';

export default function Sidebar({ upid, replaceGraphData, mergeGraphData, filters, onFilterChange, onSummary, graphSummary, style }) {
  const [limit, setLimit] = useState(500);
  const [currentLevel, setCurrentLevel] = useState(null);
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

  // Level 1: Flagged network only
  const handleLoadFlagged = async () => {
    try {
      const res = await api.get(`/graph/flagged?${upidParam}`);
      replaceGraphData(res.data);
      setCurrentLevel(1);
      fetchSummary(res.data);
    } catch (err) {
      console.error('Load flagged error:', err);
    }
  };

  // Level 2: All people
  const handleLoadPeople = async () => {
    try {
      const res = await api.get(`/graph/people?${upidParam}`);
      replaceGraphData(res.data);
      setCurrentLevel(2);
    } catch (err) {
      console.error('Load people error:', err);
    }
  };

  // Level 3: Show all details
  const handleShowAll = async () => {
    try {
      const res = await api.get(`/graph/details?${upidParam}`);
      replaceGraphData(res.data);
      setCurrentLevel(3);
    } catch (err) {
      console.error('Details error:', err);
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

  // Auto-load Level 1 (flagged network) when UPID is in the URL
  useEffect(() => {
    if (upid && !autoLoaded.current) {
      autoLoaded.current = true;
      handleLoadFlagged();
    }
  }, [upid]);

  const buttonStyle = (level) => ({
    width: '100%',
    padding: '8px',
    background: currentLevel === level ? '#4CAF50' : '#455A64',
    border: currentLevel === level ? '2px solid #fff' : '2px solid transparent',
    borderRadius: '4px',
    color: '#fff',
    cursor: 'pointer',
    fontSize: '13px',
    marginBottom: '6px',
    fontWeight: currentLevel === level ? 'bold' : 'normal',
  });

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

      <button onClick={handleLoadFlagged} style={buttonStyle(1)}>
        Load PAX Network (Level I)
      </button>

      <button onClick={handleLoadPeople} style={buttonStyle(2)}>
        Load All People (Level II)
      </button>

      <button onClick={handleShowAll} style={buttonStyle(3)}>
        Show All Details (Level III)
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
            marginTop: '4px',
            marginBottom: '8px',
          }}
        >
          {summaryVisible ? 'Hide Summary' : 'Show Summary'}
        </button>
      )}

      <div style={{ marginTop: '10px' }}>
        <SearchBar upid={upid} replaceGraphData={replaceGraphData} />
      </div>

      {currentLevel === 3 && (
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
