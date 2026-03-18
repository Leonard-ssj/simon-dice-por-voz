"use client";

import { Wifi, WifiOff, Usb, Radio, Loader2, Mic, Volume2, Cpu } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface Props {
  conectado: boolean;
  modo: "websocket" | "serial";
  onModoChange: (m: "websocket" | "serial") => void;
  onConectar: () => void;
  onDesconectar: () => void;
  serialDisponible?: boolean;
  dark: boolean;
  whisperCargado?: boolean;
  whisperTranscribiendo?: boolean;
  whisperProgreso?: string;
  // Retroalimentación del micrófono en tiempo real
  whisperNivelMic?: number;        // RMS normalizado 0-1 (barra de nivel)
  whisperGrabando?: boolean;       // VAD activo — grabando voz
  whisperMicAbierto?: boolean;     // getUserMedia tuvo éxito — mic realmente abierto
  whisperTiempoRestante?: number | null; // countdown en segundos
  whisperProcesando?: boolean;     // Whisper procesando audio (inferencia)
  enEscucha?: boolean;             // estado LISTENING activo (juego pide voz)
  puedoHablar?: boolean;           // PTT habilitado en el estado actual
  iniciarPTT?: () => void;         // iniciar grabación PTT
  finalizarPTT?: () => void;       // finalizar grabación PTT
  whisperLocalActivo?: boolean;    // Whisper corre en Python local (no en browser)
  dispositivoMic?: string | null;      // nombre del micrófono activo
  dispositivoSpeaker?: string | null;  // nombre del altavoz activo
  whisperModelo?: string | null;       // modelo Whisper en uso
  onReiniciar?: () => void;        // callback para reiniciar el juego
}

