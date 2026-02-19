import type { ButtonHTMLAttributes, ReactNode } from "react";

type ButtonVariant = "primary" | "secondary" | "range";

type ButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  active?: boolean;
  children: ReactNode;
};

function Button({ variant = "secondary", active = false, className, children, ...props }: ButtonProps) {
  const baseClass =
    variant === "primary" ? "primary-btn" : variant === "range" ? (active ? "range-btn active" : "range-btn") : "secondary-btn";
  return (
    <button {...props} className={`${baseClass}${className ? ` ${className}` : ""}`}>
      {children}
    </button>
  );
}

export default Button;
