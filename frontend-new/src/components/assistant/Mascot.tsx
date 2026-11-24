import { useEffect, useLayoutEffect, useRef, useState, type AnimationEvent, type CSSProperties } from 'react';
import type { RobotMode } from '@/store/doctor';
import { cn } from '@/utils/cn';

/**
 * Mascotte de l'assistant, en deux tenues : chatbot (apparence d'origine) et docteur
 * (blouse blanche, stéthoscope, miroir frontal). La boîte reste à 92×104 px : le vol
 * vers le bandeau du tiroir (FLIP, GlobalAssistantPanel) mesure cette largeur.
 *
 * À chaque changement de mode (jamais au premier rendu), une classe transitoire
 * `is-changing-to-doctor` / `is-changing-to-chat` déclenche l'animation de changement
 * de tenue (keyframes dans index.css). Elle est retirée en fin d'animation, ou par
 * un délai de sécurité si l'événement `animationend` n'arrive pas.
 */

type Change = 'to-doctor' | 'to-chat';

/** Délai de sécurité : un peu plus que l'animation la plus longue (1,1 s). */
export const CHANGE_SAFETY_MS = 1_400;

/** Animations qui marquent la fin du changement de tenue (mouvement normal ou réduit). */
const FINAL_ANIMATIONS = new Set([
  'mascotSuitUp',
  'mascotSuitDown',
  'mascotOutfitFadeIn',
  'mascotOutfitFadeOut',
]);

/* Blouse : blanche dans les deux thèmes, contour ardoise pour la détacher du fond clair. */
const COAT = '#fbfcfe';
const COAT_LINE = '#9aa9bf';
const LAPEL = '#e6ecf4';
const STETHO = '#334155';

/** Croix médicale (SVG 10×10), rouge du thème. */
export function MedicalCross({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 10 10" className={className} aria-hidden="true" focusable="false">
      <path d="M3.5 0h3v3.5H10v3H6.5V10h-3V6.5H0v-3h3.5z" className="fill-danger" />
    </svg>
  );
}

/** Petit avatar à côté des messages ; en mode docteur, une pastille à croix rouge. */
export function BotAvatar({ mode }: { mode: RobotMode }) {
  return (
    <div
      aria-hidden="true"
      data-mode={mode}
      className="relative flex h-[30px] w-[30px] flex-none items-center justify-center gap-1 rounded-[9px] bg-primary"
    >
      <span className="h-[5px] w-[5px] rounded-full bg-[#8fe3ee]" />
      <span className="h-[5px] w-[5px] rounded-full bg-[#8fe3ee]" />
      {mode === 'doctor' && (
        <span
          data-part="avatar-cross"
          className="absolute -right-1.5 -top-1.5 flex h-[15px] w-[15px] items-center justify-center rounded-full border border-[#9aa9bf] bg-white"
        >
          <MedicalCross className="h-2 w-2" />
        </span>
      )}
    </div>
  );
}

/** Blouse posée sur le corps : col en V, revers, poche avec stylo et croix rouge. */
function Coat() {
  return (
    <svg
      data-part="coat"
      viewBox="0 0 60 40"
      className="m-doc m-coat absolute left-4 top-16 h-10 w-[60px] overflow-visible"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M14 1H46Q59 1 59 14V35Q59 40 54 40H6Q1 40 1 35V14Q1 1 14 1Z"
        fill={COAT}
        stroke={COAT_LINE}
        strokeWidth="1.5"
      />
      {/* Tenue de bloc visible dans le col */}
      <path d="M21 6L30 26L39 6Z" className="fill-primary" />
      {/* Revers */}
      <path d="M21 6L30 26L18 16L15 8Z" fill={LAPEL} stroke={COAT_LINE} strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M39 6L30 26L42 16L45 8Z" fill={LAPEL} stroke={COAT_LINE} strokeWidth="1.2" strokeLinejoin="round" />
      <path d="M30 26V40" stroke={LAPEL} strokeWidth="1.2" />
      {/* Stylo puis poche (le stylo dépasse de la poche) */}
      <rect x="49" y="20" width="2.4" height="9" rx="1" className="fill-primary" />
      <rect x="41" y="26" width="12" height="9" rx="1.5" fill={COAT} stroke={COAT_LINE} strokeWidth="1.2" />
      <path d="M46 27.5h2v2h2v2h-2v2h-2v-2h-2v-2h2z" className="fill-danger" />
    </svg>
  );
}

