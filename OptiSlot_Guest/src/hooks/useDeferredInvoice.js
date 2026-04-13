import { useState, useEffect, useRef } from 'react';

const PENDING_KEY = 'optislot_pending_invoice';

/**
 * Green Channel Checkout – Deferred Invoice
 *
 * When a user exits without payment (no wallet / offline), the exit camera
 * logs their departure and the PWA stores a pending invoice in localStorage.
 * When the phone reconnects (e.g., above ground with 5G), this hook:
 *   1. Detects the `online` event
 *   2. POSTs the pending invoice to `/api/send_invoice`
 *   3. On success, clears the pending invoice and shows a banner
 *   4. Gives the user 48h to pay
 */
export function useDeferredInvoice() {
    const [invoiceBanner, setInvoiceBanner] = useState(null);
    const processingRef = useRef(false);

    useEffect(() => {
        function handleOnline() {
            processPendingInvoice();
        }

        // Check on mount if already online
        if (navigator.onLine) {
            processPendingInvoice();
        }

        window.addEventListener('online', handleOnline);
        return () => window.removeEventListener('online', handleOnline);
    }, []);

    async function processPendingInvoice() {
        if (processingRef.current) return;

        try {
            const raw = localStorage.getItem(PENDING_KEY);
            if (!raw) return;

            const invoice = JSON.parse(raw);
            processingRef.current = true;

            const API_BASE = import.meta.env.VITE_API_URL ||
                (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
                    ? '' : `http://${window.location.hostname}:5000`);

            const res = await fetch(`${API_BASE}/api/send_invoice`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(invoice),
                signal: AbortSignal.timeout(8000),
            });

            if (res.ok) {
                localStorage.removeItem(PENDING_KEY);
                setInvoiceBanner({
                    plate: invoice.plate,
                    amount: invoice.amount,
                    dueHours: 48,
                    status: 'sent',
                });

                // Auto-dismiss after 10 seconds
                setTimeout(() => setInvoiceBanner(null), 10000);
            }
        } catch {
            // Server not ready yet — will retry on next online event
        } finally {
            processingRef.current = false;
        }
    }

    /**
     * Store a pending invoice for deferred submission.
     * Call this from the checkout flow when the user exits without paying.
     */
    function storePendingInvoice(plate, amount, slot, durationSec) {
        // Billing is currently disabled.
        console.log(`[Deferred] Exited offline. Billing disabled for plate ${plate}.`);

        // const existing = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
        // existing.push({ plate, amount, slot, durationSec, timestamp: Date.now() });

        // localStorage.setItem(STORAGE_KEY, JSON.stringify(existing));
        // localStorage.setItem(PENDING_KEY, JSON.stringify(invoice)); // This line was likely intended to be commented out or removed.
    }

    function dismissBanner() {
        setInvoiceBanner(null);
    }

    return {
        invoiceBanner,
        storePendingInvoice,
        dismissBanner,
    };
}
