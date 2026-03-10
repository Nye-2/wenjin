import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-lg text-sm font-medium transition-all duration-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--accent-primary)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--bg-base)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-gradient-to-r from-[var(--accent-primary)] to-[#1D4ED8] text-white shadow-md hover:shadow-lg hover:scale-[1.02] active:scale-[0.98]",
        destructive:
          "bg-red-500/15 text-[var(--semantic-error)] border border-red-500/30 hover:bg-red-500/25",
        outline:
          "border border-[var(--border-default)] bg-transparent hover:bg-[var(--bg-surface)] hover:border-[var(--accent-secondary)] text-[var(--text-primary)]",
        secondary:
          "bg-[var(--accent-primary)]/15 text-[var(--accent-secondary)] border border-[var(--accent-secondary)]/30 hover:bg-[var(--accent-primary)]/25",
        ghost:
          "hover:bg-[var(--bg-surface)] text-[var(--text-secondary)] hover:text-[var(--text-primary)]",
        link:
          "text-[var(--accent-secondary)] underline-offset-4 hover:underline hover:text-[var(--accent-primary)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-12 rounded-lg px-8",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";

export { Button, buttonVariants };
