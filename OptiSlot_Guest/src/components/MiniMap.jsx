import { useRef, useEffect, useCallback, useState } from 'react';

/**
 * MiniMap – renders a small overview of ALL floors in the parking facility.
 *
 * Props:
 *   nodes      – full nodes object from the graph
 *   pathNodes  – array of ALL node IDs in the A* path (across all floors)
 *   targetSlot – the goal slot ID
 *   currentFloor – the floor currently shown in the main MapRenderer
 */

const FLOOR_COLORS = {
    0: '#10b981',   // ground – emerald
    '-1': '#6366f1', // B1 – indigo
    '-2': '#8b5cf6', // B2 – violet
    '-3': '#ec4899', // B3 – pink
    1: '#0ea5e9',    // F1 – sky
};

export default function MiniMap({ nodes, pathNodes = [], targetSlot, currentFloor }) {
    const canvasRef = useRef(null);
    const animRef = useRef(null);
    const [expanded, setExpanded] = useState(false);

    const SIZE = expanded ? 240 : 120;

    const draw = useCallback(() => {
        const canvas = canvasRef.current;
        if (!canvas || !nodes) return;

        const allIds = Object.keys(nodes);
        if (allIds.length === 0) return;

        const ctx = canvas.getContext('2d');
        const dpr = window.devicePixelRatio || 1;

        canvas.width = SIZE * dpr;
        canvas.height = SIZE * dpr;
        canvas.style.width = `${SIZE}px`;
        canvas.style.height = `${SIZE}px`;
        ctx.scale(dpr, dpr);

        const W = SIZE;
        const H = SIZE;

        // Background
        ctx.fillStyle = 'rgba(10, 10, 15, 0.85)';
        ctx.beginPath();
        ctx.roundRect(0, 0, W, H, 12);
        ctx.fill();

        // Border
        ctx.strokeStyle = 'rgba(99, 102, 241, 0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.roundRect(0, 0, W, H, 12);
        ctx.stroke();

        // Compute bounds across ALL nodes
        let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity;
        for (const id of allIds) {
            const n = nodes[id];
            if (n.x < minX) minX = n.x;
            if (n.y < minY) minY = n.y;
            if (n.x > maxX) maxX = n.x;
            if (n.y > maxY) maxY = n.y;
        }

        const rangeX = maxX - minX || 1;
        const rangeY = maxY - minY || 1;
        const pad = expanded ? 20 : 12;
        const scale = Math.min((W - pad * 2) / rangeX, (H - pad * 2) / rangeY);
        const offX = (W - rangeX * scale) / 2;
        const offY = (H - rangeY * scale) / 2;

        function toS(x, y) {
            return {
                sx: (x - minX) * scale + offX,
                sy: (y - minY) * scale + offY,
            };
        }

        // --- Draw path (Thick Road style) ---
        if (pathNodes.length > 1) {
            const drawPathLine = () => {
                ctx.beginPath();
                for (let i = 0; i < pathNodes.length; i++) {
                    const n = nodes[pathNodes[i]];
                    if (!n) continue;
                    const p = toS(n.x, n.y);
                    if (i === 0) ctx.moveTo(p.sx, p.sy);
                    else ctx.lineTo(p.sx, p.sy);
                }
            };

            // Outer thick glow base
            ctx.strokeStyle = 'rgba(99, 102, 241, 0.15)';
            ctx.lineWidth = expanded ? 10 : 6;
            ctx.lineCap = 'round';
            ctx.lineJoin = 'round';
            drawPathLine();
            ctx.stroke();

            // Inner solid road
            ctx.strokeStyle = 'rgba(99, 102, 241, 0.8)';
            ctx.lineWidth = expanded ? 3.5 : 2;
            drawPathLine();
            ctx.stroke();
        }

        // --- Draw only target & path nodes ---
        const dotR = expanded ? 3 : 2;
        for (const id of allIds) {
            const n = nodes[id];
            const onPath = pathNodes.includes(id);
            const isTarget = id === targetSlot;

            if (!onPath && !isTarget) continue;

            const p = toS(n.x, n.y);
            const isCurrFloor = n.floor === currentFloor;

            if (isTarget) {
                // Pulsing target
                const pulse = 6 + Math.sin(Date.now() / 300) * 3;
                ctx.fillStyle = 'rgba(139, 92, 246, 0.35)'; // Violet glow
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, pulse + dotR, 0, Math.PI * 2);
                ctx.fill();

                ctx.fillStyle = '#8b5cf6';
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, dotR + 1.5, 0, Math.PI * 2);
                ctx.fill();

                ctx.strokeStyle = '#fff';
                ctx.lineWidth = 1.5;
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, dotR + 1.5, 0, Math.PI * 2);
                ctx.stroke();
            } else if (onPath) {
                ctx.fillStyle = isCurrFloor ? '#d8b4fe' : 'rgba(99,102,241,0.6)';
                ctx.beginPath();
                ctx.arc(p.sx, p.sy, dotR, 0, Math.PI * 2);
                ctx.fill();
            }
        }

        // --- Floor label & target label (expanded only) ---
        if (expanded && targetSlot && nodes[targetSlot]) {
            const t = nodes[targetSlot];
            const tp = toS(t.x, t.y);
            ctx.fillStyle = '#e4e4e7';
            ctx.font = "600 9px 'JetBrains Mono', monospace";
            ctx.textAlign = 'center';
            ctx.fillText(t.label || targetSlot, tp.sx, tp.sy - 10);
        }

        // "MINIMAP" label
        ctx.fillStyle = 'rgba(255,255,255,0.2)';
        ctx.font = `500 ${expanded ? '8' : '6'}px Inter, sans-serif`;
        ctx.textAlign = 'right';
        ctx.fillText('MAP', W - (expanded ? 10 : 6), H - (expanded ? 10 : 6));

        animRef.current = requestAnimationFrame(draw);
    }, [nodes, pathNodes, targetSlot, currentFloor, expanded, SIZE]);

    useEffect(() => {
        draw();
        return () => {
            if (animRef.current) cancelAnimationFrame(animRef.current);
        };
    }, [draw]);

    return (
        <div
            onClick={() => setExpanded((e) => !e)}
            style={{
                position: 'fixed',
                bottom: '5rem',
                right: '1rem',
                zIndex: 50,
                cursor: 'pointer',
                transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
                boxShadow: '0 8px 32px rgba(0,0,0,0.4)',
                borderRadius: '12px',
                overflow: 'hidden',
            }}
        >
            <canvas ref={canvasRef} />
        </div>
    );
}
