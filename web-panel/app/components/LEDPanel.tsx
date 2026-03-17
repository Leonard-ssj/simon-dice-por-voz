"use client";

import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { ColorJuego } from "../../types/game";

interface Props {
  activo: ColorJuego | null;
  secuencia: ColorJuego[];
  dark: boolean;
}

const LED_CONFIG: Record<ColorJuego, { bg: string; glow: string; ring: string; label: string }> = {
  ROJO:     { bg: "bg-red-500",     glow: "shadow-red-500/60",     ring: "ring-red-400",     label: "Rojo" },
  VERDE:    { bg: "bg-emerald-500", glow: "shadow-emerald-500/60", ring: "ring-emerald-400", label: "Verde" },
  AZUL:     { bg: "bg-blue-500",    glow: "shadow-blue-500/60",    ring: "ring-blue-400",    label: "Azul" },
  AMARILLO: { bg: "bg-yellow-400",  glow: "shadow-yellow-400/60",  ring: "ring-yellow-300",  label: "Amarillo" },
};

const COLORES: ColorJuego[] = ["ROJO", "VERDE", "AZUL", "AMARILLO"];

export default function LEDPanel({ activo, secuencia, dark }: Props) {
  return (
    <div className="flex flex-col items-center gap-4">
      <div className="flex gap-6 justify-center">
        {COLORES.map((color) => {
          const config = LED_CONFIG[color];
          const encendido = activo === color;

          return (
            <div key={color} className="flex flex-col items-center gap-2">
              <motion.div
                animate={encendido ? { scale: 1.15 } : { scale: 1 }}
                transition={{ type: "spring", stiffness: 400, damping: 20 }}
                className="relative"
              >
                {/* Glow exterior */}
                <AnimatePresence>
                  {encendido && (
                    <motion.div
                      key="glow"
                      initial={{ opacity: 0, scale: 0.8 }}
                      animate={{ opacity: 1, scale: 1.4 }}
                      exit={{ opacity: 0, scale: 0.8 }}
                      transition={{ duration: 0.2 }}
                      className={cn(
                        "absolute inset-0 rounded-full blur-xl",
                        config.bg,
                        "opacity-60"
                      )}
                    />
                  )}
                </AnimatePresence>

                {/* LED */}
                <div
                  className={cn(
                    "relative w-16 h-16 rounded-full transition-all duration-200",
                    encendido
                      ? cn(config.bg, "shadow-2xl", config.glow, "ring-2", config.ring)
                      : dark ? "bg-white/5 ring-1 ring-white/10" : "bg-slate-200 ring-1 ring-slate-300"
                  )}
                >
                  {/* Brillo interno */}
                  {encendido && (
                    <div className="absolute top-2 left-2 w-4 h-4 bg-white/40 rounded-full blur-sm" />
                  )}
                </div>
              </motion.div>

              <span className={cn(
                "text-xs font-medium transition-colors duration-200",
                encendido ? "text-white" : dark ? "text-white/30" : "text-slate-400"
              )}>
                {config.label}
              </span>
            </div>
          );
        })}
      </div>

      {/* Indicador de cuántos colores van en la secuencia */}
      {secuencia.length > 0 && (
        <div className="flex gap-1 flex-wrap justify-center max-w-xs">
          {secuencia.map((color, i) => (
            <div
              key={i}
              className={cn(
                "w-2 h-2 rounded-full transition-all duration-300",
                LED_CONFIG[color].bg,
                "opacity-50"
              )}
            />
          ))}
        </div>
      )}
    </div>
  );
}
