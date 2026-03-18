"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ColorJuego } from "../../types/game";

interface Props {
  secuencia: ColorJuego[];
  esperado: ColorJuego | null;
}

const COLOR_STYLES: Record<ColorJuego, { bg: string; border: string; text: string }> = {
  ROJO:     { bg: "bg-red-500/80",     border: "border-red-400/50",     text: "text-red-100" },
  VERDE:    { bg: "bg-emerald-500/80", border: "border-emerald-400/50", text: "text-emerald-100" },
  AZUL:     { bg: "bg-blue-500/80",    border: "border-blue-400/50",    text: "text-blue-100" },
  AMARILLO: { bg: "bg-yellow-400/80",  border: "border-yellow-300/50",  text: "text-yellow-900" },
};

const ESPERADO_RING: Record<ColorJuego, string> = {
  ROJO:     "ring-red-400",
  VERDE:    "ring-emerald-400",
  AZUL:     "ring-blue-400",
  AMARILLO: "ring-yellow-300",
};

export default function SequenceDisplay({ secuencia, esperado }: Props) {
  if (secuencia.length === 0) {
    return (
      <div className="flex items-center justify-center h-10 text-white/20 text-xs">
        La secuencia aparecerá aquí al iniciar
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-2">
      <div className="flex flex-wrap gap-1.5">
        <AnimatePresence>
          {secuencia.map((color, i) => {
            const s = COLOR_STYLES[color];
            return (
              <motion.div
                key={i}
                initial={{ opacity: 0, scale: 0.7 }}
                animate={{ opacity: 1, scale: 1 }}
                transition={{ delay: i * 0.03, type: "spring", stiffness: 300 }}
                className={cn(
                  "w-6 h-6 rounded-md border flex items-center justify-center",
                  "text-[9px] font-bold",
                  s.bg, s.border, s.text
                )}
              >
                {i + 1}
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {esperado && (
        <motion.div
          key={esperado}
          initial={{ opacity: 0, scale: 0.9 }}
          animate={{ opacity: 1, scale: 1 }}
          className={cn(
            "inline-flex items-center gap-2 self-start px-3 py-1.5 rounded-full",
            "bg-white/5 border border-white/10 ring-2",
            ESPERADO_RING[esperado]
          )}
        >
          <div className={cn("w-3 h-3 rounded-full", COLOR_STYLES[esperado].bg)} />
          <span className="text-xs font-semibold text-white/80">
            Di: <span className="text-white">{esperado.charAt(0) + esperado.slice(1).toLowerCase()}</span>
          </span>
        </motion.div>
      )}
    </div>
  );
}
