import { useRef, useState, useCallback, useEffect } from 'react';

/**
 * QRScanner – uses html5-qrcode to scan slot QR codes.
 *
 * Props:
 *   onScan(slotId) – called when a valid slot QR is decoded
 *   active – whether the scanner should be running
 */
export default function QRScanner({ onScan, active = false }) {
    const [scanning, setScanning] = useState(false);
    const [error, setError] = useState(null);
    const scannerRef = useRef(null);
    const readerRef = useRef(null);

    const startScanner = useCallback(async () => {
        if (scannerRef.current) return;
        setError(null);

        try {
            const { Html5Qrcode } = await import('html5-qrcode');
            const scanner = new Html5Qrcode('optislot-qr-reader');
            scannerRef.current = scanner;

            await scanner.start(
                { facingMode: 'environment' },
                { fps: 10, qrbox: { width: 220, height: 220 } },
                (decodedText) => {
                    // Extract slot ID from QR URL
                    let slotId = decodedText;
                    if (decodedText.includes('/scan/')) {
                        slotId = decodedText.split('/scan/')[1];
                    } else if (decodedText.includes('/qr/')) {
                        slotId = decodedText.split('/qr/')[1];
                    }
                    slotId = slotId.split('?')[0].split('/')[0].trim();

                    if (slotId) {
                        stopScanner();
                        onScan(slotId);
                    }
                },
                () => { } // ignore scan failures
            );

            setScanning(true);
        } catch (err) {
            setError('Camera access denied or unavailable.');
            console.error('QR Scanner error:', err);
        }
    }, [onScan]);

    const stopScanner = useCallback(async () => {
        if (scannerRef.current) {
            try {
                await scannerRef.current.stop();
                scannerRef.current.clear();
            } catch {
                // ignore
            }
            scannerRef.current = null;
            setScanning(false);
        }
    }, []);

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            stopScanner();
        };
    }, [stopScanner]);

    // Auto-stop when inactive
    useEffect(() => {
        if (!active && scanning) {
            stopScanner();
        }
    }, [active, scanning, stopScanner]);

    return (
        <div className="animate-fade-in flex flex-col text-white font-sans w-full" style={{ minHeight: '60vh' }}>
            {/* Camera Viewfinder */}
            <main className="flex-grow flex flex-col items-center justify-center relative p-6 mt-4">
                <div className="w-full aspect-square max-w-sm bg-neutral-900 rounded-3xl relative overflow-hidden shadow-2xl border border-white/5" style={{ minHeight: '300px' }}>

                    {/* The actual HTML5 QR reader target */}
                    <div id="optislot-qr-reader" ref={readerRef} style={{
                        width: '100%',
                        height: '100%',
                        position: 'absolute',
                        inset: 0,
                        zIndex: 10
                    }} />

                    {/* Viewfinder Brackets & Effects (Overlay) */}
                    <div className="absolute inset-0 pointer-events-none z-20">
                        {/* Simulating Camera Static/Feed Noise */}
                        <div className="absolute inset-0 opacity-20 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')]"></div>

                        {/* Top Left */}
                        <div className="viewfinder-corner top-6 left-6 border-t-4 border-l-4 rounded-tl-lg"></div>
                        {/* Top Right */}
                        <div className="viewfinder-corner top-6 right-6 border-t-4 border-r-4 rounded-tr-lg"></div>
                        {/* Bottom Left */}
                        <div className="viewfinder-corner bottom-6 left-6 border-b-4 border-l-4 rounded-bl-lg"></div>
                        {/* Bottom Right */}
                        <div className="viewfinder-corner bottom-6 right-6 border-b-4 border-r-4 rounded-br-lg"></div>

                        {/* Scanning Line Animation */}
                        {scanning && (
                            <div className="absolute inset-x-8 top-1/2 h-0.5 shadow-[0_0_15px_#6610f2] scanner-glow" style={{ backgroundColor: 'rgba(102, 16, 242, 0.5)' }}></div>
                        )}

                        {/* Instructional Text Overlay */}
                        <div className="absolute bottom-10 inset-x-0 text-center">
                            <span className="bg-black/40 backdrop-blur-md px-4 py-1.5 rounded-full text-xs font-medium text-white/70">
                                {scanning ? 'Align QR code within frame' : 'Camera OFF'}
                            </span>
                        </div>
                    </div>
                </div>

                {/* Error message */}
                {error && (
                    <div className="mt-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-500 text-xs w-full max-w-sm text-center">
                        {error}
                    </div>
                )}
            </main>

            {/* Action Footer */}
            <footer className="p-6 pb-10 z-50 mt-4">
                <div className="max-w-md mx-auto flex flex-col gap-4">
                    {/* Secondary Hint */}
                    <p className="text-center text-sm text-neutral-500 mb-2">
                        Can't find a QR code?
                        <button className="text-[#6610f2] font-medium underline underline-offset-4 ml-1">Pin manually</button>
                    </p>

                    {/* Primary Action Button */}
                    {!scanning ? (
                        <button
                            onClick={startScanner}
                            className="w-full py-5 px-8 hover:bg-[#520dc2] active:scale-[0.98] transition-all rounded-2xl flex items-center justify-center gap-3 shadow-[0_0_30px_rgba(102,16,242,0.3)]"
                            style={{ backgroundColor: 'var(--color-neon-indigo)' }}
                        >
                            <span aria-label="pin" className="text-2xl" role="img">📍</span>
                            <span className="text-lg font-bold uppercase tracking-tight text-white">I Have Parked - Scan Pillar</span>
                        </button>
                    ) : (
                        <button
                            onClick={stopScanner}
                            className="btn-secondary w-full py-4 rounded-2xl text-white"
                        >
                            Cancel Scanning
                        </button>
                    )}
                </div>
            </footer>
        </div>
    );
}