export default function ConnectionPanel({
  conectado,
  modo,
  onModoChange,
  onConectar,
  onDesconectar,
  serialDisponible = false,
  dark,
  whisperCargado = false,
  whisperTranscribiendo = false,
  whisperProgreso = "",
  whisperNivelMic = 0,
  whisperGrabando = false,
  whisperMicAbierto = false,
  whisperProcesando = false,
  enEscucha = false,
  puedoHablar = false,
  iniciarPTT,
  finalizarPTT,
  whisperLocalActivo = false,
  dispositivoMic = null,
  dispositivoSpeaker = null,
  whisperModelo = null,
  onReiniciar,
}: Props) {
  const mostrarWhisper = modo === "serial" ? serialDisponible : true;

  // Color de la barra de nivel: verde si sobre umbral, azul si bajo
  const barColor = whisperNivelMic > 0.25
    ? "bg-emerald-400"
    : whisperNivelMic > 0.08
    ? "bg-yellow-400"
    : "bg-blue-400/60";

  return (
    <div className={cn(
      "flex flex-wrap items-center gap-3 px-4 py-3 rounded-2xl border",
      dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
    )}>
      {/* Selector de modo */}
      <div className={cn("flex gap-1 p-1 rounded-xl", dark ? "bg-white/5" : "bg-slate-100")}>
        <button
          onClick={() => onModoChange("websocket")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200",
            modo === "websocket"
              ? "bg-indigo-600 text-white shadow-lg shadow-indigo-500/30"
              : dark ? "text-white/40 hover:text-white/70" : "text-slate-400 hover:text-slate-600"
          )}
        >
          <Radio size={12} />
          Simulador — WebSocket
        </button>
        <button
          onClick={() => onModoChange("serial")}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all duration-200",
            modo === "serial"
              ? "bg-purple-600 text-white shadow-lg shadow-purple-500/30"
              : dark ? "text-white/40 hover:text-white/70" : "text-slate-400 hover:text-slate-600"
          )}
        >
          <Usb size={12} />
          ESP32 — Web Serial
        </button>
      </div>

      {/* Aviso serial no disponible */}
      {modo === "serial" && !serialDisponible && (
        <span className="text-yellow-400/70 text-xs">
          ⚠ Solo Chrome o Edge
        </span>
      )}

      {/* Badge + barra de nivel de Whisper — solo cuando conectado o ya cargado */}
      {mostrarWhisper && (conectado || whisperCargado || whisperProgreso !== "") && (
        <div className="flex items-center gap-2">
          {/* Botón PTT — mantener presionado para hablar */}
          {puedoHablar && iniciarPTT && finalizarPTT ? (
            <button
              onMouseDown={iniciarPTT}
              onMouseUp={finalizarPTT}
              onMouseLeave={finalizarPTT}
              onTouchStart={(e) => { e.preventDefault(); iniciarPTT(); }}
              onTouchEnd={finalizarPTT}
              className={cn(
                "flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-bold select-none transition-all duration-150",
                whisperGrabando
                  ? "bg-emerald-500/30 text-emerald-200 border border-emerald-400/50 shadow-lg shadow-emerald-500/20 scale-95"
                  : whisperProcesando
                    ? "bg-purple-500/25 text-purple-200 border border-purple-400/40 shadow-md shadow-purple-500/15"
                    : whisperTranscribiendo
                      ? "bg-blue-500/20 text-blue-200 border border-blue-400/30"
                      : dark
                        ? "bg-indigo-600/25 text-indigo-200 border border-indigo-500/40 hover:bg-indigo-500/35 hover:shadow-lg hover:shadow-indigo-500/20 active:scale-95"
                        : "bg-indigo-600 text-white border border-indigo-500 hover:bg-indigo-700 active:scale-95 shadow-md shadow-indigo-500/20"
              )}
            >
              <Mic size={14} className={cn(
                "transition-transform",
                whisperGrabando ? "text-emerald-300 scale-110" : ""
              )} />
              {whisperTranscribiendo
                ? whisperGrabando
                  ? "🔴 Grabando..."
                  : whisperProcesando
                    ? "⚙ Procesando..."
                    : "Abriendo mic..."
                : "🎤 Mantén para hablar"}
            </button>
          ) : null}

          {/* Badge de estado — LISTENING pero mic aún no abierto */}
          {enEscucha && !whisperTranscribiendo ? (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              "bg-indigo-500/15 text-indigo-300"
            )}>
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
              Escuchando...
            </span>
          ) : whisperTranscribiendo ? (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              whisperGrabando
                ? "bg-emerald-500/20 text-emerald-300 animate-pulse"
                : whisperProcesando
                  ? "bg-purple-500/20 text-purple-300 animate-pulse"
                  : whisperMicAbierto
                    ? "bg-blue-500/15 text-blue-300 animate-pulse"
                    : "bg-white/8 text-white/40"
            )}>
              <Mic size={11} className={whisperGrabando ? "text-emerald-400" : ""} />
              {whisperGrabando
                ? "Detectando voz..."
                : whisperProcesando
                  ? "Procesando..."
                  : whisperMicAbierto
                    ? "Habla ahora"
                    : "Abriendo micrófono..."}
            </span>
          ) : whisperCargado ? (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              whisperLocalActivo
                ? dark ? "bg-blue-500/15 text-blue-300" : "bg-blue-100 text-blue-600"
                : dark ? "bg-emerald-500/15 text-emerald-400" : "bg-emerald-100 text-emerald-600"
            )}>
              <span className={cn("w-1.5 h-1.5 rounded-full", whisperLocalActivo ? "bg-blue-400" : "bg-emerald-400")} />
              {whisperLocalActivo ? "Whisper local" : "Whisper listo"}
            </span>
          ) : (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              dark ? "bg-yellow-500/15 text-yellow-400" : "bg-yellow-100 text-yellow-600"
            )}>
              <Loader2 size={11} className="animate-spin" />
              {whisperProgreso || "Cargando modelo..."}
            </span>
          )}

          {/* Barra de nivel del micrófono — visible cuando está escuchando */}
          {whisperTranscribiendo && (
            <div
              title={`Nivel mic: ${Math.round(whisperNivelMic * 100)}%`}
              className={cn(
                "w-24 h-3 rounded-full overflow-hidden",
                dark ? "bg-white/8" : "bg-slate-200"
              )}
            >
              <div
                className={cn("h-full rounded-full transition-all duration-150", barColor)}
                style={{ width: `${Math.round(whisperNivelMic * 100)}%` }}
              />
            </div>
          )}
        </div>
      )}

      {/* Botón reiniciar */}
      {conectado && onReiniciar && (
        <button
          onClick={onReiniciar}
          title="Reiniciar juego"
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold transition-colors",
            dark
              ? "bg-white/5 text-white/50 hover:bg-orange-500/20 hover:text-orange-300 border border-white/8"
              : "bg-slate-100 text-slate-500 hover:bg-orange-100 hover:text-orange-600 border border-slate-200"
          )}
        >
          ↺ Reiniciar
        </button>
      )}

      {/* Estado + botón conectar — siempre en la primera fila */}
      <div className="ml-auto flex items-center gap-2">
        <div className={cn(
          "flex items-center gap-1.5 text-xs font-medium",
          conectado ? "text-emerald-400" : dark ? "text-white/30" : "text-slate-400"
        )}>
          {conectado ? <Wifi size={13} /> : <WifiOff size={13} />}
          {conectado ? "Conectado" : "Desconectado"}
        </div>
        {conectado && (
          <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
        )}
        <Button
          variant={conectado ? "destructive" : "success"}
          size="sm"
          onClick={conectado ? onDesconectar : onConectar}
          disabled={modo === "serial" && !serialDisponible && !conectado}
        >
          {conectado ? "Desconectar" : "Conectar"}
        </Button>
      </div>

      {/* Info de dispositivos — segunda fila cuando conectado */}
      {conectado && (dispositivoMic || dispositivoSpeaker || whisperModelo) && (
        <div className="basis-full flex items-center gap-4 flex-wrap pt-1 border-t border-white/5 text-xs">
          {dispositivoMic && (
            <span className={cn("flex items-center gap-1.5", dark ? "text-white/30" : "text-slate-400")}>
              <Mic size={10} />
              {dispositivoMic}
            </span>
          )}
          {!dispositivoMic && !whisperLocalActivo && (
            <span className={cn("flex items-center gap-1.5", dark ? "text-white/30" : "text-slate-400")}>
              <Mic size={10} />
              Micrófono del navegador
            </span>
          )}
          {dispositivoSpeaker && (
            <span className={cn("flex items-center gap-1.5", dark ? "text-white/30" : "text-slate-400")}>
              <Volume2 size={10} />
              {dispositivoSpeaker}
            </span>
          )}
          {whisperModelo && (
            <span className={cn("flex items-center gap-1.5", dark ? "text-white/30" : "text-slate-400")}>
              <Cpu size={10} />
              Whisper {whisperModelo}
            </span>
          )}
        </div>
      )}
    </div>
  );
}
