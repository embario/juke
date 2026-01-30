import { useLocation, useNavigate } from 'react-router-dom';

export default function GlobeOverlayNav() {
  const navigate = useNavigate();
  const location = useLocation();

  const params = new URLSearchParams(location.search);
  const isNative = params.get('native') === '1';

  if (isNative) {
    return null;
  }

  const handleHome = () => {
    const messageHandler = (window as { webkit?: { messageHandlers?: { jukeWorld?: { postMessage: (payload: object) => void } } } })
      .webkit?.messageHandlers?.jukeWorld;
    if (messageHandler) {
      messageHandler.postMessage({ type: 'exit' });
      return;
    }
    navigate('/');
  };

  return (
    <div
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        right: 0,
        padding: '16px 24px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: 'linear-gradient(180deg, rgba(0,0,0,0.6) 0%, rgba(0,0,0,0) 100%)',
        zIndex: 10,
        fontFamily: 'system-ui, -apple-system, sans-serif',
        pointerEvents: 'none',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, pointerEvents: 'auto' }}>
        <button
          onClick={handleHome}
          style={{
            background: 'rgba(255,255,255,0.1)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: 8,
            color: '#fff',
            padding: '6px 12px',
            cursor: 'pointer',
            fontSize: 13,
            fontWeight: 500,
            display: 'flex',
            alignItems: 'center',
            gap: 6,
            transition: 'background 0.2s',
          }}
          onMouseEnter={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.2)')}
          onMouseLeave={(e) => (e.currentTarget.style.background = 'rgba(255,255,255,0.1)')}
        >
          <span style={{ fontSize: 16 }}>&larr;</span>
          Home
        </button>
        <span
          style={{
            color: '#fff',
            fontSize: 20,
            fontWeight: 700,
            letterSpacing: '-0.5px',
          }}
        >
          Juke World
        </span>
      </div>

      <div
        style={{
          color: 'rgba(255,255,255,0.4)',
          fontSize: 12,
          pointerEvents: 'auto',
        }}
      >
        <span style={{ marginRight: 12 }}>Scroll to zoom</span>
        <span style={{ marginRight: 12 }}>Left-drag to spin</span>
        <span>Right-drag to tilt</span>
      </div>
    </div>
  );
}
