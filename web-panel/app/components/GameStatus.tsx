"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Mic, Eye, CheckCircle, XCircle, Clock, Pause, Trophy, Volume2 } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EstadoJuego } from "../../types/game";

interface Props {
  estado: EstadoJuego;
  ultimaDeteccion: string | null;
  ultimoTextoWhisper: string | null;
  ultimoResultado: string | null;
  dark: boolean;
}

const ESTADO_CONFIG: Record<EstadoJuego, {
  label: string;
  colorDark: string;
  colorLight: string;
  bg: string;
  bgLight: string;
  Icon: React.ElementType;
  pulso: boolean;
}> = {
  IDLE:       { label: "Esperando",           colorDark: "text-white/40",    colorLight: "text-slate-400",   bg: "bg-white/5",        bgLight: "bg-slate-100",    Icon: Clock,       pulso: false },
  SHOWING:    { label: "Mira la secuencia",   colorDark: "text-blue-400",    colorLight: "text-blue-600",    bg: "bg-blue-500/10",    bgLight: "bg-blue-50",      Icon: Eye,         pulso: false },
  LISTENING:  { label: "Tu turno — habla",    colorDark: "text-emerald-400", colorLight: "text-emerald-600", bg: "bg-emerald-500/10", bgLight: "bg-emerald-50",   Icon: Mic,         pulso: true  },
  EVALUATING: { label: "Procesando...",       colorDark: "text-yellow-400",  colorLight: "text-yellow-600",  bg: "bg-yellow-500/10",  bgLight: "bg-yellow-50",    Icon: Clock,       pulso: true  },
  CORRECT:    { label: "¡Correcto!",          colorDark: "text-emerald-400", colorLight: "text-emerald-600", bg: "bg-emerald-500/10", bgLight: "bg-emerald-50",   Icon: CheckCircle, pulso: false },
  LEVEL_UP:   { label: "¡Nivel superado!",   colorDark: "text-purple-400",  colorLight: "text-purple-600",  bg: "bg-purple-500/10",  bgLight: "bg-purple-50",    Icon: Trophy,      pulso: false },
  WRONG:      { label: "Incorrecto",          colorDark: "text-red-400",     colorLight: "text-red-600",     bg: "bg-red-500/10",     bgLight: "bg-red-50",       Icon: XCircle,     pulso: false },
  GAMEOVER:   { label: "Fin del juego",       colorDark: "text-red-500",     colorLight: "text-red-600",     bg: "bg-red-500/10",     bgLight: "bg-red-50",       Icon: XCircle,     pulso: false },
  PAUSA:      { label: "Pausa",               colorDark: "text-orange-400",  colorLight: "text-orange-600",  bg: "bg-orange-500/10",  bgLight: "bg-orange-50",    Icon: Pause,       pulso: false },
};

// Colores reconocidos — para mostrar el badge en color
const COLOR_BADGE: Record<string, string> = {
  ROJO:     "bg-red-500 text-white",
  VERDE:    "bg-emerald-500 text-white",
  AZUL:     "bg-blue-500 text-white",
  AMARILLO: "bg-yellow-400 text-yellow-900",
};

export default function GameStatus({ estado, ultimaDeteccion, ultimoTextoWhisper, ultimoResultado, dark, grabando = false }: Props & { grabando?: boolean }) {
  const config = ESTADO_CONFIG[estado] ?? ESTADO_CONFIG.IDLE;
  const { Icon } = config;
  const colorClass = dark ? config.colorDark : config.colorLight;
  const bgClass    = dark ? config.bg        : config.bgLight;
  const colorBadge = ultimaDeteccion ? COLOR_BADGE[ultimaDeteccion.toUpperCase()] : null;

  return (
    <div className="flex flex-col gap-2">
      {/* Estado principal */}
      <AnimatePresence mode="wait">
        <motion.div
          key={estado}
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: 8 }}
          transition={{ duration: 0.2 }}
          className={cn(
            "flex items-center gap-3 px-4 py-3 rounded-xl border",
            dark ? "border-white/5" : "border-slate-200",
            bgClass
          )}
        >
          <div className={cn(
            "relative shrink-0",
            config.pulso && "after:absolute after:inset-0 after:rounded-full after:animate-ping after:opacity-30",
            colorClass
          )}>
            <Icon size={20} />
          </div>
          <span className={cn("font-semibold text-base", colorClass)}>
            {config.label}
          </span>
        </motion.div>
      </AnimatePresence>

      {/* Hint PTT — solo cuando es turno del jugador y no está grabando */}
      <AnimatePresence>
        {estado === "LISTENING" && !grabando && (
          <motion.p
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.3 }}
            className={cn("text-xs text-center", dark ? "text-white/40" : "text-slate-400")}
          >
            Presiona{" "}
            <kbd className={cn(
              "inline-block px-1.5 py-0.5 rounded text-[10px] font-mono border",
              dark ? "border-white/20 bg-white/8 text-white/60" : "border-slate-300 bg-slate-100 text-slate-600"
            )}>ESPACIO</kbd>
            {" "}o el botón 🎤 para hablar
          </motion.p>
        )}
      </AnimatePresence>

      {/* Última detección — prominente */}
      <AnimatePresence>
        {ultimaDeteccion && (
          <motion.div
            key={ultimaDeteccion}
            initial={{ opacity: 0, scale: 0.95 }}
            animate={{ opacity: 1, scale: 1 }}
            className={cn(
              "flex flex-col gap-1.5 px-4 py-3 rounded-xl border",
              dark ? "bg-white/3 border-white/5" : "bg-slate-50 border-slate-200"
            )}
          >
            {/* Texto escuchado por Whisper */}
            {ultimoTextoWhisper && ultimoTextoWhisper !== ultimaDeteccion.toLowerCase() && (
              <div className="flex items-center gap-1.5">
                <Volume2 size={11} className={dark ? "text-white/25 shrink-0" : "text-slate-300 shrink-0"} />
                <span className={cn("text-xs italic truncate", dark ? "text-white/30" : "text-slate-400")}>
                  "{ultimoTextoWhisper}"
                </span>
              </div>
            )}

            {/* Comando detectado — grande y en color */}
            <div className="flex items-center gap-2">
              <Mic size={12} className={dark ? "text-white/30 shrink-0" : "text-slate-400 shrink-0"} />
              <span className={cn("text-xs", dark ? "text-white/40" : "text-slate-500")}>Detectado</span>
              <div className="ml-auto">
                {colorBadge ? (
                  <span className={cn("px-3 py-0.5 rounded-full text-sm font-bold", colorBadge)}>
                    {ultimaDeteccion.charAt(0) + ultimaDeteccion.slice(1).toLowerCase()}
                  </span>
                ) : (
                  <span className={cn("text-sm font-mono font-bold", dark ? "text-white/80" : "text-slate-700")}>
                    {ultimaDeteccion}
                  </span>
                )}
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
