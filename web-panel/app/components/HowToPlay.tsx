"use client";

import { motion } from "framer-motion";
import { X, Mic, Eye, CheckCircle, XCircle, RotateCcw, Pause } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  onClose: () => void;
  dark: boolean;
}

const PASOS = [
  {
    icono: Mic,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    titulo: "1. Inicia el juego",
    desc: 'Di "EMPIEZA" por el micrófono. El juego comenzará una partida nueva.',
  },
  {
    icono: Eye,
    color: "text-blue-400",
    bg: "bg-blue-500/10",
    titulo: "2. Mira la secuencia",
    desc: "Los LEDs se encienden uno por uno mostrando una secuencia de colores. Memorízala.",
  },
  {
    icono: Mic,
    color: "text-yellow-400",
    bg: "bg-yellow-500/10",
    titulo: "3. Repite la secuencia",
    desc: 'Di los colores en el mismo orden: "ROJO", "VERDE", "AZUL", "AMARILLO". Espera el beep entre cada uno.',
  },
  {
    icono: CheckCircle,
    color: "text-emerald-400",
    bg: "bg-emerald-500/10",
    titulo: "4. Sube de nivel",
    desc: "Si aciertas toda la secuencia, el juego agrega un color más y repite. Cada nivel suma puntos.",
  },
  {
    icono: XCircle,
    color: "text-red-400",
    bg: "bg-red-500/10",
    titulo: "5. No cometas errores",
    desc: "Un color incorrecto o no hablar a tiempo termina el juego. El panel muestra tu puntuación final.",
  },
];

const TRUCOS = [
  { cmd: "REPITE", desc: 'Di "REPITE" si no recordás la secuencia — se vuelve a mostrar.' },
  { cmd: "PAUSA",  desc: 'Di "PAUSA" para frenar el juego temporalmente.' },
  { cmd: "PARA",   desc: 'Di "PARA" para terminar la partida en cualquier momento.' },
  { cmd: "VOZ",    desc: "Hablá claro y a volumen normal. Whisper procesa en ~2 segundos." },
];

export default function HowToPlay({ onClose, dark }: Props) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
      onClick={onClose}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95, y: 10 }}
        animate={{ opacity: 1, scale: 1, y: 0 }}
        exit={{ opacity: 0, scale: 0.95, y: 10 }}
        transition={{ type: "spring", stiffness: 300, damping: 25 }}
        onClick={(e) => e.stopPropagation()}
        className={cn(
          "w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-3xl border shadow-2xl",
          dark
            ? "bg-[#0e0e14] border-white/10"
            : "bg-white border-slate-200"
        )}
      >
        {/* Header */}
        <div className={cn(
          "flex items-center justify-between p-6 border-b sticky top-0 z-10",
          dark ? "border-white/5 bg-[#0e0e14]" : "border-slate-100 bg-white"
        )}>
          <div>
            <h2 className="text-lg font-bold">¿Cómo se juega?</h2>
            <p className={cn("text-xs mt-0.5", dark ? "text-white/40" : "text-slate-400")}>
              Simon Dice por Voz — Guía rápida
            </p>
          </div>
          <button
            onClick={onClose}
            className={cn(
              "p-2 rounded-xl transition-colors",
              dark ? "hover:bg-white/8 text-white/40" : "hover:bg-slate-100 text-slate-400"
            )}
          >
            <X size={18} />
          </button>
        </div>

        <div className="p-6 flex flex-col gap-6">
          {/* Qué es */}
          <div className={cn(
            "rounded-2xl p-4 border",
            dark ? "bg-indigo-500/5 border-indigo-500/15" : "bg-indigo-50 border-indigo-100"
          )}>
            <p className={cn("text-sm", dark ? "text-white/70" : "text-slate-600")}>
              <strong className={dark ? "text-indigo-300" : "text-indigo-600"}>Simon Dice por Voz</strong> es
              el clásico juego de memoria Simon Says controlado completamente con tu voz.
              El sistema muestra una secuencia de colores y debes repetirla en orden, hablando al micrófono.
              Con cada nivel, la secuencia crece en un color más.
            </p>
          </div>

          {/* Pasos */}
          <div>
            <h3 className={cn("text-xs font-semibold uppercase tracking-widest mb-3", dark ? "text-white/30" : "text-slate-400")}>
              Cómo jugar paso a paso
            </h3>
            <div className="flex flex-col gap-2">
              {PASOS.map(({ icono: Icon, color, bg, titulo, desc }) => (
                <div key={titulo} className={cn(
                  "flex gap-3 p-3 rounded-xl",
                  dark ? "bg-white/3" : "bg-slate-50"
                )}>
                  <div className={cn("w-8 h-8 rounded-lg flex items-center justify-center shrink-0 mt-0.5", bg)}>
                    <Icon size={15} className={color} />
                  </div>
                  <div>
                    <p className={cn("text-sm font-semibold", dark ? "text-white/80" : "text-slate-700")}>{titulo}</p>
                    <p className={cn("text-xs mt-0.5", dark ? "text-white/45" : "text-slate-500")}>{desc}</p>
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Puntuación */}
          <div>
            <h3 className={cn("text-xs font-semibold uppercase tracking-widest mb-3", dark ? "text-white/30" : "text-slate-400")}>
              Puntuación
            </h3>
            <div className={cn("rounded-xl p-4 border font-mono text-sm", dark ? "bg-white/3 border-white/5" : "bg-slate-50 border-slate-200")}>
              <p className={dark ? "text-white/60" : "text-slate-600"}>
                Puntos por secuencia completada = <span className="text-yellow-400 font-bold">nivel × 10</span>
              </p>
              <p className={cn("text-xs mt-1", dark ? "text-white/30" : "text-slate-400")}>
                Nivel 1 → 10 pts · Nivel 5 → 50 pts · Nivel 10 → 100 pts
              </p>
            </div>
          </div>

          {/* Trucos */}
          <div>
            <h3 className={cn("text-xs font-semibold uppercase tracking-widest mb-3", dark ? "text-white/30" : "text-slate-400")}>
              Comandos útiles
            </h3>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {TRUCOS.map(({ cmd, desc }) => (
                <div key={cmd} className={cn(
                  "flex gap-2 p-3 rounded-xl border",
                  dark ? "bg-white/3 border-white/5" : "bg-slate-50 border-slate-200"
                )}>
                  <span className={cn(
                    "text-xs font-mono font-bold px-1.5 py-0.5 rounded-md self-start",
                    dark ? "bg-indigo-500/20 text-indigo-300" : "bg-indigo-100 text-indigo-600"
                  )}>{cmd}</span>
                  <span className={cn("text-xs", dark ? "text-white/45" : "text-slate-500")}>{desc}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Nota técnica */}
          <div className={cn(
            "rounded-xl p-3 border text-xs",
            dark ? "bg-yellow-500/5 border-yellow-500/15 text-yellow-400/70" : "bg-yellow-50 border-yellow-200 text-yellow-700"
          )}>
            <strong>Nota técnica:</strong> El reconocimiento de voz usa Whisper (IA de OpenAI) corriendo
            localmente. Hay ~2 segundos de latencia por procesamiento. Hablá cuando el estado diga
            "Tu turno — habla" y espera el resultado antes del siguiente color.
          </div>
        </div>
      </motion.div>
    </motion.div>
  );
}
