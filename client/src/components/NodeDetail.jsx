export default function NodeDetail({ node, onClose }) {
  if (!node) return null;

  return (
    <div style={{
      position: 'absolute',
      top: '16px',
      right: '16px',
      background: 'var(--bg-panel)',
      border: '1px solid var(--border-hover)',
      borderRadius: '8px',
      padding: '16px',
      minWidth: '250px',
      maxWidth: '350px',
      color: 'var(--text-primary)',
      zIndex: 10,
    }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '12px' }}>
        <span style={{
          background: node.color,
          padding: '2px 10px',
          borderRadius: '12px',
          fontSize: '12px',
          fontWeight: 'bold',
        }}>
          {node.label}
        </span>
        <button
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '16px' }}
        >
          x
        </button>
      </div>
      <table style={{ width: '100%', fontSize: '12px' }}>
        <tbody>
          {Object.entries(node.properties || {}).map(([key, value]) => (
            <tr key={key}>
              <td style={{ color: 'var(--text-dim)', padding: '2px 8px 2px 0', verticalAlign: 'top' }}>{key}</td>
              <td style={{ color: 'var(--text-secondary)', padding: '2px 0' }}>{String(value)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
