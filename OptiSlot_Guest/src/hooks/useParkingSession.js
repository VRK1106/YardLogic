import { useState, useEffect, useCallback, useRef } from 'react';

const STORAGE_KEY = 'optislot_session';

/**
 * Manages the parking session.
 *
 * ONLINE  → always fetch fresh data from server, update localStorage as backup.
 * OFFLINE → fall back to localStorage cache.
 *
 * Session shape:
 *  { plate, assignedSlot, pinnedSlot, sessionId, entryTime, isRegistered }
 */
export function useParkingSession() {
    const [session, setSession] = useState(() => {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            return stored ? JSON.parse(stored) : null;
        } catch {
            return null;
        }
    });

    const [isOnline, setIsOnline] = useState(navigator.onLine);
    const refreshingRef = useRef(false);

    // ─── Online / Offline tracking ──────────────────────
    useEffect(() => {
        const goOnline = () => {
            setIsOnline(true);
            // Auto-refresh session from server when connectivity returns
            triggerServerRefresh();
        };
        const goOffline = () => setIsOnline(false);
        window.addEventListener('online', goOnline);
        window.addEventListener('offline', goOffline);
        return () => {
            window.removeEventListener('online', goOnline);
            window.removeEventListener('offline', goOffline);
        };
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    // ─── Persist to localStorage as offline backup ──────
    useEffect(() => {
        if (session) {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(session));
        }
    }, [session]);

    /**
     * Refresh session data from the server.
     * Called automatically when coming back online,
     * and can be called manually from components.
     */
    const refreshFromServer = useCallback(async (plate) => {
        const targetPlate = plate || session?.plate;
        if (!targetPlate || refreshingRef.current) return null;

        refreshingRef.current = true;
        try {
            const API_BASE = import.meta.env.VITE_API_URL ||
                (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
                    ? '' : `http://${window.location.hostname}:5000`);

            const res = await fetch(`${API_BASE}/api/find_vehicle/${encodeURIComponent(targetPlate)}`, {
                signal: AbortSignal.timeout(5000),
            });
            const data = await res.json();

            if (data.found) {
                setSession((prev) => {
                    const refreshed = {
                        plate: targetPlate,
                        assignedSlot: data.slot_id,
                        pinnedSlot: data.is_verified ? data.slot_id : (prev?.pinnedSlot || null), // auto-pin
                        sessionId: prev?.sessionId || generateId(),
                        entryTime: data.entry_time,
                        isRegistered: prev?.isRegistered || false,
                    };
                    localStorage.setItem(STORAGE_KEY, JSON.stringify(refreshed));
                    return refreshed;
                });
                return data;
            }
            return null;
        } catch {
            // Server unreachable – keep using cached data
            return null;
        } finally {
            refreshingRef.current = false;
        }
    }, [session?.plate]);

    /**
     * Internal trigger for auto-refresh on reconnect.
     */
    function triggerServerRefresh() {
        try {
            const stored = localStorage.getItem(STORAGE_KEY);
            if (stored) {
                const { plate } = JSON.parse(stored);
                if (plate) refreshFromServer(plate);
            }
        } catch { /* noop */ }
    }

    /**
     * Save a new session (called when online at the gate).
     */
    const saveSession = useCallback((data) => {
        const newSession = {
            plate: data.plate?.toUpperCase().replace(/\s/g, '') || '',
            assignedSlot: data.assignedSlot || null,
            pinnedSlot: data.pinnedSlot || null,
            sessionId: data.sessionId || generateId(),
            entryTime: data.entryTime || new Date().toISOString(),
            isRegistered: data.isRegistered || false,
        };
        setSession(newSession);
        return newSession;
    }, []);

    /**
     * Update specific fields without replacing the whole session.
     */
    const updateSession = useCallback((updates) => {
        setSession((prev) => {
            if (!prev) return prev;
            return { ...prev, ...updates };
        });
    }, []);

    /**
     * Pin a slot (after scanning slot QR).
     */
    const pinSlot = useCallback((slotId) => {
        setSession((prev) => {
            if (!prev) return prev;
            const updated = { ...prev, pinnedSlot: slotId };
            localStorage.setItem(STORAGE_KEY, JSON.stringify(updated));
            return updated;
        });
    }, []);

    /**
     * Privacy self-destruct: clear everything.
     */
    const clearSession = useCallback(() => {
        localStorage.removeItem(STORAGE_KEY);
        localStorage.removeItem('optislot_registered_plate');
        setSession(null);
    }, []);

    /**
     * Registered plate management (persists across sessions).
     */
    const getRegisteredPlate = useCallback(() => {
        return localStorage.getItem('optislot_registered_plate') || null;
    }, []);

    const registerPlate = useCallback((plate) => {
        const clean = plate.toUpperCase().replace(/\s/g, '');
        localStorage.setItem('optislot_registered_plate', clean);
        return clean;
    }, []);

    const unregisterPlate = useCallback(() => {
        localStorage.removeItem('optislot_registered_plate');
    }, []);

    return {
        session,
        isOnline,
        saveSession,
        updateSession,
        pinSlot,
        clearSession,
        refreshFromServer,
        getRegisteredPlate,
        registerPlate,
        unregisterPlate,
    };
}

/** Generate a UUID that works on HTTP (no crypto.randomUUID). */
function generateId() {
    if (typeof crypto?.randomUUID === 'function') return crypto.randomUUID();
    return 'xxxx-xxxx-xxxx'.replace(/x/g, () => ((Math.random() * 16) | 0).toString(16));
}
