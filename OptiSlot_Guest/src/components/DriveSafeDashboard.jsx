import { useState, useEffect, useRef, useMemo } from 'react';

/**
 * DriveSafeDashboard – Glanceable driving UI.
 *
 * Replaces the detailed canvas map when the user is in driving mode.
 * Shows: massive directional arrow, slot number, floor badge,
 * and uses Web Speech API + Vibration API for eyes-free guidance.
 *
 * Props:
 *   graphNodes  – full node map from parkingGraph.json
 *   segments    – floor-segmented path from A*
 *   currentIdx  – current floor segment index
 *   targetSlot  – destination slot ID
 *   onFloorNext – callback to advance to next floor
 *   onFloorPrev – callback to go back a floor
 */
export default function DriveSafeDashboard({
    graphNodes,
    segments,
    currentIdx,
    targetSlot,
    onFloorNext,
    onFloorPrev,
}) {
    const segment = segments?.[currentIdx];
    const nextSegment = segments?.[currentIdx + 1];
    const prevSegment = segments?.[currentIdx - 1];
    const spokenRef = useRef(new Set());
    const [animPulse, setAnimPulse] = useState(false);

    // ─── Derive direction from path nodes ────────────────
    const direction = useMemo(() => {
        if (!segment?.nodes || segment.nodes.length < 2 || !graphNodes) return null;

        const nodes = segment.nodes;
        // Use the first two nodes for current bearing
        const from = graphNodes[nodes[0]];
        const to = graphNodes[nodes[1]];
        if (!from || !to) return null;

        const dx = to.x - from.x;
        const dy = to.y - from.y;

        // Thresholds for cardinal directions
        if (Math.abs(dx) > Math.abs(dy)) {
            return dx > 0 ? 'right' : 'left';
        } else {
            return dy > 0 ? 'down' : 'up';
        }
    }, [segment, graphNodes]);

    // Next turn direction (if path has 3+ nodes)
    const nextTurn = useMemo(() => {
        if (!segment?.nodes || segment.nodes.length < 3 || !graphNodes) return null;

        const nodes = segment.nodes;
        const a = graphNodes[nodes[0]];
        const b = graphNodes[nodes[1]];
        const c = graphNodes[nodes[2]];
        if (!a || !b || !c) return null;

        const dx1 = b.x - a.x;
        const dy1 = b.y - a.y;
        const dx2 = c.x - b.x;
        const dy2 = c.y - b.y;

        // Cross product for turn direction
        const cross = dx1 * dy2 - dy1 * dx2;
        if (Math.abs(cross) < 0.5) return 'straight';
        return cross > 0 ? 'right' : 'left';
    }, [segment, graphNodes]);

    const isLastFloor = currentIdx >= segments.length - 1;
    const slotLabel = graphNodes?.[targetSlot]?.label || targetSlot;
    const floorLabel = segment?.floor === 0 ? 'Ground' : `B${Math.abs(segment?.floor || 0)}`;

    // ─── Direction arrow config ──────────────────────────
    const arrowConfig = {
        up: { arrow: '↑', text: 'Straight Ahead', rotation: 0 },
        down: { arrow: '↓', text: 'Continue', rotation: 180 },
        left: { arrow: '←', text: 'Turn Left', rotation: -90 },
        right: { arrow: '→', text: 'Turn Right', rotation: 90 },
    };
    const current = arrowConfig[direction] || arrowConfig.up;

    // ─── Web Speech API ──────────────────────────────────
    useEffect(() => {
        if (!direction || !('speechSynthesis' in window)) return;

        const key = `${currentIdx}-${direction}`;
        if (spokenRef.current.has(key)) return;
        spokenRef.current.add(key);

        const msg = new SpeechSynthesisUtterance();
        msg.text = current.text + '. ' + (nextTurn === 'left' ? 'Then turn left.'
            : nextTurn === 'right' ? 'Then turn right.'
                : '');
        msg.rate = 0.9;
        msg.pitch = 1.0;
        msg.volume = 1.0;
        speechSynthesis.speak(msg);
    }, [direction, currentIdx, current.text, nextTurn]);

    // ─── Vibration API on direction change ───────────────
    useEffect(() => {
        if (direction && 'vibrate' in navigator) {
            navigator.vibrate(200);
            setAnimPulse(true);
            const t = setTimeout(() => setAnimPulse(false), 600);
            return () => clearTimeout(t);
        }
    }, [direction, currentIdx]);

    // ─── Speak floor transition ──────────────────────────
    function speakFloorArrival(floorNum) {
        if ('speechSynthesis' in window) {
            const label = floorNum === 0 ? 'Ground Floor' : `Basement ${Math.abs(floorNum)}`;
            const msg = new SpeechSynthesisUtterance(`Arrived at ${label}. Follow the path to your slot.`);
            msg.rate = 0.9;
            speechSynthesis.speak(msg);
        }
        if ('vibrate' in navigator) {
            navigator.vibrate([100, 50, 100, 50, 200]);
        }
    }

    return (
        <div style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '70vh',
            gap: '1.5rem',
            textAlign: 'center',
        }}>
            {/* Floor badge */}
            <div style={{
                padding: '0.5rem 1.25rem',
                borderRadius: '9999px',
                background: segment?.floor === 0
                    ? 'rgba(14, 165, 233, 0.12)' : 'rgba(139, 92, 246, 0.12)',
                border: `1px solid ${segment?.floor === 0
                    ? 'rgba(14, 165, 233, 0.25)' : 'rgba(139, 92, 246, 0.25)'}`,
                color: segment?.floor === 0 ? 'var(--accent-sky)' : 'var(--accent-violet)',
                fontSize: '0.75rem',
                fontWeight: 700,
                fontFamily: "'JetBrains Mono', monospace",
                letterSpacing: '0.1em',
                textTransform: 'uppercase',
            }}>
                {floorLabel}
            </div>

            {/* Giant directional arrow */}
            <div style={{
                width: '10rem',
                height: '10rem',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, rgba(99,102,241,0.15), rgba(139,92,246,0.15))',
                border: '2px solid rgba(99,102,241,0.3)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                transition: 'all 0.5s cubic-bezier(0.4, 0, 0.2, 1)',
                transform: animPulse ? 'scale(1.08)' : 'scale(1)',
                boxShadow: animPulse
                    ? '0 0 60px rgba(99, 102, 241, 0.3)'
                    : '0 0 30px rgba(99, 102, 241, 0.1)',
            }}>
                <span style={{
                    fontSize: '5rem',
                    fontWeight: 300,
                    lineHeight: 1,
                    color: 'var(--text-primary)',
                    transition: 'transform 0.3s ease',
                }}>
                    {current.arrow}
                </span>
            </div>

            {/* Direction text */}
            <div style={{
                fontSize: '1.25rem',
                fontWeight: 600,
                color: 'var(--text-secondary)',
                letterSpacing: '0.05em',
            }}>
                {current.text}
            </div>

            {/* Next turn preview */}
            {nextTurn && nextTurn !== 'straight' && (
                <div style={{
                    fontSize: '0.75rem',
                    color: 'var(--text-muted)',
                    padding: '0.375rem 0.875rem',
                    borderRadius: '9999px',
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                }}>
                    Then {nextTurn === 'left' ? '← Turn Left' : '→ Turn Right'}
                </div>
            )}

            {/* Target slot – massive */}
            <div style={{ marginTop: '0.5rem' }}>
                <div style={{
                    fontSize: '0.625rem',
                    fontWeight: 600,
                    letterSpacing: '0.2em',
                    textTransform: 'uppercase',
                    color: 'var(--text-muted)',
                    marginBottom: '0.25rem',
                }}>
                    YOUR SLOT
                </div>
                <div style={{
                    fontSize: '3rem',
                    fontWeight: 900,
                    fontFamily: "'JetBrains Mono', monospace",
                    letterSpacing: '-0.02em',
                    background: 'var(--gradient-primary)',
                    WebkitBackgroundClip: 'text',
                    WebkitTextFillColor: 'transparent',
                }}>
                    {slotLabel}
                </div>
            </div>

            {/* Floor progress */}
            {segments.length > 1 && (
                <div style={{
                    display: 'flex',
                    gap: '0.5rem',
                    alignItems: 'center',
                }}>
                    {segments.map((_, idx) => (
                        <div key={idx} style={{
                            width: idx === currentIdx ? '2rem' : '0.5rem',
                            height: '0.375rem',
                            borderRadius: '0.25rem',
                            background: idx === currentIdx ? 'var(--accent-indigo)' : 'rgba(255,255,255,0.12)',
                            transition: 'all 0.3s',
                        }} />
                    ))}
                    <span style={{
                        fontSize: '0.625rem',
                        color: 'var(--text-muted)',
                        fontFamily: "'JetBrains Mono', monospace",
                        marginLeft: '0.25rem',
                    }}>
                        {currentIdx + 1}/{segments.length}
                    </span>
                </div>
            )}

            {/* Floor transition buttons */}
            <div style={{ width: '100%', maxWidth: '320px', display: 'flex', flexDirection: 'column', gap: '0.5rem', marginTop: '0.5rem' }}>
                {!isLastFloor && nextSegment && (
                    <button
                        onClick={() => {
                            onFloorNext();
                            speakFloorArrival(nextSegment.floor);
                        }}
                        className="btn-primary"
                        style={{
                            width: '100%',
                            background: 'var(--gradient-warm)',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            gap: '0.5rem',
                            padding: '1rem 1.5rem',
                            fontSize: '1rem',
                        }}
                    >
                        <span>I've arrived at</span>
                        <strong>{nextSegment.floor === 0 ? 'Ground' : `Basement ${Math.abs(nextSegment.floor)}`}</strong>
                        <span>→</span>
                    </button>
                )}

                {prevSegment && (
                    <button
                        onClick={() => {
                            onFloorPrev();
                        }}
                        className="btn-secondary"
                        style={{ width: '100%' }}
                    >
                        ← Back to {prevSegment.floor === 0 ? 'Ground' : `B${Math.abs(prevSegment.floor)}`}
                    </button>
                )}

                {isLastFloor && (
                    <div style={{
                        padding: '0.75rem 1rem',
                        borderRadius: '0.75rem',
                        background: 'rgba(16, 185, 129, 0.1)',
                        border: '1px solid rgba(16, 185, 129, 0.2)',
                        color: 'var(--accent-emerald)',
                        fontSize: '0.875rem',
                        fontWeight: 600,
                        textAlign: 'center',
                    }}>
                        ✓ You're on the final floor — look for your slot!
                    </div>
                )}
            </div>
        </div>
    );
}
