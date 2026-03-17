import { cn } from "@/lib/utils";
import { cva, type VariantProps } from "class-variance-authority";
import { Slot } from "@radix-ui/react-slot";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded-xl text-sm font-semibold transition-all duration-200 disabled:opacity-50 disabled:pointer-events-none",
  {
    variants: {
      variant: {
        default:     "bg-white/10 text-white hover:bg-white/15 border border-white/10",
        primary:     "bg-indigo-600 text-white hover:bg-indigo-500 shadow-lg shadow-indigo-500/20",
        success:     "bg-emerald-600 text-white hover:bg-emerald-500 shadow-lg shadow-emerald-500/20",
        destructive: "bg-red-600 text-white hover:bg-red-500 shadow-lg shadow-red-500/20",
        ghost:       "text-white/60 hover:text-white hover:bg-white/5",
      },
      size: {
        sm: "h-8 px-3 text-xs",
        md: "h-10 px-5",
        lg: "h-12 px-7 text-base",
      },
    },
    defaultVariants: { variant: "default", size: "md" },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export function Button({ className, variant, size, asChild = false, ...props }: ButtonProps) {
  const Comp = asChild ? Slot : "button";
  return <Comp className={cn(buttonVariants({ variant, size }), className)} {...props} />;
}
