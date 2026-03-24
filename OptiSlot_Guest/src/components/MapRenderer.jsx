import { useRef, useEffect, useCallback } from 'react';
import { getFloorLabel } from '../utils/astar';

/**
 * Node type → colour mapping
 */
const NODE_COLORS = {
    entry: '#10b981',      // emerald
    path: '#6b7280',       // gray
    landmark: '#0ea5e9',   // sky
    transition: '#f59e0b', // amber
    slot: '#8b5cf6',       // violet
};

const PATH_COLOR = '#4f46e5'; // Indigo
const PATH_GLOW = 'rgba(168, 85, 247, 0.4)'; // Violet glow
const BG_COLOR = 'transparent'; // Let CSS grid show through

/**
 * MapRenderer – draws the parking map on a canvas for a single floor.
 *
 * Props:
 *   nodes        – full nodes object from the graph
 *   floorNodes   – array of node IDs to render on current floor
 *   pathNodes    – array of node IDs in the A* path (for this floor)
 *   currentFloor – the floor number being displayed
 *   targetSlot   – the goal slot ID (highlighted)
 */
export default function MapRenderer({
    nodes,
    floorNodes,
    pathNodes = [],
    currentFloor,
    targetSlot,
    voiceEnabled = false,
    onDirectionChange = null,
}) {
    const canvasRef = useRef(null);
    const animRef = useRef(null);
    const progressRef = useRef(0);
    const spokenNodes = useRef(new Set());
    const lastVoiceTime = useRef(0);   // timestamp of last speech — prevents rapid overlapping
    const lastDirRef = useRef('straight'); // tracks last direction to avoid redundant setState calls

    useEffect(() => {
        spokenNodes.current.clear();
        lastVoiceTime.current = 0;
        lastDirRef.current = 'straight';
    }, [pathNodes.join(',')]);

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas || !nodes || !floorNodes || floorNodes.length === 0) return;

        const ctx = canvas.getContext('2d');
        const container = canvas.parentElement;
        const dpr = window.devicePixelRatio || 1;

        canvas.width = container.clientWidth * dpr;
        canvas.height = container.clientHeight * dpr;
        canvas.style.width = `${container.clientWidth}px`;
        canvas.style.height = `${container.clientHeight}px`;
        ctx.scale(dpr, dpr);

        const W = container.clientWidth;
        const H = container.clientHeight;

        // Calculate bounds for nodes on this floor
        const floorData = floorNodes.map((id) => ({ id, ...nodes[id] }));
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const n of floorData) {
            if (n.x < minX) minX = n.x;
            if (n.y < minY) minY = n.y;
            if (n.x > maxX) maxX = n.x;
            if (n.y > maxY) maxY = n.y;
        }

        const rangeX = maxX - minX || 1;
        const rangeY = maxY - minY || 1;
        const padding = 50;
        const scaleX = (W - padding * 2) / rangeX;
        const scaleY = (H - padding * 2) / rangeY;
        const scale = Math.min(scaleX, scaleY);

        const offsetX = (W - rangeX * scale) / 2;
        const offsetY = (H - rangeY * scale) / 2;

        function toScreen(x, y) {
            return {
                sx: (x - minX) * scale + offsetX,
                sy: (y - minY) * scale + offsetY,
            };
        }

        // --- BACKGROUND ---
        ctx.clearRect(0, 0, W, H);

        // --- EDGES ---
        // (Spider-web background edges removed for clean road styling)

        // --- PATH (Road Style) ---
        if (pathNodes.length > 1) {
            // Context setup for drawing the path
            const drawPathLine = () => {
                ctx.beginPath();
                for (let i = 0; i < pathNodes.length; i++) {
                    const node = nodes[pathNodes[i]];
                    if (!node || node.floor !== currentFloor) continue;
                    const p = toScreen(node.x, node.y);
                    if (i === 0 || (nodes[pathNodes[i - 1]]?.floor !== currentFloor)) {
                        ctx.moveTo(p.sx, p.sy);
                    } else {
                        ctx.lineTo(p.sx, p.sy);
                    }
                }
            };

            // Thick Road Base
            ctx.strokeStyle = 'rgba(255, 255, 255, 0.08)';
            ctx.lineWidth = 28;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            drawPathLine();
            ctx.stroke();

            // Inner Glow / Route Line
            ctx.strokeStyle = PATH_GLOW;
            ctx.lineWidth = 8;
            drawPathLine();
            ctx.stroke();

            // Solid core path
            ctx.strokeStyle = PATH_COLOR;
            ctx.lineWidth = 3;
            ctx.setLineDash([]);
            drawPathLine();
            ctx.stroke();
        }

        // --- NODES ---
        for (const n of floorData) {
            const isTarget = n.id === targetSlot;
            const isOnPath = pathNodes.includes(n.id);

            // Only draw path nodes or target for a clean look
            if (!isOnPath && !isTarget) continue;

            const p = toScreen(n.x, n.y);
            const color = NODE_COLORS[n.type] || '#6b7280';
            const radius = isTarget ? 12 : 6;

            // Target glow
            if (isTarget) {
                const pulse = 6 + Math.sin(Date.now() / 300) * 4;
                ctx.fillStyle = `${color}33`;
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, radius + pulse, 0, Math.PI * 2);
                ctx.fill();
            }

            // Node circle
            ctx.fillStyle = isOnPath ? color : `${color}88`;
            ctx.beginPath();
            ctx.arc(p.sx, p.sy, radius, 0, Math.PI * 2);
            ctx.fill();

            // White ring for target
            if (isTarget) {
                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 2;
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, radius + 2, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Label
            ctx.fillStyle = isOnPath ? 'var(--text-primary)' : 'rgba(255,255,255,0.35)';
            ctx.fillStyle = isOnPath ? '#f0f0f5' : 'rgba(255,255,255,0.35)';
            ctx.font = `${isTarget ? '600 11px' : '500 9px'} Inter, sans-serif`;
            ctx.textAlign = 'center';
            ctx.fillText(n.label, p.sx, p.sy - radius - 6);
        }

        // --- ANIMATED DOT AND VOICE ON PATH ---
        if (pathNodes.length > 1) {
            const floorPathNodes = pathNodes.filter(
                (id) => nodes[id] && nodes[id].floor === currentFloor
            );
            if (floorPathNodes.length > 1) {
                progressRef.current += 0.005; 
                if (progressRef.current > 1) progressRef.current = 1; // Stop at destination!

                const totalSegs = floorPathNodes.length - 1;
                const segT = progressRef.current * totalSegs;
                const idx = Math.min(Math.floor(segT), totalSegs - 1);
                const subT = segT - idx;

                const p1Node = nodes[floorPathNodes[idx]];
                const p2Node = nodes[floorPathNodes[idx + 1]];

                const p1 = toScreen(p1Node.x, p1Node.y);
                const p2 = toScreen(p2Node.x, p2Node.y);

                const dotX = p1.sx + (p2.sx - p1.sx) * subT;
                const dotY = p1.sy + (p2.sy - p1.sy) * subT;

                // Voice Trigger logic — fires only once per node segment with cooldown
                const now = Date.now();
                const cooldownOk = (now - lastVoiceTime.current) > 4000;
                
                // 1. ARRIVAL TRIGGER (at the very end)
                if (progressRef.current === 1 && !spokenNodes.current.has('arrival-done') && cooldownOk) {
                    spokenNodes.current.add('arrival-done');
                    const p2NodeId = floorPathNodes[idx + 1];
                    const isFinalDestination = p2NodeId === targetSlot;
                    const textToSpeak = isFinalDestination ? "You have arrived at your destination." : "Please proceed to the next floor.";
                    
                    if (onDirectionChange) {
                        onDirectionChange(isFinalDestination ? 'arrived' : 'transition');
                    }

                    if (voiceEnabled && 'speechSynthesis' in window) {
                        lastVoiceTime.current = now;
                        window.speechSynthesis.cancel();
                        const msg = new SpeechSynthesisUtterance(textToSpeak);
                        msg.lang = 'en-US';
                        window.speechSynthesis.speak(msg);
                    }
                    if ('vibrate' in navigator) navigator.vibrate([200, 100, 200]);
                }
                
                // 2. SEGMENT START TRIGGERS (Turns / Start)
                else if (subT < 0.1 && !spokenNodes.current.has(idx) && cooldownOk) {
                    spokenNodes.current.add(idx);
                    let textToSpeak = "";
                    let dirLabel = "straight";

                    if (idx === 0) {
                        const levelName = getFloorLabel(currentFloor);
                        textToSpeak = `Entering ${levelName}. Please proceed straight.`;
                        dirLabel = "straight";
                    } else {
                        const p0Node = nodes[floorPathNodes[idx - 1]];
                        const dx1 = p1Node.x - p0Node.x;
                        const dy1 = p1Node.y - p0Node.y;
                        const dx2 = p2Node.x - p1Node.x;
                        const dy2 = p2Node.y - p1Node.y;

                        const cross = dx1 * dy2 - dy1 * dx2;
                        if (cross > 0.5) {
                            textToSpeak = "Please turn right ahead.";
                            dirLabel = "right";
                        } else if (cross < -0.5) {
                            textToSpeak = "Please turn left ahead.";
                            dirLabel = "left";
                        } else {
                            dirLabel = "straight";
                        }
                    }

                    // Only update billboard state when direction actually changes (prevents re-render loop)
                    if (onDirectionChange && dirLabel !== lastDirRef.current) {
                        lastDirRef.current = dirLabel;
                        onDirectionChange(dirLabel);
                    }

                    if (voiceEnabled && textToSpeak && 'speechSynthesis' in window) {
                        lastVoiceTime.current = now;
                        window.speechSynthesis.cancel();
                        const msg = new SpeechSynthesisUtterance(textToSpeak);
                        msg.lang = 'en-US';
                        window.speechSynthesis.speak(msg);
                        if ('vibrate' in navigator) navigator.vibrate(200);
                    }
                }

                // Pulse Glow
                const pulseR = 15 + Math.sin(Date.now() / 200) * 8;
                ctx.fillStyle = 'rgba(168, 85, 247, 0.3)';
                ctx.beginPath();
                ctx.arc(dotX, dotY, pulseR, 0, Math.PI * 2);
                ctx.fill();

                // Advanced Car/Chevron Arrow
                ctx.save();
                ctx.translate(dotX, dotY);
                // Calculate rotation angle
                const angle = Math.atan2(p2.sy - p1.sy, p2.sx - p1.sx);
                ctx.rotate(angle);

                // Draw a sleek glowing chevron instead of a boring dot
                ctx.fillStyle = '#fff';
                ctx.shadowColor = '#a855f7';
                ctx.shadowBlur = 15;
                ctx.beginPath();
                ctx.moveTo(8, 0);       // Tip
                ctx.lineTo(-8, 6);      // Bottom wing
                ctx.lineTo(-4, 0);      // Inner cutout
                ctx.lineTo(-8, -6);     // Top wing
                ctx.closePath();
                ctx.fill();
                ctx.restore();
            }
        }

        animRef.current = requestAnimationFrame(draw);
    }, [nodes, floorNodes, pathNodes, currentFloor, targetSlot, voiceEnabled]);

    useEffect(() => {
        progressRef.current = 0;
        draw();
        return () => {
            if (animRef.current) cancelAnimationFrame(animRef.current);
        };
    }, [draw]);

    return (
        <div className="animate-scale-in" style={{ position: 'relative', width: '100%', height: 'calc(100vh - 200px)', minHeight: '300px' }}>
            {/* Canvas (Full bleed underlying layer) */}
            <div className="map-container" style={{ position: 'absolute', inset: 0, borderRadius: '1.25rem' }}>
                <canvas
                    ref={canvasRef}
                    style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}
                />
            </div>

            {/* Floating Glassmorphic Floor indicator Overlaid on Map */}
            <div className="glass-panel" style={{
                position: 'absolute',
                top: '1rem',
                left: '1rem',
                right: '1rem',
                padding: '0.75rem 1rem',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                zIndex: 10,
            }}>
                <span className={`floor-badge ${currentFloor === 0 ? 'floor-ground' : 'floor-basement'}`} style={{ margin: 0 }}>
                    {getFloorLabel(currentFloor)}
                </span>
                {targetSlot && (
                    <span style={{
                        fontSize: '0.75rem',
                        fontWeight: 600,
                        color: 'var(--text-primary)',
                        fontFamily: "'JetBrains Mono', monospace",
                    }}>
                        → {nodes[targetSlot]?.label || targetSlot}
                    </span>
                )}
            </div>
        </div>
    );
}
