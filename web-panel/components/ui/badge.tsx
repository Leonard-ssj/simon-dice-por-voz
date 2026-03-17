import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";

const badgeVariants = cva(
  "inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-semibold transition-colors",
  {
    variants: {
      variant: {
        default:  "bg-white/10 text-white/70",
        success:  "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30",
        error:    "bg-red-500/20 text-red-400 border border-red-500/30",
        warning:  "bg-yellow-500/20 text-yellow-400 border border-yellow-500/30",
        info:     "bg-blue-500/20 text-blue-400 border border-blue-500/30",
        rojo:     "bg-red-500/30 text-red-300 border border-red-500/40",
        verde:    "bg-emerald-500/30 text-emerald-300 border border-emerald-500/40",
        azul:     "bg-blue-500/30 text-blue-300 border border-blue-500/40",
        amarillo: "bg-yellow-500/30 text-yellow-300 border border-yellow-500/40",
      },
    },
    defaultVariants: { variant: "default" },
  }
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

export function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
