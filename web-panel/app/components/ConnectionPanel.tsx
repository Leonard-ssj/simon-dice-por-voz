"use client";

import { Wifi, WifiOff, Usb, Radio, Loader2, Mic } from "lucide-react";
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
  whisperTiempoRestante = null,
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

      {/* Badge + barra de nivel de Whisper */}
      {mostrarWhisper && (
        <div className="flex items-center gap-2">
          {/* Badge de estado */}
          {whisperTranscribiendo ? (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              whisperGrabando
                ? "bg-emerald-500/20 text-emerald-300 animate-pulse"
                : whisperMicAbierto
                  ? "bg-blue-500/15 text-blue-300 animate-pulse"
                  : "bg-white/8 text-white/40"
            )}>
              <Mic size={11} className={whisperGrabando ? "text-emerald-400" : ""} />
              {whisperGrabando
                ? "Detectando voz..."
                : whisperMicAbierto
                  ? "Habla ahora"
                  : "Abriendo micrófono..."}
            </span>
          ) : whisperCargado ? (
            <span className={cn(
              "flex items-center gap-1.5 text-xs font-medium px-2.5 py-1 rounded-full",
              dark ? "bg-emerald-500/15 text-emerald-400" : "bg-emerald-100 text-emerald-600"
            )}>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
              Whisper listo
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

      {/* Estado conexión */}
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
      </div>

      {/* Botón conectar/desconectar */}
      <Button
        variant={conectado ? "destructive" : "success"}
        size="sm"
        onClick={conectado ? onDesconectar : onConectar}
        disabled={!conectado && !whisperCargado}
      >
        {conectado ? "Desconectar" : "Conectar"}
      </Button>
    </div>
  );
}
