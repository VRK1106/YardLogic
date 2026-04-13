/**
 * NavigationModeSelector – toggle between Driving and Walking nav modes.
 */
export default function NavigationModeSelector({ mode, onModeChange }) {
    return (
        <div style={{
            display: 'flex',
            gap: '0.5rem',
            marginBottom: '1rem',
        }}
            className="animate-fade-in"
        >
            <button
                onClick={() => onModeChange('driving')}
                style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                    padding: '0.75rem',
                    borderRadius: '0.75rem',
                    border: '1px solid',
                    borderColor: mode === 'driving' ? 'var(--accent-indigo)' : 'var(--border-subtle)',
                    background: mode === 'driving' ? 'rgba(99, 102, 241, 0.1)' : 'transparent',
                    color: mode === 'driving' ? 'var(--accent-indigo)' : 'var(--text-secondary)',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                }}
            >
                <span style={{ fontSize: '1.125rem' }}>🚗</span>
                <span>Gate → Slot</span>
            </button>

            <button
                onClick={() => onModeChange('walking')}
                style={{
                    flex: 1,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '0.5rem',
                    padding: '0.75rem',
                    borderRadius: '0.75rem',
                    border: '1px solid',
                    borderColor: mode === 'walking' ? 'var(--accent-emerald)' : 'var(--border-subtle)',
                    background: mode === 'walking' ? 'rgba(16, 185, 129, 0.1)' : 'transparent',
                    color: mode === 'walking' ? 'var(--accent-emerald)' : 'var(--text-secondary)',
                    fontSize: '0.8125rem',
                    fontWeight: 600,
                    cursor: 'pointer',
                    transition: 'all 0.2s',
                }}
            >
                <span style={{ fontSize: '1.125rem' }}>🚶</span>
                <span>Mall → Slot</span>
            </button>
        </div>
    );
}