/** Stéthoscope autour du cou (sous la tête), pavillon sur la poitrine. */
function Stethoscope() {
  return (
    <svg
      data-part="stethoscope"
      viewBox="0 0 48 40"
      className="m-doc m-stetho absolute left-[22px] top-16 h-10 w-12 overflow-visible"
      aria-hidden="true"
      focusable="false"
    >
      <path
        d="M6 3C6 18 14 26 24 28M42 3C42 18 34 26 24 28"
        fill="none"
        stroke={STETHO}
        strokeWidth="2.6"
        strokeLinecap="round"
      />
      <circle cx="24" cy="32.5" r="4.4" fill="#cbd5e1" stroke={STETHO} strokeWidth="2" />
      <circle cx="24" cy="32.5" r="1.5" fill="#64748b" />
    </svg>
  );
}

/** Bandeau et miroir frontal. */
function HeadMirror() {
  return (
    <div data-part="head-mirror" className="m-doc m-headgear absolute left-3 top-[9px] h-[37px] w-[68px]">
      <div className="absolute left-0 top-[7px] h-[30px] w-[68px] rounded-[24px_24px_0_0] border-t-[3px] border-[#8494ab]" />
      <div
        className="m-mirror-disc absolute left-3 top-0 h-[19px] w-[19px] rounded-full border-2 border-[#475569]"
        style={{
          background:
            'radial-gradient(circle at 35% 30%, #ffffff 0 16%, #dbe2ec 38%, #94a3b8 100%)',
        }}
      >
        <span className="absolute left-1/2 top-1/2 h-[4px] w-[4px] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[#334155]" />
      </div>
    </div>
  );
}

const SPARKS: { x: number; y: number; size: number; tone: 'danger' | 'primary'; delay: number }[] = [
  { x: -46, y: -28, size: 11, tone: 'danger', delay: 0.1 },
  { x: 46, y: -34, size: 10, tone: 'primary', delay: 0.14 },
  { x: -52, y: 12, size: 9, tone: 'primary', delay: 0.18 },
  { x: 52, y: 8, size: 12, tone: 'danger', delay: 0.12 },
  { x: -24, y: -58, size: 9, tone: 'primary', delay: 0.22 },
  { x: 28, y: -60, size: 11, tone: 'danger', delay: 0.16 },
  { x: -38, y: 42, size: 8, tone: 'danger', delay: 0.24 },
  { x: 40, y: 40, size: 9, tone: 'primary', delay: 0.2 },
];

const PUFFS: { x: number; y: number; size: number; delay: number }[] = [
  { x: -40, y: -10, size: 18, delay: 0.1 },
  { x: 42, y: -16, size: 16, delay: 0.14 },
  { x: -28, y: 30, size: 14, delay: 0.2 },
  { x: 32, y: 28, size: 15, delay: 0.18 },
  { x: 4, y: -46, size: 13, delay: 0.24 },
];

/** Gerbe de croix (vers docteur) ou nuage de fumée (vers chatbot). */
function Burst({ kind }: { kind: 'sparks' | 'puffs' }) {
  return (
    <div data-part={kind} className="m-burst pointer-events-none absolute left-1/2 top-[56%] h-0 w-0">
      {kind === 'sparks'
        ? SPARKS.map((s, i) => (
            <svg
              key={i}
              viewBox="0 0 10 10"
              className="m-spark"
              style={
                {
                  width: s.size,
                  height: s.size,
                  '--sx': `${s.x}px`,
                  '--sy': `${s.y}px`,
                  animationDelay: `${s.delay}s`,
                } as CSSProperties
              }
              aria-hidden="true"
              focusable="false"
            >
              <path
                d="M3.5 0h3v3.5H10v3H6.5V10h-3V6.5H0v-3h3.5z"
                className={s.tone === 'danger' ? 'fill-danger' : 'fill-primary'}
              />
            </svg>
          ))
        : PUFFS.map((p, i) => (
            <span
              key={i}
              className="m-puff rounded-full border border-primary-200 bg-primary-100"
              style={
                {
                  width: p.size,
                  height: p.size,
                  '--sx': `${p.x}px`,
                  '--sy': `${p.y}px`,
                  animationDelay: `${p.delay}s`,
                } as CSSProperties
              }
            />
          ))}
    </div>
  );
}

