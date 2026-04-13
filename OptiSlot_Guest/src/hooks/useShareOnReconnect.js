import { useEffect, useRef } from 'react';

/**
 * Deferred Native Share – "Family Sync"
 *
 * When the driver parks underground (offline), pins their slot, and later
 * rides the elevator up, the phone detects connectivity. This hook:
 *   1. Fires a local Notification: "Parking saved at Slot C4. Tap to share."
 *   2. On click → opens the phone's native Share Sheet (navigator.share)
 *   3. Marks the session as shared to avoid repeated prompts.
 *
 * The share URL is a deep link: /?plate=XX&slot=YY — so family members
 * can pre-cache the route while still on WiFi.
 */
export function useShareOnReconnect(session, updateSession) {
    const triggeredRef = useRef(false);

    useEffect(() => {
        // Only proceed if we have a pinned slot and haven't shared yet
        if (!session?.pinnedSlot || session?._shared || triggeredRef.current) return;

        function handleOnline() {
            if (triggeredRef.current) return;
            triggeredRef.current = true;

            const slotLabel = session.pinnedSlot;
            const plate = session.plate;
            const shareUrl = `${window.location.origin}/?plate=${encodeURIComponent(plate)}&slot=${encodeURIComponent(slotLabel)}`;
            const shareTitle = `Find my car at ${slotLabel}`;
            const shareText = `I parked at ${slotLabel}. Open this link to get offline directions to my car.`;

            // Try notification first
            if ('Notification' in window && Notification.permission !== 'denied') {
                Notification.requestPermission().then((perm) => {
                    if (perm === 'granted') {
                        const notif = new Notification('🚗 Parking Saved', {
                            body: `Slot ${slotLabel} — Tap to share with family`,
                            icon: '/vite.svg',
                            tag: 'optislot-share',
                            requireInteraction: true,
                        });

                        notif.onclick = () => {
                            notif.close();
                            triggerShare(shareTitle, shareText, shareUrl);
                        };
                    } else {
                        // No notification permission — share directly
                        triggerShare(shareTitle, shareText, shareUrl);
                    }
                });
            } else {
                // Notifications not available — share directly
                triggerShare(shareTitle, shareText, shareUrl);
            }
        }

        // If already online and pinned, trigger immediately
        if (navigator.onLine) {
            handleOnline();
        }

        window.addEventListener('online', handleOnline);
        return () => window.removeEventListener('online', handleOnline);
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [session?.pinnedSlot, session?._shared]);

    async function triggerShare(title, text, url) {
        if (navigator.share) {
            try {
                await navigator.share({ title, text, url });
            } catch {
                // User cancelled — that's ok
            }
        }

        // Mark as shared regardless (avoid repeat prompts)
        if (updateSession) {
            updateSession({ _shared: true });
        }
    }
}
