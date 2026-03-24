import { useState, useEffect, useMemo, useCallback } from 'react';
import { useParkingSession } from './hooks/useParkingSession';
import { useInstallPrompt } from './hooks/useInstallPrompt';
import { useShareOnReconnect } from './hooks/useShareOnReconnect';
import { useDeferredInvoice } from './hooks/useDeferredInvoice';
import { findPath, splitPathByFloor, getFloorLabel } from './utils/astar';
import * as api from './services/api';
import LandmarkSelector from './components/LandmarkSelector';
import MapRenderer from './components/MapRenderer';
import QRScanner from './components/QRScanner';
import NavigationModeSelector from './components/NavigationModeSelector';
import DriveSafeDashboard from './components/DriveSafeDashboard';

/*
  Screens:
    welcome    – guest QR landing  /  registered auto-login
    register   – save plate + "Add to Home Screen"
    navigate   – dual mode nav (driving or walking)
    pin        – scan slot QR to pin car location
    checkout   – exit + billing + clearSession
*/

export default function App() {
  const {
    session, isOnline, saveSession, updateSession, pinSlot,
    clearSession, getRegisteredPlate, registerPlate, unregisterPlate,
  } = useParkingSession();
  const { canInstall, isInstalled, installApp } = useInstallPrompt();
  useShareOnReconnect(session, updateSession);
  const { invoiceBanner, storePendingInvoice, dismissBanner } = useDeferredInvoice();

  const [screen, setScreen] = useState(() => {
    const params = new URLSearchParams(window.location.search);
    return (params.get('plate') && (params.get('slot') || params.get('t'))) ? 'navigate' : 'welcome';
  });
  const [plateInput, setPlateInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [graphData, setGraphData] = useState(null);

  // Navigation state
  const [navMode, setNavMode] = useState('driving'); // 'driving' | 'walking'
  const [landmarkId, setLandmarkId] = useState(null);
  const [currentFloorIdx, setCurrentFloorIdx] = useState(0);
  const [voiceEnabled, setVoiceEnabled] = useState(true);
  const [currentDirection, setCurrentDirection] = useState('straight'); // synced from MapRenderer

  // Checkout state
  const [exitResult, setExitResult] = useState(null);

  // Pin success
  const [pinSuccess, setPinSuccess] = useState(null);
  const [pinConfirmed, setPinConfirmed] = useState(false);

  // ─── Session Self-Destruct via BroadcastChannel ───────
  useEffect(() => {
    if (!('BroadcastChannel' in window)) return;
    const bc = new BroadcastChannel('optislot_control');
    bc.onmessage = (event) => {
      if (event.data?.action === 'SESSION_WIPE') {
        clearSession();
        setExitResult(null);
        setPinSuccess(null);
        setPinConfirmed(false);
        setScreen('welcome');
        setPlateInput('');
        setError(null);
      }
    };
    return () => bc.close();
  }, [clearSession]);

  // ─── Load graph data ──────────────────────────────────
  useEffect(() => {
    fetch('/parkingGraph.json')
      .then((r) => r.json())
      .then((data) => setGraphData(data))
      .catch(() => {
        // Try from cache/local
        try {
          const cached = localStorage.getItem('optislot_graph');
          if (cached) setGraphData(JSON.parse(cached));
        } catch { /* noop */ }
      });
  }, []);

  // Cache graph to localStorage for deep offline
  useEffect(() => {
    if (graphData) {
      localStorage.setItem('optislot_graph', JSON.stringify(graphData));
    }
  }, [graphData]);

  // ─── Auto-login for registered users ──────────────────
  useEffect(() => {
    if (session) {
      setScreen('navigate');
    } else {
      const registered = getRegisteredPlate();
      if (registered) {
        setPlateInput(registered);
        autoCheckVehicle(registered);
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [session]);

  // ─── Parse URL params for guest QR flow ───────────────
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const plate = params.get('plate');
    const slot = params.get('slot');
    const entryTime = params.get('t') || params.get('entry');
    if (plate && slot) {
      saveSession({
        plate,
        assignedSlot: slot,
        entryTime: entryTime ? new Date(parseInt(entryTime)).toISOString() : new Date().toISOString(),
      });
      setScreen('navigate');
      // Clean URL
      window.history.replaceState({}, '', '/');
    }
  }, [saveSession]);

  // ─── Force Find My Car mode if pinned ─────────────────
  useEffect(() => {
    if (session?.pinnedSlot) {
      setNavMode('walking');
    }
  }, [session?.pinnedSlot]);

  // ─── Guard: Prevent checkout without pin ───────────────
  useEffect(() => {
    if (screen === 'checkout' && !session?.pinnedSlot) {
      setScreen('navigate');
      setError('Please scan QR at Slot to pin your location first!');
    }
  }, [screen, session?.pinnedSlot]);

  // ─── Core functions ───────────────────────────────────
  async function autoCheckVehicle(plate) {
    if (!isOnline) {
      // Offline: check if we have a stored session
      if (session) {
        setScreen('navigate');
      }
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await api.findVehicle(plate);
      if (data.found) {
        saveSession({
          plate,
          assignedSlot: data.slot_id,
          pinnedSlot: data.is_verified ? data.slot_id : null, // admin backend bypass
          entryTime: data.entry_time,
          isRegistered: true,
        });
        setScreen('navigate');
      } else {
        setError('Vehicle not checked in yet. Please enter through the gate first.');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function handleGuestLogin() {
    const plate = plateInput.trim().toUpperCase().replace(/\s/g, '');
    if (plate.length < 4) {
      setError('Please enter a valid registration number');
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await api.findVehicle(plate);
      if (data.found) {
        saveSession({
          plate,
          assignedSlot: data.slot_id,
          pinnedSlot: data.is_verified ? data.slot_id : null, // admin backend bypass
          entryTime: data.entry_time,
        });
        setScreen('navigate');
      } else {
        setError('Vehicle not found. Please ensure your vehicle has entered the gate.');
      }
    } catch (err) {
      // If offline and we have no session, can't proceed
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  function handleRegister() {
    const plate = plateInput.trim().toUpperCase().replace(/\s/g, '');
    if (plate.length < 4) {
      setError('Please enter a valid registration number');
      return;
    }
    registerPlate(plate);
    setError(null);
    autoCheckVehicle(plate);
  }

  async function handleSlotPin(slotId) {
    pinSlot(slotId);
    setPinSuccess(slotId);

    // Also try to verify with backend if online
    if (isOnline && session?.plate) {
      try {
        await api.verifyParking(slotId, session.plate);
      } catch {
        // Verification failure is non-critical for the guest flow
      }
    }
  }

  // ─── Checkout: Option B ─────────────────────────────
  // PWA does NOT call /exit. It only shows billing info
  // and clears local data. The exit gate camera handles
  // actual slot release via LPR.
  function handleCheckout() {
    if (!session?.plate) return;

    // Billing disabled
    const bill = {
      plate: session.plate,
      slot: session.pinnedSlot || session.assignedSlot,
    };

    setExitResult(bill);
  }

  function handleFullClear() {
    clearSession();
    setExitResult(null);
    setPinSuccess(null);
    setScreen('welcome');
    setPlateInput('');
    setError(null);
  }

  // ─── Path calculation ─────────────────────────────────
  const pathResult = useMemo(() => {
    if (!graphData?.nodes || !session?.assignedSlot) return null;

    const targetSlot = session.pinnedSlot || session.assignedSlot;
    let startNode;

    if (navMode === 'driving') {
      startNode = 'entry_gate';
    } else {
      startNode = landmarkId;
    }

    if (!startNode || !graphData.nodes[startNode]) return null;

    // Find node that matches the slot - try direct ID first, then label match
    let goalId = null;
    if (graphData.nodes[targetSlot]) {
      goalId = targetSlot;
    } else {
      // Search by label
      for (const [id, node] of Object.entries(graphData.nodes)) {
        if (node.label === targetSlot || node.label.includes(targetSlot)) {
          goalId = id;
          break;
        }
      }
    }

    if (!goalId) return null;

    const result = findPath(graphData.nodes, startNode, goalId);
    if (result.path.length === 0) return null;

    const segments = splitPathByFloor(graphData.nodes, result.path);
    return { ...result, segments, goalId };
  }, [graphData, session, navMode, landmarkId]);

  // Floor nodes for current segment
  const currentSegment = pathResult?.segments?.[currentFloorIdx] || null;

  // Reset direction when switching floors
  useEffect(() => {
    setCurrentDirection('straight');
  }, [currentFloorIdx]);

  const floorNodes = useMemo(() => {
    if (!graphData?.nodes || currentSegment === null) return [];
    return Object.keys(graphData.nodes).filter(
      (id) => graphData.nodes[id].floor === currentSegment?.floor
    );
  }, [graphData, currentSegment]);

  // Reset floor index when path changes
  useEffect(() => {
    setCurrentFloorIdx(0);
  }, [pathResult?.path?.join(',')]);

  const targetSlotId = pathResult?.goalId || session?.pinnedSlot || session?.assignedSlot;

  // ─── RENDER ───────────────────────────────────────────

  return (
    <div style={{
      minHeight: '100dvh',
      display: 'flex',
      flexDirection: 'column',
      maxWidth: '480px',
      margin: '0 auto',
      position: 'relative',
    }}>
      {/* ─── TOP BAR ─── */}
      <header style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '1rem 1.25rem',
        position: 'sticky',
        top: 0,
        zIndex: 40,
        background: 'rgba(10, 10, 15, 0.85)',
        backdropFilter: 'blur(12px)',
      }}>
        <div style={{ fontWeight: 800, fontSize: '1.125rem', letterSpacing: '-0.02em' }}>
          Opti<span style={{ color: 'var(--accent-indigo)' }}>Slot</span>
        </div>
        <div className={`status-badge ${isOnline ? 'status-online' : 'status-offline'}`}>
          <span className={`status-dot ${isOnline ? 'online' : 'offline'}`} />
          {isOnline ? 'ONLINE' : 'OFFLINE'}
        </div>
      </header>

      {/* ─── INVOICE BANNER ─── */}
      {invoiceBanner && (
        <div style={{
          margin: '0 1.25rem',
          padding: '0.75rem 1rem',
          borderRadius: '0.75rem',
          background: 'rgba(16, 185, 129, 0.1)',
          border: '1px solid rgba(16, 185, 129, 0.2)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          animation: 'slide-up 0.4s ease-out',
        }}>
          <div>
            <div style={{ fontSize: '0.8125rem', fontWeight: 600, color: 'var(--accent-emerald)' }}>
              ✅ Invoice Sent
            </div>
            <div style={{ fontSize: '0.6875rem', color: 'var(--text-muted)', marginTop: '0.125rem' }}>
              ₹{invoiceBanner.amount} due within {invoiceBanner.dueHours}h — {invoiceBanner.plate}
            </div>
          </div>
          <button
            onClick={dismissBanner}
            style={{ background: 'none', border: 'none', color: 'var(--text-muted)', cursor: 'pointer', fontSize: '1rem' }}
          >
            ✕
          </button>
        </div>
      )}

      {/* ─── MAIN CONTENT ─── */}
      <main style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '0 1.25rem 6rem', overflowY: 'auto', overflowX: 'hidden' }}>

        {/* ━━━ WELCOME SCREEN (Screen 1 Template) ━━━ */}
        {screen === 'welcome' && (
          <div className="flex flex-col items-center justify-between flex-grow w-full text-white animate-fade-in relative z-10" style={{ fontFamily: 'Inter, sans-serif', minHeight: 'calc(100vh - 8rem)' }}>
            {/* Branding Header */}
            <header className="mt-8 text-center w-full">
              <h1 className="branding-font text-3xl font-bold tracking-widest text-white uppercase flex items-center justify-center gap-2">
                <span className="w-2 h-2 rounded-full animate-pulse" style={{ backgroundColor: 'var(--color-neon-cyan)' }}></span>
                OptiSlot
              </h1>
              <p className="text-[10px] text-zinc-500 uppercase tracking-[0.3em] mt-1">Edge AI Navigation</p>
            </header>

            {/* Main Visualizer & Form */}
            <main className="flex flex-col items-center justify-center flex-grow w-full max-w-sm mt-8 mb-4">
              <div className="relative flex items-center justify-center mb-8">
                {/* Outer Rotating Ring */}
                <svg className="w-48 h-48 ring-animation" viewBox="0 0 100 100">
                  <circle className="opacity-30" cx="50" cy="50" fill="none" r="45" stroke="var(--color-neon-cyan)" strokeDasharray="2, 6" strokeWidth="0.5"></circle>
                  <circle style={{ filter: 'drop-shadow(0 0 8px rgba(0,255,255,0.8))' }} cx="50" cy="50" fill="none" r="45" stroke="var(--color-neon-cyan)" strokeDasharray="40 160" strokeLinecap="round" strokeWidth="1.5"></circle>
                </svg>
                {/* Inner Content */}
                <div className="absolute flex flex-col items-center justify-center w-full px-8 text-center">
                  <span className="text-[10px] font-mono-tech opacity-60 mb-2" style={{ color: 'var(--color-neon-cyan)' }}>VEHICLE ID</span>

                  <input
                    type="text"
                    value={plateInput}
                    onChange={(e) => setPlateInput(e.target.value.toUpperCase())}
                    placeholder="SCAN OR TYPE"
                    className="font-mono-tech text-xl font-bold text-white tracking-widest text-center bg-transparent border-none outline-none w-full placeholder-zinc-600"
                    style={{ textShadow: '0 2px 10px rgba(0,0,0,0.5)' }}
                  />
                  <div className="mt-2 w-16 h-[1px]" style={{ backgroundColor: 'rgba(0, 255, 255, 0.3)' }}></div>
                </div>
              </div>

              <div className="w-full px-4 flex flex-col gap-3">
                <button
                  onClick={handleGuestLogin}
                  disabled={loading}
                  className="w-full py-4 text-sm font-bold tracking-wider text-black transition-all rounded-xl uppercase branding-font"
                  style={{
                    background: 'var(--color-neon-cyan)',
                    boxShadow: '0 0 15px rgba(0,255,255,0.4)',
                    opacity: loading ? 0.7 : 1
                  }}
                >
                  {loading ? 'CONNECTING EDGE...' : 'INITIALIZE ROUTING'}
                </button>

                <button
                  onClick={handleRegister}
                  className="w-full py-4 text-xs font-semibold tracking-widest transition-all border rounded-xl uppercase text-zinc-300 border-zinc-700 hover:bg-zinc-800"
                >
                  REGISTER NEW VEHICLE
                </button>
                {error && <p className="text-xs text-center text-red-500 mt-2 font-mono-tech">{error}</p>}
              </div>

              {/* Optional features restored */}
              <div className="w-full px-4 mt-6 flex flex-col gap-2 relative z-20">
                {getRegisteredPlate() && (
                  <div className="flex items-center justify-between p-3 border rounded-lg" style={{ borderColor: 'rgba(16, 185, 129, 0.3)', backgroundColor: 'rgba(16, 185, 129, 0.1)' }}>
                    <span className="text-xs" style={{ color: 'var(--accent-emerald)' }}>Registered: <strong className="font-mono-tech">{getRegisteredPlate()}</strong></span>
                    <button onClick={unregisterPlate} className="text-zinc-500 text-xs hover:text-white">✕</button>
                  </div>
                )}
                {canInstall && (
                  <button onClick={installApp} className="w-full py-3 text-xs tracking-widest transition-all border rounded-lg" style={{ color: 'var(--accent-emerald)', borderColor: 'rgba(16, 185, 129, 0.5)', backgroundColor: 'transparent' }}>
                    📱 INSTALL OFFLINE APP
                  </button>
                )}
                {isInstalled && (
                  <div className="text-[10px] text-zinc-500 text-center tracking-widest font-mono-tech uppercase mt-2">
                    ✅ Edge compute installed
                  </div>
                )}
              </div>
            </main>

            {/* Background Overlay */}
            <div className="fixed inset-0 pointer-events-none z-0">
              <div className="absolute inset-0 opacity-40" style={{ background: 'linear-gradient(to bottom, transparent, transparent, var(--color-deep-gray))' }}></div>
            </div>
          </div>
        )}

        {/* ━━━ NAVIGATE SCREEN ━━━ */}
        {
          screen === 'navigate' && session && (
            <div className="animate-fade-in stagger-children">
              {/* Session info */}
              <div style={{ marginTop: '0.5rem', marginBottom: '1.5rem' }}>
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.75rem',
                  marginBottom: '0.25rem',
                }}>
                  <h2 style={{ fontSize: '1.5rem', fontWeight: 700 }}>Navigation</h2>
                  <span style={{
                    padding: '0.2rem 0.5rem',
                    borderRadius: '0.375rem',
                    background: 'rgba(99, 102, 241, 0.12)',
                    border: '1px solid rgba(99, 102, 241, 0.2)',
                    fontSize: '0.625rem',
                    fontFamily: "'JetBrains Mono', monospace",
                    color: 'var(--accent-indigo)',
                  }}>
                    {session.plate}
                  </span>
                </div>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  Slot: <strong style={{ color: 'var(--accent-violet)', fontFamily: "'JetBrains Mono', monospace" }}>
                    {session.pinnedSlot || session.assignedSlot || '--'}
                  </strong>
                  {session.pinnedSlot && session.pinnedSlot !== session.assignedSlot && (
                    <span style={{ color: 'var(--text-muted)', fontSize: '0.6875rem' }}> (pinned)</span>
                  )}
                </p>
              </div>

              {/* Navigation mode toggle or Find My Car Banner */}
              {session.pinnedSlot ? (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '0.75rem',
                  borderRadius: '0.75rem',
                  background: 'rgba(16, 185, 129, 0.1)',
                  border: '1px solid rgba(16, 185, 129, 0.3)',
                  color: 'var(--accent-emerald)',
                  fontWeight: 600,
                  marginBottom: '1.5rem',
                  fontSize: '0.875rem'
                }}>
                  🚗 Find My Car Mode Active
                </div>
              ) : (
                <NavigationModeSelector mode={navMode} onModeChange={(m) => {
                  setNavMode(m);
                  setCurrentFloorIdx(0);
                  if (m === 'driving') setLandmarkId(null);
                }} />
              )}

              {/* Walking mode: show landmark selector */}
              {navMode === 'walking' && !landmarkId && graphData && (
                <LandmarkSelector
                  nodes={graphData.nodes}
                  onSelect={(id) => setLandmarkId(id)}
                  selectedId={landmarkId}
                />
              )}

              {/* Walking mode: selected landmark */}
              {navMode === 'walking' && landmarkId && graphData && (
                <div style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  marginBottom: '1rem',
                  padding: '0.625rem 0.875rem',
                  borderRadius: '0.75rem',
                  background: 'rgba(16, 185, 129, 0.08)',
                  border: '1px solid rgba(16, 185, 129, 0.15)',
                }}>
                  <span style={{ fontSize: '0.8125rem', color: 'var(--accent-emerald)' }}>
                    📍 From: <strong>{graphData.nodes[landmarkId]?.label}</strong>
                  </span>
                  <button onClick={() => setLandmarkId(null)} style={{
                    background: 'none', border: 'none', color: 'var(--text-muted)',
                    cursor: 'pointer', fontSize: '0.75rem',
                  }}>Change</button>
                </div>
              )}

              {/* Voice Toggle */}
              <div style={{
                display: 'flex',
                justifyContent: 'flex-end',
                marginBottom: '0.5rem',
              }}>
                <button
                  onClick={() => setVoiceEnabled(v => !v)}
                  style={{
                    background: 'var(--bg-card)',
                    border: '1px solid var(--border-subtle)',
                    color: voiceEnabled ? 'var(--accent-emerald)' : 'var(--text-muted)',
                    padding: '0.4rem 0.75rem',
                    borderRadius: '9999px',
                    fontSize: '0.75rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.375rem',
                    cursor: 'pointer',
                  }}
                >
                  {voiceEnabled ? '🔊 Voice On' : '🔇 Voice Off'}
                </button>
              </div>

              {/* Navigation Map / Billboard Dashboard */}
              {pathResult && currentSegment && graphData && (
                <div className="flex-grow w-full flex flex-col justify-between items-center p-4 text-center z-10 relative" style={{ minHeight: 'calc(100vh - 8rem)' }}>
                  {/* Background logic process for voice and tracking (Invisible) */}
                  <div className="absolute inset-0 opacity-0 pointer-events-none z-0 overflow-hidden">
                    <MapRenderer
                      nodes={graphData.nodes}
                      floorNodes={floorNodes}
                      pathNodes={currentSegment.nodes}
                      currentFloor={currentSegment.floor}
                      targetSlot={targetSlotId}
                      voiceEnabled={voiceEnabled}
                      onDirectionChange={(dir) => setCurrentDirection(dir)}
                    />
                  </div>

                  {/* ── BILLBOARD ── driven by MapRenderer onDirectionChange callback */}
                  {(() => {
                    const DIR_MAP = {
                      straight: { w1: 'GO', w2: 'STRAIGHT', color: 'text-neon-cyan', svgPath: <path d="M12 19V5m0 0l-7 7m7-7l7 7" strokeLinecap="round" strokeLinejoin="round" /> },
                      right:    { w1: 'TURN', w2: 'RIGHT',    color: 'text-parking-amber', svgPath: <path d="M5 12h14m0 0l-7-7m7 7l-7 7" strokeLinecap="round" strokeLinejoin="round" /> },
                      left:     { w1: 'TURN', w2: 'LEFT',     color: 'text-parking-amber', svgPath: <path d="M19 12H5m0 0l7-7m-7 7l7 7" strokeLinecap="round" strokeLinejoin="round" /> },
                      arrived:  { w1: 'YOU', w2: 'ARRIVED',  color: 'text-neon-green',  svgPath: <path d="M5 13l4 4L19 7" strokeLinecap="round" strokeLinejoin="round" /> },
                      transition: { w1: 'NEXT', w2: 'LEVEL',  color: 'text-parking-amber', svgPath: <path d="M5 10l7-7 7 7M12 3v18" strokeLinecap="round" strokeLinejoin="round" /> },
                    };
                    const d = DIR_MAP[currentDirection] || DIR_MAP.straight;
                    return (
                      <>
                        <header className="w-full pt-4 z-10" style={{ textShadow: '0 0 20px rgba(0,0,0,0.8)' }}>
                          <h1 className="text-5xl md:text-8xl font-black uppercase tracking-tighter leading-none neon-text-glow text-white">
                            {d.w1}<br />
                            <span className={d.color}>{d.w2}</span>
                          </h1>
                        </header>

                        <section className="flex-grow flex items-center justify-center w-full z-10 py-6">
                          <div className="animate-bounce-slow">
                            <svg className={`w-32 h-32 md:w-64 md:h-64 neon-icon-glow animate-pulse-slow ${d.color}`} fill="none" stroke="currentColor" strokeWidth="3" viewBox="0 0 24 24">
                              {d.svgPath}
                            </svg>
                          </div>
                        </section>
                      </>
                    );
                  })()}

                  <footer className="w-full pb-8 flex flex-col items-center justify-end z-10" style={{ minHeight: '30%' }}>
                    {currentFloorIdx < pathResult.segments.length - 1 ? (
                      <button
                        onClick={() => {
                          setCurrentFloorIdx((i) => i + 1);
                          if (window.navigator && window.navigator.vibrate) window.navigator.vibrate([100, 50, 100]);
                        }}
                        className="w-full bg-amoled-black border-4 md:border-8 border-parking-neon rounded-3xl flex flex-col items-center justify-center p-4 md:p-6 active:scale-95 transition-all duration-75 neon-border-glow shadow-2xl"
                        style={{ borderColor: 'var(--color-parking-neon)' }}
                      >
                        <span className="text-xl md:text-4xl font-black uppercase leading-tight text-white text-center">
                          Tap here when you reach<br />
                          <span className="text-parking-amber md:text-6xl text-3xl">{getFloorLabel(pathResult.segments[currentFloorIdx + 1].floor)}</span>
                        </span>
                      </button>
                    ) : navMode === 'driving' ? (
                      <button
                        onClick={() => {
                          setScreen('pin');
                          if (window.navigator && window.navigator.vibrate) window.navigator.vibrate([200, 100, 200]);
                        }}
                        disabled={currentDirection !== 'arrived'}
                        className={`w-full bg-amoled-black border-4 md:border-8 rounded-3xl flex flex-col items-center justify-center p-4 md:p-6 transition-all duration-300 ${
                          currentDirection === 'arrived' 
                            ? 'border-neon-green shadow-[0_0_30px_rgba(57,255,20,0.4)] active:scale-95 opacity-100' 
                            : 'border-zinc-800 opacity-40 grayscale pointer-events-none'
                        }`}
                      >
                        <span className="text-2xl md:text-5xl font-black uppercase leading-tight text-center text-white" style={{ textShadow: currentDirection === 'arrived' ? '0 0 10px rgba(57,255,20,0.8)' : 'none' }}>
                          📍 {currentDirection === 'arrived' ? 'I HAVE PARKED' : 'DRIVE TO SLOT'} <br />
                          <span className="text-lg md:text-2xl font-bold tracking-widest opacity-80" style={{ color: currentDirection === 'arrived' ? 'var(--color-neon-green)' : '#666' }}>
                            {currentDirection === 'arrived' ? 'TAP TO PIN LOCATION' : 'LOCKED UNTIL ARRIVAL'}
                          </span>
                        </span>
                      </button>
                    ) : (
                      <button
                        onClick={() => {
                          setScreen('checkout');
                          if (window.navigator && window.navigator.vibrate) window.navigator.vibrate([200, 100, 200]);
                        }}
                        disabled={currentDirection !== 'arrived' || !session?.pinnedSlot}
                        className={`w-full bg-amoled-black border-4 md:border-8 rounded-3xl flex flex-col items-center justify-center p-4 md:p-6 transition-all duration-300 ${
                          (currentDirection === 'arrived' && session?.pinnedSlot)
                            ? 'border-accent-emerald shadow-[0_0_30px_rgba(16,185,129,0.4)] active:scale-95 opacity-100 cursor-pointer' 
                            : 'border-zinc-800 opacity-40 grayscale cursor-not-allowed'
                        }`}
                      >
                        <span className="text-2xl md:text-5xl font-black uppercase leading-tight text-center text-white" style={{ textShadow: (currentDirection === 'arrived' && session?.pinnedSlot) ? '0 0 10px rgba(16,185,129,0.8)' : 'none' }}>
                          🚗 {currentDirection !== 'arrived' ? 'WALK TO CAR' : !session?.pinnedSlot ? 'PIN LOCATION FIRST' : 'REACHED CAR'}<br />
                          <span className="text-lg md:text-2xl font-bold tracking-widest opacity-80" style={{ color: (currentDirection === 'arrived' && session?.pinnedSlot) ? 'var(--accent-emerald)' : '#666' }}>
                            {currentDirection !== 'arrived' ? 'LOCKED UNTIL ARRIVAL' : !session?.pinnedSlot ? 'SCAN QR AT SLOT TO UNLOCK' : 'PROCEED TO CHECKOUT'}
                          </span>
                        </span>
                      </button>
                    )}

                    {currentFloorIdx > 0 && (
                      <button
                        onClick={() => setCurrentFloorIdx((i) => i - 1)}
                        className="mt-4 text-zinc-500 font-bold tracking-widest uppercase text-sm z-20 px-4 py-2"
                      >
                        Wait, go back to {getFloorLabel(pathResult.segments[currentFloorIdx - 1].floor)}
                      </button>
                    )}
                  </footer>
                </div>
              )}

              {/* No path or loading state */}
              {(navMode === 'driving' || landmarkId) && !pathResult && (
                <div style={{
                  textAlign: 'center',
                  padding: '3rem 1rem',
                  color: 'var(--text-muted)',
                  fontSize: '0.875rem',
                }}>
                  <div style={{ fontSize: '2.5rem', marginBottom: '1rem', opacity: 0.3 }}>🗺️</div>
                  {!session.assignedSlot && !session.pinnedSlot
                    ? 'No slot assigned yet. Scan the slot QR to pin your location.'
                    : 'Unable to calculate route. Please try a different starting point.'}
                </div>
              )}
            </div>
          )
        }

        {/* ━━━ PIN SCREEN ━━━ */}
        {
          screen === 'pin' && (
            <div className="animate-fade-in">
              <div style={{ marginTop: '0.5rem', marginBottom: '1.5rem' }}>
                <h2 style={{ fontSize: '1.5rem', fontWeight: 700, marginBottom: '0.25rem' }}>
                  Pin Location
                </h2>
                <p style={{ fontSize: '0.8125rem', color: 'var(--text-secondary)' }}>
                  Scan the QR code at your parking slot to pin your car's exact location.
                </p>
              </div>

              {!pinSuccess ? (
                <QRScanner
                  onScan={handleSlotPin}
                  active={screen === 'pin'}
                />
              ) : (
                <div className="animate-scale-in" style={{
                  textAlign: 'center',
                  padding: '3rem 1rem',
                }}>
                  {!pinConfirmed ? (
                    <>
                      <div style={{
                        width: '4rem',
                        height: '4rem',
                        borderRadius: '50%',
                        background: 'rgba(99, 102, 241, 0.15)',
                        border: '1px solid var(--accent-indigo)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '1.5rem',
                        margin: '0 auto 1.5rem',
                        boxShadow: 'var(--shadow-glow)'
                      }}>
                        📍
                      </div>
                      <div style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.5rem' }}>
                        Location Detected
                      </div>
                      <div style={{
                        fontSize: '2.5rem',
                        fontWeight: 800,
                        fontFamily: "'JetBrains Mono', monospace",
                        color: 'var(--text-primary)',
                        marginBottom: '1rem',
                        textShadow: '0 0 20px rgba(255,255,255,0.3)'
                      }}>
                        {graphData?.nodes?.[pinSuccess]?.label || pinSuccess}
                      </div>
                      <p style={{ fontSize: '0.875rem', color: 'var(--text-secondary)', marginBottom: '2rem' }}>
                        Is this your current parking slot?
                      </p>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
                        <button
                          onClick={() => setPinConfirmed(true)}
                          className="btn-primary"
                          style={{ background: 'var(--gradient-success)', width: '100%', padding: '1rem' }}
                        >
                          Confirm Parking
                        </button>
                        <button
                          onClick={() => { setPinSuccess(null); }}
                          className="btn-secondary"
                          style={{ width: '100%', border: 'none' }}
                        >
                          Rescan QR
                        </button>
                      </div>
                    </>
                  ) : (
                    <div className="animate-scale-in" style={{ padding: '2rem 0' }}>
                      <div style={{
                        width: '5rem',
                        height: '5rem',
                        borderRadius: '50%',
                        background: 'var(--gradient-success)',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '2rem',
                        margin: '0 auto 1.5rem',
                        boxShadow: '0 10px 30px rgba(16, 185, 129, 0.3)'
                      }}>
                        ✓
                      </div>
                      <h2 style={{ fontSize: '1.75rem', fontWeight: 800, marginBottom: '1rem', color: 'var(--text-primary)' }}>
                        Vehicle Secured!
                      </h2>
                      <p style={{ fontSize: '1rem', color: 'var(--text-secondary)', lineHeight: 1.6, marginBottom: '2rem' }}>
                        Have a great time! When you're ready to leave, just switch to the <strong style={{ color: 'var(--accent-emerald)' }}>Navigate</strong> tab and we'll guide you straight back to <strong style={{ color: 'white' }}>{graphData?.nodes?.[pinSuccess]?.label || pinSuccess}</strong>.
                      </p>
                      <button
                        onClick={() => setScreen('navigate')}
                        className="btn-secondary glass-card"
                        style={{ width: '100%', padding: '1rem', borderColor: 'rgba(255,255,255,0.1)' }}
                      >
                        Return to Map
                      </button>
                    </div>
                  )}
                </div>
              )}
            </div>
          )
        }

        {/* ━━━ CHECKOUT SCREEN (Screen 5 Template) ━━━ */}
        {
          screen === 'checkout' && (
            <div className="animate-fade-in flex flex-col flex-grow w-full mt-4 justify-between" style={{ fontFamily: 'Inter, sans-serif', minHeight: 'calc(100vh - 8rem)' }}>
              {/* Header Section */}
              <header className="pt-2 w-full text-white">
                <div className="flex items-center justify-between mb-8">
                  <button onClick={() => setScreen('navigate')} aria-label="Go back" className="p-2 -ml-2 text-zinc-400 hover:text-white transition-colors cursor-pointer">
                    <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path d="M15 19l-7-7 7-7" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2"></path>
                    </svg>
                  </button>
                  <h1 className="text-xl font-bold tracking-tight uppercase">Session Summary</h1>
                  <div className="w-10"></div>
                </div>
              </header>

              {!exitResult ? (
                <div className="flex flex-col items-center justify-center flex-grow w-full text-center">
                  <div className="w-20 h-20 rounded-3xl flex items-center justify-center text-4xl mb-6 shadow-2xl" style={{ backgroundColor: 'rgba(244, 63, 94, 0.15)', border: '1px solid rgba(244, 63, 94, 0.3)' }}>
                    💳
                  </div>
                  <h2 className="text-3xl font-bold mb-2 text-white">Ready to Leave?</h2>
                  <p className="text-sm text-zinc-400 mb-2 uppercase tracking-widest font-mono-tech">
                    Vehicle: <span className="text-white">{session?.plate}</span>
                  </p>
                  <p className="text-sm text-zinc-400 mb-8 uppercase tracking-widest font-mono-tech">
                    Slot: <span className="text-white">{session?.pinnedSlot || session?.assignedSlot || '--'}</span>
                  </p>

                  <button
                    onClick={handleCheckout}
                    className="w-full text-black font-black text-lg py-5 rounded-2xl tracking-tighter transition-transform active:scale-95 animate-pulse-neon cursor-pointer"
                    style={{ backgroundColor: 'var(--color-neon-green)', boxShadow: '0 0 20px rgba(57,255,20,0.4)' }}
                  >
                    VIEW BILL & CHECKOUT
                  </button>

                  <p className="mt-8 text-[11px] text-zinc-500 max-w-[280px] leading-relaxed uppercase tracking-widest font-mono-tech opacity-70">
                    Your slot will be freed automatically when the exit gate camera detects your vehicle leaving.
                  </p>
                </div>
              ) : (
                <>
                  {/* Exit Card Section */}
                  <section className="flex-grow flex flex-col justify-center w-full">
                    <div className="frosted-glass border border-white/10 rounded-3xl p-8 relative overflow-hidden shadow-2xl" style={{ backgroundColor: 'rgba(255, 255, 255, 0.03)' }}>
                      <div className="absolute top-0 right-0 p-4 opacity-20 text-white">
                        <svg fill="none" height="60" stroke="currentColor" strokeWidth="1" viewBox="0 0 24 24" width="60">
                          <path d="M12 22C17.5228 22 22 17.5228 22 12C22 6.47715 17.5228 2 12 2C6.47715 2 2 6.47715 2 12C2 17.5228 6.47715 22 12 22Z"></path>
                          <path d="M12 16V12M12 8H12.01"></path>
                        </svg>
                      </div>

                      <div className="mb-6">
                        <h2 className="text-4xl font-light tracking-tighter text-white">Ready to Leave</h2>
                        <p className="text-sm text-zinc-400 mt-2">Vehicle: {exitResult.plate}</p>
                      </div>

                      <div className="h-px w-full my-8" style={{ background: 'linear-gradient(to right, transparent, rgba(255,255,255,0.2), transparent)' }}></div>

                      <div className="mt-10 grid grid-cols-2 gap-4 text-[10px] text-zinc-500 uppercase tracking-widest font-medium">
                        <div>
                          <p>Parked at</p>
                          <p className="text-zinc-300 font-mono-tech mt-1">{exitResult.slot}</p>
                        </div>
                        <div className="text-right">
                          <p>Status</p>
                          <p className="text-zinc-300 font-mono-tech mt-1">{isOnline ? 'Synced' : 'Offline'}</p>
                        </div>
                      </div>
                    </div>
                  </section>

                  {/* Action Footer Section */}
                  <footer className="pb-8 space-y-6 mt-10 w-full text-white">

                    <button
                      onClick={(e) => {
                        e.currentTarget.innerText = "OPENING BARRIER...";
                        e.currentTarget.style.animation = "none";
                        handleFullClear();
                      }}
                      className="w-full text-black font-black text-lg py-6 rounded-2xl tracking-tighter transition-transform active:scale-95 cursor-pointer"
                      style={{
                        backgroundColor: 'var(--color-neon-green)',
                        boxShadow: '0 0 20px rgba(57,255,20,0.4)',
                        animation: isOnline ? 'pulse-neon 2s infinite ease-in-out' : 'none'
                      }}
                    >
                      OPEN EXIT BARRIER
                    </button>

                    <div className="flex flex-col items-center justify-center text-center space-y-2 pb-4">
                      <div className="flex items-center gap-2 text-zinc-500">
                        <svg className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2" viewBox="0 0 24 24">
                          <path d="M5 12.55a11 11 0 0 1 14.08 0"></path>
                          <path d="M1.42 9a16 16 0 0 1 21.16 0"></path>
                          <path d="M8.53 16.11a6 6 0 0 1 6.95 0"></path>
                          <line x1="12" x2="12.01" y1="20" y2="20"></line>
                        </svg>
                        <span className="text-[10px] uppercase tracking-[0.2em] font-mono-tech">Works offline. Syncs at exit.</span>
                      </div>
                    </div>
                  </footer>
                </>
              )}
            </div>
          )
        }
      </main >

      {/* ─── BOTTOM NAV BAR ─── */}
      {
        session && screen !== 'welcome' && (
          <nav className="nav-bar" style={{
            position: 'fixed',
            bottom: '1rem',
            left: '50%',
            transform: 'translateX(-50%)',
            width: 'calc(100% - 2.5rem)',
            maxWidth: '440px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-around',
            padding: '0.5rem 0.25rem',
            zIndex: 50,
          }}>
            <button
              onClick={() => setScreen('navigate')}
              className={`nav-item ${screen === 'navigate' ? 'active' : ''}`}
            >
              <span className="nav-icon">🗺️</span>
              <span>Navigate</span>
            </button>
            <button
              onClick={() => setScreen('pin')}
              className={`nav-item ${screen === 'pin' ? 'active' : ''}`}
            >
              <span className="nav-icon">📍</span>
              <span>Pin Car</span>
            </button>
            <button
              onClick={() => {
                if (!session?.pinnedSlot) {
                  setError("Please scan QR at Slot to pin your location first!");
                  return;
                }
                setScreen('checkout');
              }}
              className={`nav-item ${screen === 'checkout' ? 'active' : ''} ${!session?.pinnedSlot ? 'opacity-30 cursor-not-allowed grayscale' : ''}`}
            >
              <span className="nav-icon">💳</span>
              <span>Exit</span>
            </button>
          </nav>
        )
      }
    </div >
  );
}