export function Mascot({ mode }: { mode: RobotMode }) {
  const [changing, setChanging] = useState<Change | null>(null);
  const previousMode = useRef(mode);

  // Effet de mise en page : la classe est posée avant que le navigateur peigne la
  // nouvelle tenue, sans image intermédiaire (ni blouse qui disparaît d'un coup).
  useLayoutEffect(() => {
    if (previousMode.current === mode) return;
    previousMode.current = mode;
    setChanging(mode === 'doctor' ? 'to-doctor' : 'to-chat');
  }, [mode]);

  useEffect(() => {
    if (!changing) return;
    const timer = setTimeout(() => setChanging(null), CHANGE_SAFETY_MS);
    return () => clearTimeout(timer);
  }, [changing]);

  function onAnimationEnd(e: AnimationEvent<HTMLDivElement>) {
    if (FINAL_ANIMATIONS.has(e.animationName)) setChanging(null);
  }

  // La blouse reste montée pendant qu'elle s'envole (retour au chatbot).
  const dressed = mode === 'doctor' || changing === 'to-chat';

  return (
    <div
      aria-hidden="true"
      data-mode={mode}
      onAnimationEnd={onAnimationEnd}
      className={cn(
        'm-robot relative h-[104px] w-[92px] drop-shadow-[0_10px_18px_rgba(31,44,84,.22)]',
        changing === 'to-doctor' && 'is-changing-to-doctor',
        changing === 'to-chat' && 'is-changing-to-chat'
      )}
    >
      <div className="m-costume absolute inset-0">
        {/* Antenne */}
        <div className="absolute -top-0.5 left-1/2 h-4 w-[3px] -translate-x-1/2 rounded-sm bg-primary" />
        <div className="absolute -top-[9px] left-1/2 h-[11px] w-[11px] -translate-x-1/2 rounded-full bg-primary" />

        {/* Bras qui salue (manche de blouse en mode docteur) */}
        <div className="m-arm absolute -left-[9px] top-11 h-[34px] w-[15px] origin-bottom rotate-[8deg] rounded-[9px] bg-primary">
          <div className="absolute -left-1 -top-3 h-[22px] w-[22px] rounded-[50%_50%_50%_40%] bg-primary" />
          {dressed && (
            <div
              data-part="sleeve"
              className="m-doc m-sleeve absolute -inset-x-px bottom-0 h-[22px] rounded-[3px_3px_9px_9px] border border-[#9aa9bf] bg-[#fbfcfe]"
            >
              <div className="absolute inset-x-0 top-[3px] h-px bg-[#c3cede]" />
            </div>
          )}
        </div>

        {/* Oreilles */}
        <div className="absolute left-0.5 top-10 h-[26px] w-[11px] rounded-md bg-primary" />
        <div className="absolute right-0.5 top-10 h-[26px] w-[11px] rounded-md bg-primary" />

        {/* Corps */}
        <div className="absolute bottom-0 left-1/2 h-[38px] w-14 -translate-x-1/2 rounded-[16px_16px_12px_12px] border-2 border-border bg-card">
          <div className="absolute left-1/2 top-[9px] h-4 w-[26px] -translate-x-1/2 rounded-md bg-primary-50" />
        </div>

        {dressed && <Coat />}
        {dressed && <Stethoscope />}

        {/* Tête */}
        <div className="absolute left-1/2 top-3.5 h-[60px] w-[74px] -translate-x-1/2 rounded-[26px_26px_22px_22px] border-2 border-border bg-card">
          <div className="absolute left-1/2 top-1/2 flex h-[38px] w-14 -translate-x-1/2 -translate-y-1/2 items-center justify-center gap-3 rounded-[20px] bg-[#2e3f73]">
            <div className="m-eye h-[11px] w-[11px] rounded-full bg-[#8fe3ee] shadow-[0_0_8px_rgba(143,227,238,.9)]" />
            <div className="m-eye h-[11px] w-[11px] rounded-full bg-[#8fe3ee] shadow-[0_0_8px_rgba(143,227,238,.9)] [animation-delay:.08s]" />
          </div>
        </div>

        {dressed && <HeadMirror />}
      </div>

      {changing === 'to-doctor' && <Burst kind="sparks" />}
      {changing === 'to-chat' && <Burst kind="puffs" />}
    </div>
  );
}
