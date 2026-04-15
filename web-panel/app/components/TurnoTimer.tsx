"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { cn } from "@/lib/utils";
import type { EstadoJuego, ColorJuego } from "../../types/game";

interface Props {
  estado: EstadoJuego;
  esperado: ColorJuego | null;
  dark: boolean;
  timeoutMs?: number;          // total de tiempo del turno en ms (default 60000)
  startDelayMs?: number;       // esperar N ms antes de iniciar el countdown interno
  tiempoRestanteMs?: number | null; // override del servidor (sincronizado) — si se pasa, ignora el countdown interno
}

const COLOR_DOT: Record<ColorJuego, string> = {
  ROJO:     "bg-red-500",
  VERDE:    "bg-emerald-500",
  AZUL:     "bg-blue-500",
  AMARILLO: "bg-yellow-400",
};

const COMANDOS = [
  { cmd: "empieza",   aliases: "inicia / comienza",   tipo: "inicio"   },
  { cmd: "rojo",      aliases: "roja / roxo",          tipo: "color"    },
  { cmd: "verde",     aliases: "berde / verd",          tipo: "color"    },
  { cmd: "azul",      aliases: "asul / azur",           tipo: "color"    },
  { cmd: "amarillo",  aliases: "amarilla / amarijo",    tipo: "color"    },
  { cmd: "repite",    aliases: "de nuevo / otra vez",   tipo: "accion"   },
  { cmd: "pausa",     aliases: "pausar / espera",       tipo: "accion"   },
  { cmd: "para",      aliases: "stop / termina",        tipo: "accion"   },
];

const TIPO_COLOR = {
  inicio: "text-indigo-400",
  color:  "text-white/60",
  accion: "text-yellow-400/80",
};

export default function TurnoTimer({ estado, esperado, dark, timeoutMs = 60000, startDelayMs = 0, tiempoRestanteMs }: Props) {
  const [segundos, setSegundos]   = useState(timeoutMs / 1000);
  const [activo,   setActivo]     = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const delayRef    = useRef<ReturnType<typeof setTimeout>  | null>(null);
  const totalSeg    = timeoutMs / 1000;

  // Si el servidor pasa tiempoRestanteMs, sincronizar con ese valor
  // en lugar de usar el countdown interno.
  const usarOverride = tiempoRestanteMs !== null && tiempoRestanteMs !== undefined;
  const segundosEfectivos = usarOverride ? (tiempoRestanteMs! / 1000) : segundos;
  const activoEfectivo    = usarOverride ? (tiempoRestanteMs! > 0 && estado === "LISTENING") : activo;

  useEffect(() => {
    // Limpiar siempre al salir de LISTENING o al desmontar
    if (estado !== "LISTENING") {
      if (delayRef.current)    clearTimeout(delayRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
      setActivo(false);
      setSegundos(totalSeg);
      return;
    }

    // Entró en LISTENING — esperar startDelayMs (TTS "Tu turno...") antes de arrancar
    setActivo(false);
    setSegundos(totalSeg);
    delayRef.current = setTimeout(() => {
      setActivo(true);
      intervalRef.current = setInterval(() => {
        setSegundos((s) => {
          if (s <= 0.2) {
            if (intervalRef.current) clearInterval(intervalRef.current);
            return 0;
          }
          return s - 0.2;
        });
      }, 200);
    }, startDelayMs);

    return () => {
      if (delayRef.current)    clearTimeout(delayRef.current);
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [estado, totalSeg, startDelayMs]);

  const pct  = (segundosEfectivos / totalSeg) * 100;
  const sInt = Math.ceil(segundosEfectivos);
  const urgente  = segundosEfectivos <= 10;
  const critico  = segundosEfectivos <= 5;

  // ── Modo LISTENING: mostrar temporizador ──
  if (estado === "LISTENING") {
    return (
      <div className={cn(
        "rounded-2xl border p-4 flex flex-col gap-3",
        dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
      )}>
        <div className="flex items-center justify-between">
          <p className={cn("text-[10px] font-semibold uppercase tracking-widest", dark ? "text-white/25" : "text-slate-400")}>
            {activoEfectivo ? "Tiempo restante" : "Preparando..."}
          </p>
          {esperado && (
            <div className="flex items-center gap-1.5">
              <span className={cn("text-[10px]", dark ? "text-white/30" : "text-slate-400")}>Di:</span>
              <div className={cn("w-2.5 h-2.5 rounded-full", COLOR_DOT[esperado])} />
              <span className={cn("text-xs font-bold", dark ? "text-white/70" : "text-slate-700")}>
                {esperado.charAt(0) + esperado.slice(1).toLowerCase()}
              </span>
            </div>
          )}
        </div>

        {/* Número grande */}
        <AnimatePresence mode="wait">
          <motion.div
            key={activoEfectivo ? sInt : "wait"}
            initial={{ opacity: 0.6, scale: 0.85 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.15 }}
            className={cn(
              "text-5xl font-bold tabular-nums text-center leading-none",
              !activoEfectivo ? (dark ? "text-white/20" : "text-slate-300") :
              critico         ? "text-red-400"    :
              urgente         ? "text-yellow-400" :
                                (dark ? "text-white" : "text-slate-800")
            )}
          >
            {activoEfectivo ? sInt : "—"}
            {activoEfectivo && <span className={cn("text-base ml-1", dark ? "text-white/30" : "text-slate-400")}>s</span>}
          </motion.div>
        </AnimatePresence>

        {/* Barra de progreso */}
        <div className={cn("h-2 rounded-full overflow-hidden", dark ? "bg-white/8" : "bg-slate-200")}>
          <motion.div
            className={cn(
              "h-full rounded-full transition-colors duration-500",
              !activoEfectivo ? (dark ? "bg-white/10" : "bg-slate-300") :
              critico         ? "bg-red-500"    :
              urgente         ? "bg-yellow-400" :
                                "bg-emerald-400"
            )}
            style={{ width: activoEfectivo ? `${pct}%` : "100%" }}
            transition={{ duration: 0.2, ease: "linear" }}
          />
        </div>

        {activoEfectivo && critico && (
          <p className="text-center text-xs text-red-400 animate-pulse font-semibold">
            ¡Habla ahora!
          </p>
        )}
        {!activoEfectivo && (
          <p className={cn("text-center text-xs", dark ? "text-white/25" : "text-slate-400")}>
            Escucha las instrucciones...
          </p>
        )}
      </div>
    );
  }

  // ── Otros estados: referencia de comandos ──
  return (
    <div className={cn(
      "rounded-2xl border p-4 flex flex-col gap-2",
      dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
    )}>
      <p className={cn("text-[10px] font-semibold uppercase tracking-widest mb-1", dark ? "text-white/25" : "text-slate-400")}>
        Comandos de voz
      </p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-0.5">
        {COMANDOS.map(({ cmd, aliases, tipo }) => (
          <div key={cmd} className="flex items-baseline gap-1.5">
            <span className={cn("text-xs font-bold shrink-0", TIPO_COLOR[tipo as keyof typeof TIPO_COLOR])}>
              {cmd}
            </span>
            <span className={cn("text-[10px] truncate", dark ? "text-white/20" : "text-slate-400")}>
              {aliases}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
