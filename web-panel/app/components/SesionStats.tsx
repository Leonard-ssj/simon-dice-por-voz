"use client";

import { motion, AnimatePresence } from "framer-motion";
import { Trophy, Layers, Target, Gamepad2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  mejorNivel: number;
  mejorPuntuacion: number;
  totalPartidas: number;
  rachaMaxima: number;
  dark: boolean;
}

function Stat({
  icon: Icon, label, value, color, dark,
}: {
  icon: React.ElementType; label: string; value: number; color: string; dark: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <div className={cn("shrink-0 rounded-lg p-1.5", dark ? "bg-white/5" : "bg-slate-100")}>
        <Icon size={12} className={color} />
      </div>
      <div className="flex-1 min-w-0">
        <p className={cn("text-[10px] truncate", dark ? "text-white/30" : "text-slate-400")}>{label}</p>
        <AnimatePresence mode="wait">
          <motion.p
            key={value}
            initial={{ opacity: 0, y: -6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.15 }}
            className={cn("text-lg font-bold tabular-nums leading-tight", dark ? "text-white" : "text-slate-800")}
          >
            {value}
          </motion.p>
        </AnimatePresence>
      </div>
    </div>
  );
}

export default function SesionStats({ mejorNivel, mejorPuntuacion, totalPartidas, rachaMaxima, dark }: Props) {
  return (
    <div className={cn(
      "rounded-2xl border p-4 flex flex-col gap-3",
      dark ? "border-white/5 bg-white/2" : "border-slate-200 bg-white"
    )}>
      <p className={cn("text-[10px] font-semibold uppercase tracking-widest", dark ? "text-white/25" : "text-slate-400")}>
        Esta sesión
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Stat icon={Layers}    label="Mejor nivel"   value={mejorNivel}      color="text-indigo-400"  dark={dark} />
        <Stat icon={Trophy}    label="Mejor puntaje" value={mejorPuntuacion} color="text-yellow-400"  dark={dark} />
        <Stat icon={Gamepad2}  label="Partidas"      value={totalPartidas}   color="text-blue-400"    dark={dark} />
        <Stat icon={Target}    label="Mejor racha"   value={rachaMaxima}     color="text-emerald-400" dark={dark} />
      </div>
    </div>
  );
}
