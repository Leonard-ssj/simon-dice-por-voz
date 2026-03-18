"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Mic2, Sun, Moon, HelpCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { useWebSocket } from "../hooks/useWebSocket";
import { useWebSerial } from "../hooks/useWebSerial";
import ConnectionPanel from "./components/ConnectionPanel";
import GameStatus from "./components/GameStatus";
import LEDPanel from "./components/LEDPanel";
import SequenceDisplay from "./components/SequenceDisplay";
import LogConsole from "./components/LogConsole";
import ScoreBoard from "./components/ScoreBoard";
import HowToPlay from "./components/HowToPlay";
import TurnoTimer from "./components/TurnoTimer";
import SesionStats from "./components/SesionStats";
import ParticleBackground from "./components/ParticleBackground";
import type { ColorJuego } from "../types/game";

type Modo = "websocket" | "serial";

export default function Home() {
  const [modo, setModo]         = useState<Modo>("websocket");
  const [dark, setDark]         = useState(true);   // oscuro por defecto
  const [showHelp, setShowHelp] = useState(false);

  const ws     = useWebSocket();
  const serial = useWebSerial();
  const activo = modo === "websocket" ? ws : serial;
  const { estadoJuego } = activo;
  const limpiarLog = modo === "websocket" ? ws.limpiarLog : undefined;
  const whisperProgreso       = activo.whisperProgresoDescarga ?? "";
  const whisperNivelMic       = activo.whisperNivelMic ?? 0;
  const whisperGrabando       = activo.whisperGrabando ?? false;
  const whisperMicAbierto     = activo.whisperMicAbierto ?? false;
  const whisperProcesando       = activo.whisperProcesando ?? false;
  const whisperTiempoRestante   = activo.whisperTiempoRestante ?? null;
  const handleReiniciar         = activo.reiniciar ?? undefined;
  const iniciarPTT              = activo.iniciarPTT;
  const finalizarPTT            = activo.finalizarPTT;
  const puedoHablar             = activo.puedoHablar ?? false;
  const whisperLocalActivo      = (activo as typeof ws).whisperLocalActivo ?? false;
  const dispositivoMic          = estadoJuego.dispositivoMic ?? null;
  const dispositivoSpeaker      = estadoJuego.dispositivoSpeaker ?? null;
  const whisperModelo           = estadoJuego.whisperModelo ?? null;

  const handleConectar    = useCallback(() => activo.conectar(),    [activo]);
  const handleDesconectar = useCallback(() => activo.desconectar(), [activo]);

  // ── Estadísticas de sesión ──
  const [mejorNivel,      setMejorNivel]      = useState(0);
  const [mejorPuntuacion, setMejorPuntuacion] = useState(0);
  const [totalPartidas,   setTotalPartidas]   = useState(0);
  const [rachaActual,     setRachaActual]      = useState(0);
  const [rachaMaxima,     setRachaMaxima]      = useState(0);

  // Actualizar stats cuando cambia el estado del juego
  const prevEstado = useRef<string>("");
  useEffect(() => {
    const e = estadoJuego.estado;
    if (e === prevEstado.current) return;
    prevEstado.current = e;

    if (e === "CORRECT") {
      const nueva = rachaActual + 1;
      setRachaActual(nueva);
      setRachaMaxima((m) => Math.max(m, nueva));
    }
    if (e === "WRONG" || e === "GAMEOVER") {
      setRachaActual(0);
    }
    if (e === "GAMEOVER") {
      setTotalPartidas((n) => n + 1);
      setMejorNivel((m) => Math.max(m, estadoJuego.nivel));
      setMejorPuntuacion((m) => Math.max(m, estadoJuego.puntuacion));
    }
  }, [estadoJuego.estado, estadoJuego.nivel, estadoJuego.puntuacion, rachaActual]);

  const ledActivo: ColorJuego | null = estadoJuego.ledActivo;

  const esGameOver = estadoJuego.estado === "GAMEOVER";

  return (
    <div className={cn(
      "h-screen overflow-hidden flex flex-col transition-colors duration-300",
      dark ? "bg-[#060608] text-white" : "bg-slate-100 text-slate-900"
    )}>
      {/* Fondos decorativos */}
      {dark ? (
        <>
          <div className="fixed inset-0 bg-grid-white bg-grid opacity-100 pointer-events-none" />
          <div className="fixed inset-0 bg-[radial-gradient(ellipse_80%_40%_at_50%_-5%,rgba(99,102,241,0.12),transparent)] pointer-events-none" />
        </>
      ) : (
        <div className="fixed inset-0 bg-[radial-gradient(ellipse_70%_35%_at_50%_0%,rgba(99,102,241,0.07),transparent)] pointer-events-none" />
      )}
      <ParticleBackground dark={dark} />

      {/* Contenido principal — flex col, llena la pantalla sin scroll */}
      <div className="relative flex flex-col h-full max-w-6xl w-full mx-auto px-5 py-4 gap-3">

        {/* ── Header ── */}
        <div className="flex items-center justify-between shrink-0">
          <div className="flex items-center gap-3">
            <div className={cn(
              "w-9 h-9 rounded-xl flex items-center justify-center",
              dark ? "bg-indigo-600/20 border border-indigo-500/30" : "bg-indigo-100 border border-indigo-200"
            )}>
              <Mic2 size={18} className={dark ? "text-indigo-400" : "text-indigo-600"} />
            </div>
            <div>
              <h1 className={cn("text-lg font-bold tracking-tight", dark ? "text-white" : "text-slate-800")}>
                Simon Dice por Voz
              </h1>
              <p className={cn("text-xs", dark ? "text-white/30" : "text-slate-500")}>
                Sistemas Inteligentes
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowHelp(true)}
              className={cn(
                "p-2 rounded-xl transition-colors",
                dark ? "hover:bg-white/8 text-white/40 hover:text-white" : "hover:bg-slate-200 text-slate-400 hover:text-slate-700"
              )}
              title="Cómo jugar"
            >
              <HelpCircle size={18} />
            </button>
            <button
              onClick={() => setDark(!dark)}
              className={cn(
                "p-2 rounded-xl transition-colors",
                dark ? "hover:bg-white/8 text-white/40 hover:text-white" : "hover:bg-slate-200 text-slate-400 hover:text-slate-700"
              )}
              title={dark ? "Modo claro" : "Modo oscuro"}
            >
              {dark ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
        </div>

        {/* ── Conexión ── */}
        <div className="shrink-0">
          <ConnectionPanel
            conectado={estadoJuego.conectado}
            modo={modo}
            onModoChange={setModo}
            onConectar={handleConectar}
            onDesconectar={handleDesconectar}
            serialDisponible={"serial" in (typeof navigator !== "undefined" ? navigator : {})}
            dark={dark}
            whisperCargado={estadoJuego.whisperCargado}
            whisperTranscribiendo={estadoJuego.whisperTranscribiendo}
            whisperProgreso={whisperProgreso}
            whisperNivelMic={whisperNivelMic}
            whisperGrabando={whisperGrabando}
            whisperMicAbierto={whisperMicAbierto}
            whisperProcesando={whisperProcesando}
            enEscucha={estadoJuego.estado === "LISTENING"}
            puedoHablar={puedoHablar}
            iniciarPTT={iniciarPTT}
            finalizarPTT={finalizarPTT}
            whisperLocalActivo={whisperLocalActivo}
            dispositivoMic={dispositivoMic}
            dispositivoSpeaker={dispositivoSpeaker}
            whisperModelo={whisperModelo}
            onReiniciar={handleReiniciar}
            whisperTiempoRestante={whisperTiempoRestante}
          />
        </div>

        {/* ── Game Over banner ── */}
        <AnimatePresence>
          {esGameOver && (
            <motion.div
              initial={{ opacity: 0, y: -10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -10 }}
              className={cn(
                "shrink-0 rounded-2xl border px-5 py-3 text-center",
                dark ? "border-red-500/20 bg-red-500/5" : "border-red-200 bg-red-50"
              )}
            >
              <p className="text-xl font-bold text-red-400 mb-0.5">Fin del juego</p>
              <p className={cn("text-sm", dark ? "text-white/50" : "text-slate-600")}>
                Puntuación: <span className="text-yellow-500 font-bold">{estadoJuego.puntuacion}</span>
                {" · "}Nivel: <span className={cn("font-bold", dark ? "text-white" : "text-slate-700")}>{estadoJuego.nivel}</span>
                {" · "}Di <strong className={dark ? "text-white/70" : "text-slate-700"}>EMPIEZA</strong> para volver
              </p>
            </motion.div>
          )}
        </AnimatePresence>

        {/* ── Área principal: 2 columnas, flex-1 ── */}
        <div className="grid grid-cols-1 lg:grid-cols-5 gap-3 flex-1 min-h-0">

          {/* ── Columna izquierda: LEDs + Secuencia (2/5) ── */}
          <div className="lg:col-span-2 flex flex-col gap-3">
            <div className={cn(
              "rounded-2xl border p-5 flex flex-col items-center gap-3 shrink-0",
              dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
            )}>
              <p className={cn(
                "text-xs font-semibold uppercase tracking-widest self-start",
                dark ? "text-white/25" : "text-slate-400"
              )}>Panel de LEDs</p>
              <LEDPanel activo={ledActivo} secuencia={estadoJuego.secuencia} dark={dark} />
            </div>

            <div className={cn(
              "rounded-2xl border px-4 py-3 shrink-0",
              dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
            )}>
              <p className={cn(
                "text-[10px] font-semibold uppercase tracking-widest mb-2",
                dark ? "text-white/25" : "text-slate-400"
              )}>
                Secuencia{estadoJuego.secuencia.length > 0 && ` · ${estadoJuego.secuencia.length} pasos`}
              </p>
              <SequenceDisplay secuencia={estadoJuego.secuencia} esperado={estadoJuego.esperado} />
            </div>

            {/* Temporizador de turno / Referencia de comandos */}
            <TurnoTimer
              estado={estadoJuego.estado}
              esperado={estadoJuego.esperado}
              dark={dark}
              timeoutMs={30000}
              startDelayMs={3500}
            />

            {/* Estadísticas de sesión */}
            <SesionStats
              mejorNivel={mejorNivel}
              mejorPuntuacion={mejorPuntuacion}
              totalPartidas={totalPartidas}
              rachaMaxima={rachaMaxima}
              dark={dark}
            />
          </div>

          {/* ── Columna derecha: Estado + Score + Log (3/5) ── */}
          <div className="lg:col-span-3 flex flex-col gap-3 min-h-0">

            {/* Estado + Score en una fila horizontal */}
            <div className="grid grid-cols-2 gap-3 shrink-0">
              <div className={cn(
                "rounded-2xl border p-4 flex flex-col gap-2",
                dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
              )}>
                <p className={cn(
                  "text-xs font-semibold uppercase tracking-widest",
                  dark ? "text-white/25" : "text-slate-400"
                )}>Estado</p>
                <GameStatus
                  estado={estadoJuego.estado}
                  ultimaDeteccion={estadoJuego.ultimaDeteccion}
                  ultimoTextoWhisper={estadoJuego.ultimoTextoWhisper}
                  ultimoResultado={estadoJuego.ultimoResultado}
                  dark={dark}
                  grabando={whisperGrabando || estadoJuego.whisperTranscribiendo}
                />
              </div>

              <ScoreBoard nivel={estadoJuego.nivel} puntuacion={estadoJuego.puntuacion} dark={dark} />
            </div>

            {/* Log — ocupa todo el espacio restante */}
            <div className="flex-1 min-h-0">
              <LogConsole log={estadoJuego.log} dark={dark} onClear={limpiarLog} />
            </div>

          </div>
        </div>

      </div>

      {/* ── Modal Cómo Jugar ── */}
      <AnimatePresence>
        {showHelp && (
          <HowToPlay onClose={() => setShowHelp(false)} dark={dark} />
        )}
      </AnimatePresence>
    </div>
  );
}
