import { useMemo } from 'react';

/**
 * LandmarkSelector – lets user pick their current physical location
 * from a list of landmark + entry nodes in the parking graph.
 */
export default function LandmarkSelector({ nodes, onSelect, selectedId }) {
    const landmarks = useMemo(() => {
        if (!nodes) return [];
        return Object.entries(nodes)
            .filter(([, n]) => n.type === 'landmark' || n.type === 'entry')
            .map(([id, n]) => ({ id, ...n }));
    }, [nodes]);

    return (
        <div className="animate-fade-in flex flex-col w-full justify-center">
            <header className="pt-4 mb-8">
                <h1 className="text-4xl font-bold tracking-tight leading-tight text-white">
                    Where are you<br />right now?
                </h1>
                <p className="mt-4 text-gray-400 text-lg leading-relaxed">
                    Select your nearest landmark to route to your pinned car.
                </p>
            </header>

            <div className="grid grid-cols-2 gap-4 w-full">
                {landmarks.map((lm) => {
                    const isActive = selectedId === lm.id;
                    return (
                        <button
                            key={lm.id}
                            onClick={() => onSelect(lm.id)}
                            className={`glass-card aspect-square rounded-3xl flex flex-col items-center justify-center p-4 text-center focus:outline-none transition-all active:scale-95 ${isActive ? 'selected-card' : ''}`}
                        >
                            <div className={`mb-4 ${isActive ? 'text-[#39FF14]' : 'text-white'} opacity-90`}>
                                <svg fill="none" height="40" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.5" viewBox="0 0 24 24" width="40">
                                    {lm.type === 'entry' ? (
                                        <>
                                            <path d="M15 3h4a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-4"></path>
                                            <polyline points="10 17 15 12 10 7"></polyline>
                                            <line x1="15" x2="3" y1="12" y2="12"></line>
                                        </>
                                    ) : (
                                        <>
                                            <rect height="18" rx="2" width="18" x="3" y="3"></rect>
                                            <path d="m9 10 3-3 3 3"></path>
                                            <path d="m9 14 3 3 3-3"></path>
                                        </>
                                    )}
                                </svg>
                            </div>
                            <span className="text-sm font-medium tracking-wide text-white">{lm.label}</span>
                            <span className="text-xs text-gray-500 mt-1">Floor {lm.floor === 0 ? 'G' : `B${Math.abs(lm.floor)}`}</span>
                        </button>
                    );
                })}
            </div>
        </div>
    );
}
