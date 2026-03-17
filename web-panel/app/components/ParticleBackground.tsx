"use client";

import { useMemo } from "react";

interface Props {
  dark: boolean;
}

// Genera partículas con posiciones y tiempos aleatorios pero deterministas (SSR-safe via seed).
function seededRand(seed: number) {
  let s = seed;
  return () => {
    s = (s * 1664525 + 1013904223) & 0xffffffff;
    return (s >>> 0) / 0xffffffff;
  };
}

export default function ParticleBackground({ dark }: Props) {
  const particulas = useMemo(() => {
    const rand = seededRand(42);
    return Array.from({ length: 28 }, (_, i) => ({
      id: i,
      left:     Math.round(rand() * 100),           // % horizontal
      size:     1 + Math.round(rand() * 3),          // 1-4px
      delay:    Math.round(rand() * 18),             // segundos
      duration: 14 + Math.round(rand() * 20),        // 14-34 segundos
      dx:       Math.round((rand() - 0.5) * 80),     // deriva horizontal px
      opacity:  0.15 + rand() * 0.25,                // 0.15-0.4
    }));
  }, []);

  return (
    <div
      aria-hidden
      className="fixed inset-0 overflow-hidden pointer-events-none z-0"
    >
      {particulas.map((p) => (
        <span
          key={p.id}
          className="absolute bottom-0 rounded-full"
          style={{
            left:       `${p.left}%`,
            width:      p.size,
            height:     p.size,
            opacity:    0,
            background: dark
              ? `rgba(${p.size > 2 ? "129,140,248" : "255,255,255"}, ${p.opacity})`
              : `rgba(${p.size > 2 ? "99,102,241"  : "148,163,184"}, ${p.opacity + 0.1})`,
            animation:  `float-up ${p.duration}s ${p.delay}s ease-in infinite`,
            ["--dx" as string]: `${p.dx}px`,
          }}
        />
      ))}
    </div>
  );
}
