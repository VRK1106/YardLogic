/**
 * API Service – connects to parking_proto_sensor.py Flask backend.
 *
 * In development, Vite's proxy forwards /api/* and /entry, /exit
 * to localhost:5000.  In production, VITE_API_URL should point to
 * the Cloudflare Tunnel or Render gateway URL.
 */

/**
 * Dynamic API base URL:
 *  - VITE_API_URL env var takes priority (e.g. Cloudflare Tunnel URL)
 *  - localhost  → empty string (Vite proxy forwards to Flask on :5000)
 *  - LAN IP    → http://<same-hostname>:5000 (direct to Flask, for mobile)
 */
const API_BASE = import.meta.env.VITE_API_URL ||
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? ''
        : `http://${window.location.hostname}:5000`);

async function request(url, options = {}) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);

    try {
        const res = await fetch(`${API_BASE}${url}`, {
            ...options,
            signal: controller.signal,
            headers: {
                'Content-Type': 'application/json',
                ...options.headers,
            },
        });
        clearTimeout(timeout);

        if (!res.ok) {
            const data = await res.json().catch(() => ({}));
            throw new Error(data.error || `HTTP ${res.status}`);
        }

        return await res.json();
    } catch (err) {
        clearTimeout(timeout);
        if (err.name === 'AbortError') {
            throw new Error('Request timed out – are you offline?');
        }
        throw err;
    }
}

/**
 * Register a vehicle entry.
 * Called at the gate when user has network.
 */
export async function registerEntry(regNum, vehicleSize = 'medium') {
    return request('/entry', {
        method: 'POST',
        body: JSON.stringify({ reg_num: regNum, vehicle_size: vehicleSize }),
    });
}

/**
 * Find a vehicle by registration number.
 * Returns: { found, slot_id, entry_time, is_verified, navigation }
 */
export async function findVehicle(regNum) {
    return request(`/api/find_vehicle/${encodeURIComponent(regNum)}`);
}

/**
 * Process vehicle exit and get billing info.
 * Returns: { message, freed_slot, duration_seconds }
 */
export async function processExit(regNum) {
    return request('/exit', {
        method: 'POST',
        body: JSON.stringify({ reg_num: regNum }),
    });
}

/**
 * Get current status of a specific slot.
 * Returns: { status, reg_num }
 */
export async function getSlotStatus(slotId) {
    return request(`/api/slot_status/${encodeURIComponent(slotId)}`);
}

/**
 * Verify parking – called after scanning slot QR.
 * Returns: { message } on success
 */
export async function verifyParking(slotId, regNum) {
    return request('/process_verification', {
        method: 'POST',
        body: JSON.stringify({
            slot_id: slotId,
            actual_reg_num: regNum,
            action: 'verify',
        }),
    });
}
