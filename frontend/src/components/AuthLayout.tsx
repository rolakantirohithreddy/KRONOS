/**
 * AuthLayout — two-panel auth shell.
 *
 * LEFT  ~60%: NeuralSentinel animation + status ticker, confined to left panel.
 * RIGHT ~40%: floating card, upper-right positioned with 3D tilt.
 *
 * Both panels use the EXACT same base background: var(--bg-primary).
 * No per-panel gradient, no glow bleed, no color difference — zero seam.
 */

import { useState, useEffect, useRef, type ReactNode } from 'react';
import {
  motion,
  AnimatePresence,
  useMotionValue,
  useSpring,
  useTransform,
} from 'framer-motion';
import { NeuralSentinel } from './NeuralSentinel';

const TICKER_STEPS: { atMs: number; text: string }[] = [
  { atMs:     0, text: 'Monitoring 8 devices...'           },
  { atMs:  5000, text: '⚠ Anomaly detected: Smart Camera' },
  { atMs:  7500, text: 'Mitigating threat...'              },
  { atMs:  9000, text: '✅ Threat neutralized'             },
  { atMs: 10500, text: 'Monitoring 8 devices...'           },
];
const CYCLE = 13000;

interface AuthLayoutProps { children: ReactNode }

export function AuthLayout({ children }: AuthLayoutProps) {
  /* ── Ticker synced to cycle ── */
  const [tickerText, setTickerText] = useState(TICKER_STEPS[0].text);
  const [tickerKey,  setTickerKey]  = useState(0);

  useEffect(() => {
    const origin = Date.now();
    const tick = () => {
      const ms = (Date.now() - origin) % CYCLE;
      let text = TICKER_STEPS[0].text;
      for (const step of TICKER_STEPS) {
        if (ms >= step.atMs) text = step.text;
      }
      setTickerText(prev => {
        if (prev !== text) { setTickerKey(k => k + 1); return text; }
        return prev;
      });
    };
    const id = setInterval(tick, 250);
    return () => clearInterval(id);
  }, []);

  /* ── Card 3D tilt ── */
  const cardRef = useRef<HTMLDivElement>(null);
  const cmx = useMotionValue(0);
  const cmy = useMotionValue(0);
  const csx = useSpring(cmx, { stiffness: 260, damping: 26 });
  const csy = useSpring(cmy, { stiffness: 260, damping: 26 });
  const rotX = useTransform(csy, [-1, 1], [6, -6]);
  const rotY = useTransform(csx, [-1, 1], [-6, 6]);

  const onCardMove = (e: React.MouseEvent) => {
    const r = cardRef.current?.getBoundingClientRect();
    if (!r) return;
    cmx.set((e.clientX - r.left - r.width  / 2) / (r.width  / 2));
    cmy.set((e.clientY - r.top  - r.height / 2) / (r.height / 2));
  };
  const onCardLeave = () => { cmx.set(0); cmy.set(0); };

  return (
    <div
      className="flex min-h-screen w-full flex-col lg:flex-row"
      style={{ backgroundColor: 'var(--bg-primary)' }}
    >
      {/* ══════════ LEFT PANEL ══════════
          Flat background: var(--bg-primary).
          Animation is confined ONLY to this panel.
      */}
      <div
        className="relative h-[240px] flex-shrink-0 overflow-hidden lg:h-auto lg:w-[60%]"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        {/* NeuralSentinel canvas — confined to left panel */}
        <div className="absolute inset-0">
          <NeuralSentinel />
        </div>

        {/* Status ticker — bottom-left */}
        <div className="absolute bottom-5 left-5 z-10 hidden lg:block">
          <div className="auth-ticker overflow-hidden rounded-lg px-4 py-2.5">
            <div className="relative h-[18px] w-[260px]">
              <AnimatePresence mode="wait">
                <motion.span
                  key={tickerKey}
                  initial={{ opacity: 0, y: 7 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -7 }}
                  transition={{ duration: 0.28 }}
                  className="absolute inset-0 flex items-center font-mono text-[11px] tracking-wide"
                  style={{ color: 'var(--accent-primary)' }}
                >
                  {tickerText}
                </motion.span>
              </AnimatePresence>
            </div>
          </div>
        </div>
      </div>

      {/* ══════════ RIGHT PANEL ══════════
          Exact same flat background: var(--bg-primary).
          No gradients, no glow bleed, identical color tone.
      */}
      <div
        className="relative z-20 flex w-full flex-1 flex-col items-center justify-start p-6 pt-10 lg:items-end lg:pr-[8%] lg:pt-[13vh]"
        style={{ backgroundColor: 'var(--bg-primary)' }}
      >
        <div style={{ perspective: '1200px' }} className="w-full max-w-[440px]">
          <motion.div
            ref={cardRef}
            initial={{ opacity: 0, y: 26 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, ease: 'easeOut' }}
            style={{ rotateX: rotX, rotateY: rotY }}
            onMouseMove={onCardMove}
            onMouseLeave={onCardLeave}
            className="group relative w-full"
          >
            {/* Animated gradient border */}
            <div
              className="auth-gradient-border absolute -inset-[1px] opacity-55 transition-opacity duration-300 group-hover:opacity-100"
              aria-hidden
            />
            {/* Card surface */}
            <div className="auth-card-inner relative w-full p-7 sm:p-9">
              {children}
            </div>
          </motion.div>
        </div>
      </div>
    </div>
  );
}
