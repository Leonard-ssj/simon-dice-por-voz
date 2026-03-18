"use client";

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Copy, Trash2, ChevronDown, Terminal } from "lucide-react";
import { cn } from "@/lib/utils";
import type { EntradaLog } from "../../types/game";

interface Props {
  log: EntradaLog[];
  dark: boolean;
  onClear?: () => void;
}

type Filtro = "todos" | EntradaLog["tipo"];

const FILTROS: { key: Filtro; label: string; color: string }[] = [
  { key: "todos",    label: "Todo",    color: "" },
  { key: "sistema",  label: "Sistema", color: "text-yellow-400" },
  { key: "voz",      label: "Voz",     color: "text-blue-400" },
  { key: "correcto", label: "OK",      color: "text-emerald-400" },
  { key: "error",    label: "Error",   color: "text-red-400" },
];

const TIPO_CONFIG: Record<EntradaLog["tipo"], {
  dot: string; text: string; prefix: string; rowBg: string; badgeBg: string;
}> = {
  info:     { dot: "bg-white/15",    text: "text-white/40",    prefix: "·", rowBg: "",                          badgeBg: "bg-white/5 text-white/30"         },
  correcto: { dot: "bg-emerald-400", text: "text-emerald-300", prefix: "✓", rowBg: "bg-emerald-500/5",          badgeBg: "bg-emerald-500/20 text-emerald-300" },
  error:    { dot: "bg-red-400",     text: "text-red-300",     prefix: "✗", rowBg: "bg-red-500/5",              badgeBg: "bg-red-500/20 text-red-300"         },
  voz:      { dot: "bg-blue-400",    text: "text-blue-300",    prefix: "◎", rowBg: "bg-blue-500/5",             badgeBg: "bg-blue-500/20 text-blue-300"       },
  sistema:  { dot: "bg-yellow-400",  text: "text-yellow-300",  prefix: "#", rowBg: "bg-yellow-500/5",           badgeBg: "bg-yellow-500/20 text-yellow-300"   },
};

function formatHora(ts: number) {
  return new Date(ts).toLocaleTimeString("es", {
    hour: "2-digit", minute: "2-digit", second: "2-digit",
  });
}

