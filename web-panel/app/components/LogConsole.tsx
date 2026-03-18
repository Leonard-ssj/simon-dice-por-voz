"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Copy, Trash2, ChevronDown } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EntradaLog } from "../../types/game";

interface Props {
  log: EntradaLog[];
  dark: boolean;
  onClear?: () => void;
}

type Filtro = "todos" | EntradaLog["tipo"];

const FILTROS: { key: Filtro; label: string }[] = [
  { key: "todos",    label: "Todo"   },
  { key: "sistema",  label: "Sistema" },
  { key: "voz",      label: "Voz"    },
  { key: "correcto", label: "OK"     },
  { key: "error",    label: "Error"  },
];

function getTipoStyles(dark: boolean): Record<EntradaLog["tipo"], { dot: string; text: string; prefix: string; badge: string }> {
  return {
    info:     { dot: dark ? "bg-white/20"  : "bg-slate-300",   text: dark ? "text-white/50"    : "text-slate-500",  prefix: " ",  badge: dark ? "bg-white/5 text-white/30"       : "bg-slate-100 text-slate-400"   },
    correcto: { dot: "bg-emerald-400",                          text: "text-emerald-400",                            prefix: "+",  badge: "bg-emerald-500/15 text-emerald-400"                                       },
    error:    { dot: "bg-red-400",                              text: "text-red-400",                                prefix: "!",  badge: "bg-red-500/15 text-red-400"                                               },
    voz:      { dot: "bg-blue-400",                             text: dark ? "text-blue-300"    : "text-blue-600",   prefix: "~",  badge: "bg-blue-500/15 text-blue-400"                                             },
    sistema:  { dot: "bg-yellow-400",                           text: dark ? "text-yellow-300"  : "text-yellow-600", prefix: "#",  badge: "bg-yellow-500/15 text-yellow-500"                                         },
  };
}

function formatHora(ts: number) {
  return new Date(ts).toLocaleTimeString("es", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export default function LogConsole({ log, dark, onClear }: Props) {
  const bottomRef  = useRef<HTMLDivElement>(null);
  const listRef    = useRef<HTMLDivElement>(null);
  const [filtro, setFiltro]       = useState<Filtro>("todos");
  const [autoScroll, setAutoScroll] = useState(true);
  const tipoStyles = getTipoStyles(dark);

  const logFiltrado = filtro === "todos" ? log : log.filter((e) => e.tipo === filtro);

  // Auto-scroll al nuevo mensaje — scrollTop directo para que sea inmediato
  useEffect(() => {
    if (autoScroll && listRef.current) {
      listRef.current.scrollTop = listRef.current.scrollHeight;
    }
  }, [log.length, autoScroll]);

  // Detectar si el usuario scrolleó hacia arriba (pausar auto-scroll)
  function handleScroll() {
    const el = listRef.current;
    if (!el) return;
    const distanciaAlFondo = el.scrollHeight - el.scrollTop - el.clientHeight;
    setAutoScroll(distanciaAlFondo < 40);
  }

  function copiarLog() {
    const texto = logFiltrado
      .slice()
      .reverse()
      .map((e) => `[${formatHora(e.ts)}] [${e.tipo.toUpperCase()}] ${e.mensaje}`)
      .join("\n");
    navigator.clipboard.writeText(texto).catch(() => {});
  }

  return (
    <div className={cn(
      "flex flex-col h-full min-h-0 rounded-2xl border overflow-hidden",
      dark ? "border-white/5 bg-black/30" : "border-slate-200 bg-white"
    )}>
      {/* Barra título */}
      <div className={cn(
        "flex items-center gap-2 px-4 py-2.5 border-b shrink-0",
        dark ? "border-white/5 bg-white/2" : "border-slate-100 bg-slate-50"
      )}>
        <div className="flex gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500/40" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500/40" />
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500/40" />
        </div>
        <span className={cn("text-xs font-mono ml-1 mr-auto", dark ? "text-white/30" : "text-slate-400")}>
          log en tiempo real
        </span>

        {/* Contador */}
        <span className={cn("text-xs tabular-nums", dark ? "text-white/20" : "text-slate-300")}>
          {logFiltrado.length} eventos
        </span>

        {/* Copiar */}
        <button
          onClick={copiarLog}
          title="Copiar log"
          className={cn(
            "p-1 rounded-md transition-colors",
            dark ? "hover:bg-white/8 text-white/25 hover:text-white/60" : "hover:bg-slate-200 text-slate-300 hover:text-slate-600"
          )}
        >
          <Copy size={13} />
        </button>

        {/* Limpiar */}
        {onClear && (
          <button
            onClick={onClear}
            title="Limpiar log"
            className={cn(
              "p-1 rounded-md transition-colors",
              dark ? "hover:bg-red-500/10 text-white/25 hover:text-red-400" : "hover:bg-red-50 text-slate-300 hover:text-red-500"
            )}
          >
            <Trash2 size={13} />
          </button>
        )}
      </div>

      {/* Filtros */}
      <div className={cn(
        "flex gap-1 px-3 py-2 border-b overflow-x-auto shrink-0",
        dark ? "border-white/5" : "border-slate-100"
      )}>
        {FILTROS.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => setFiltro(key)}
            className={cn(
              "px-2.5 py-1 rounded-lg text-xs font-semibold whitespace-nowrap transition-all duration-150",
              filtro === key
                ? dark
                  ? "bg-indigo-600/80 text-white"
                  : "bg-indigo-600 text-white"
                : dark
                  ? "text-white/30 hover:text-white/60 hover:bg-white/5"
                  : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
            )}
          >
            {label}
            {key !== "todos" && (
              <span className="ml-1 opacity-60">
                {log.filter((e) => e.tipo === key).length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Lista de entradas */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-3 font-mono text-xs space-y-0.5 min-h-0"
      >
        {logFiltrado.length === 0 && (
          <p className={cn("italic", dark ? "text-white/20" : "text-slate-300")}>
            _ sin eventos{filtro !== "todos" ? ` de tipo '${filtro}'` : " aún"}
          </p>
        )}
        <AnimatePresence initial={false}>
          {[...logFiltrado].reverse().map((e) => {
            const s = tipoStyles[e.tipo];
            return (
              <motion.div
                key={e.id}
                initial={{ opacity: 0, x: -8 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.12 }}
                className={cn(
                  "flex items-start gap-2 px-2 py-1 rounded-md transition-colors",
                  dark ? "hover:bg-white/3" : "hover:bg-slate-50"
                )}
              >
                <span className={cn("shrink-0 tabular-nums", dark ? "text-white/20" : "text-slate-300")}>{formatHora(e.ts)}</span>
                <span className={cn("shrink-0 font-bold", s.text)}>[{s.prefix}]</span>
                <span className={cn("flex-1 leading-relaxed", s.text)}>{e.mensaje}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
        <div ref={bottomRef} />
      </div>

      {/* Indicador de auto-scroll pausado */}
      <AnimatePresence>
        {!autoScroll && (
          <motion.button
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            onClick={() => {
              setAutoScroll(true);
              bottomRef.current?.scrollIntoView({ behavior: "smooth" });
            }}
            className={cn(
              "flex items-center justify-center gap-1.5 w-full py-1.5 text-xs border-t transition-colors",
              dark
                ? "border-white/5 bg-indigo-600/20 text-indigo-300 hover:bg-indigo-600/30"
                : "border-slate-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
            )}
          >
            <ChevronDown size={12} /> Ir al final
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
