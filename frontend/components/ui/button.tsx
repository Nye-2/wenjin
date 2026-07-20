import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center whitespace-nowrap rounded-[var(--wjn-radius-md)] text-sm font-semibold transition-[background,color,border-color,box-shadow,transform] duration-150 ease-[var(--wjn-ease-standard)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--wjn-blue)] focus-visible:ring-offset-2 focus-visible:ring-offset-[var(--wjn-bg-base)] disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default:
          "bg-[var(--wjn-navy)] text-white shadow-[0_8px_20px_rgba(28,36,32,0.16)] hover:bg-[var(--wjn-blue-strong)] active:translate-y-0",
        destructive:
          "border border-[rgba(179,52,62,0.28)] bg-[var(--wjn-error-soft)] text-[var(--wjn-error)] hover:bg-[rgba(179,52,62,0.16)]",
        outline:
          "border border-[var(--wjn-line)] bg-[var(--wjn-surface)] text-[var(--wjn-text)] shadow-[var(--wjn-shadow-sm)] hover:border-[var(--wjn-accent-line)] hover:bg-[var(--wjn-surface-subtle)]",
        secondary:
          "border border-[var(--wjn-accent-line)] bg-[var(--wjn-accent-soft)] text-[var(--wjn-blue-strong)] hover:bg-[rgba(20,84,74,0.16)]",
        ghost:
          "text-[var(--wjn-text-secondary)] hover:bg-[rgba(28,36,32,0.05)] hover:text-[var(--wjn-text)]",
        link:
          "text-[var(--wjn-blue)] underline-offset-4 hover:underline hover:text-[var(--wjn-blue-strong)]",
      },
      size: {
        default: "h-10 px-4 py-2",
        sm: "h-8 rounded-[var(--wjn-radius)] px-3 text-xs",
        lg: "h-12 rounded-[var(--wjn-radius-md)] px-8",
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