export default function LogConsole({ log, dark, onClear }: Props) {
  const listRef    = useRef<HTMLDivElement>(null);
  const [filtro, setFiltro]         = useState<Filtro>("todos");
  const [autoScroll, setAutoScroll] = useState(true);

  const logFiltrado = filtro === "todos" ? log : log.filter((e) => e.tipo === filtro);

  // Newest at top — forzar scroll al inicio cuando llega mensaje nuevo.
  // overflow-anchor:none en el contenedor evita que el browser reajuste
  // automáticamente el scroll al insertar elementos arriba.
  useEffect(() => {
    if (autoScroll && listRef.current) {
      listRef.current.scrollTop = 0;
    }
  }, [log.length, autoScroll]);

  // Si el usuario bajó a revisar historial (top=recientes, bottom=antiguos)
  function handleScroll() {
    const el = listRef.current;
    if (!el) return;
    setAutoScroll(el.scrollTop < 40);
  }

  function copiarLog() {
    const texto = logFiltrado
      .map((e) => `[${formatHora(e.ts)}] [${e.tipo.toUpperCase()}] ${e.mensaje}`)
      .join("\n");
    navigator.clipboard.writeText(texto).catch(() => {});
  }

  return (
    <div className={cn(
      "flex flex-col h-full min-h-0 rounded-2xl overflow-hidden border",
      dark
        ? "border-indigo-500/20 bg-[#080810] shadow-lg shadow-indigo-500/5"
        : "border-slate-200 bg-white"
    )}>
      {/* Header */}
      <div className={cn(
        "flex items-center gap-2 px-4 py-2.5 border-b shrink-0",
        dark
          ? "border-indigo-500/15 bg-indigo-950/40"
          : "border-slate-100 bg-slate-50"
      )}>
        {/* Icono + título */}
        <Terminal size={13} className={dark ? "text-indigo-400" : "text-indigo-500"} />
        <span className={cn("text-xs font-mono font-semibold mr-auto", dark ? "text-indigo-300" : "text-indigo-600")}>
          log en tiempo real
        </span>

        {/* Contador */}
        <span className={cn("text-xs tabular-nums font-mono", dark ? "text-white/20" : "text-slate-300")}>
          {logFiltrado.length}
        </span>

        {/* Copiar */}
        <button
          onClick={copiarLog}
          title="Copiar log"
          className={cn(
            "p-1 rounded-md transition-colors",
            dark ? "hover:bg-indigo-500/15 text-white/25 hover:text-indigo-300" : "hover:bg-slate-200 text-slate-300 hover:text-slate-600"
          )}
        >
          <Copy size={12} />
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
            <Trash2 size={12} />
          </button>
        )}
      </div>

      {/* Filtros */}
      <div className={cn(
        "flex gap-1 px-3 py-1.5 border-b overflow-x-auto shrink-0",
        dark ? "border-white/5" : "border-slate-100"
      )}>
        {FILTROS.map(({ key, label, color }) => {
          const count = key === "todos" ? null : log.filter((e) => e.tipo === key).length;
          return (
            <button
              key={key}
              onClick={() => setFiltro(key)}
              className={cn(
                "flex items-center gap-1 px-2 py-0.5 rounded-lg text-[11px] font-semibold whitespace-nowrap transition-all duration-150",
                filtro === key
                  ? dark
                    ? "bg-indigo-600/70 text-white"
                    : "bg-indigo-600 text-white"
                  : dark
                    ? cn("text-white/25 hover:text-white/60 hover:bg-white/5", color)
                    : "text-slate-400 hover:text-slate-600 hover:bg-slate-100"
              )}
            >
              {label}
              {count !== null && count > 0 && (
                <span className="opacity-50 tabular-nums">{count}</span>
              )}
            </button>
          );
        })}
      </div>

      {/* Lista — overflow-anchor:none impide que el browser reajuste el scroll
          al insertar nuevos elementos arriba (newest-at-top pattern) */}
      <div
        ref={listRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto p-2 font-mono text-[11px] space-y-px min-h-0"
        style={{ overflowAnchor: "none" }}
      >
        {logFiltrado.length === 0 && (
          <p className={cn("italic p-2", dark ? "text-white/15" : "text-slate-300")}>
            _ sin eventos{filtro !== "todos" ? ` de tipo '${filtro}'` : " aún"}
          </p>
        )}
        <AnimatePresence initial={false}>
          {[...logFiltrado].reverse().map((e) => {
            const c = TIPO_CONFIG[e.tipo];
            return (
              <motion.div
                key={e.id}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ duration: 0.15 }}
                className={cn(
                  "flex items-start gap-2 px-2 py-[3px] rounded-lg transition-colors",
                  c.rowBg,
                  dark ? "hover:bg-white/3" : "hover:bg-slate-50"
                )}
              >
                {/* Dot */}
                <span className={cn("mt-[3px] shrink-0 w-1.5 h-1.5 rounded-full", c.dot)} />
                {/* Hora */}
                <span className={cn("shrink-0 tabular-nums text-[10px]", dark ? "text-white/20" : "text-slate-300")}>
                  {formatHora(e.ts)}
                </span>
                {/* Prefix */}
                <span className={cn("shrink-0 font-bold", c.text)}>{c.prefix}</span>
                {/* Mensaje */}
                <span className={cn("flex-1 leading-relaxed break-all", c.text)}>{e.mensaje}</span>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>

      {/* "Ir al final" cuando auto-scroll está pausado */}
      <AnimatePresence>
        {!autoScroll && (
          <motion.button
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 4 }}
            onClick={() => {
              setAutoScroll(true);
              if (listRef.current) listRef.current.scrollTop = 0;
            }}
            className={cn(
              "flex items-center justify-center gap-1.5 w-full py-1.5 text-xs border-t transition-colors shrink-0",
              dark
                ? "border-indigo-500/15 bg-indigo-600/15 text-indigo-300 hover:bg-indigo-600/25"
                : "border-slate-200 bg-indigo-50 text-indigo-600 hover:bg-indigo-100"
            )}
          >
            <ChevronDown size={11} className="rotate-180" /> Ver recientes
          </motion.button>
        )}
      </AnimatePresence>
    </div>
  );
}
