"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Layers } from "lucide-react";

interface Props {
  nivel: number;
  puntuacion: number;
  dark: boolean;
}

function AnimatedNumber({ value }: { value: number }) {
  return (
    <AnimatePresence mode="wait">
      <motion.span
        key={value}
        initial={{ opacity: 0, y: -12 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: 12 }}
        transition={{ duration: 0.2 }}
        className="inline-block"
      >
        {value}
      </motion.span>
    </AnimatePresence>
  );
}

export default function ScoreBoard({ nivel, puntuacion, dark }: Props) {
  return (
    <div className="flex gap-4 h-full">
      {/* Nivel */}
      <div className={`flex-1 flex flex-col gap-1.5 p-5 rounded-2xl border ${dark ? "bg-white/3 border-white/5" : "bg-white border-slate-200"}`}>
        <div className={`flex items-center gap-1.5 ${dark ? "text-white/40" : "text-slate-400"}`}>
          <Layers size={13} />
          <span className="text-xs font-semibold uppercase tracking-widest">Nivel</span>
        </div>
        <div className={`text-4xl font-bold tabular-nums ${dark ? "text-white" : "text-slate-800"}`}>
          <AnimatedNumber value={nivel} />
        </div>
      </div>

      {/* Puntuación */}
      <div className={`flex-1 flex flex-col gap-1.5 p-5 rounded-2xl border ${dark ? "bg-yellow-500/5 border-yellow-500/10" : "bg-yellow-50 border-yellow-100"}`}>
        <div className={`flex items-center gap-1.5 ${dark ? "text-yellow-500/60" : "text-yellow-600"}`}>
          <Trophy size={13} />
          <span className="text-xs font-semibold uppercase tracking-widest">Puntos</span>
        </div>
        <div className="text-4xl font-bold text-yellow-400 tabular-nums">
          <AnimatedNumber value={puntuacion} />
        </div>
      </div>
    </div>
  );
}
