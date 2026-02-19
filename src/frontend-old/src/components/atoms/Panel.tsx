import type { ReactNode } from "react";

type PanelProps = {
  title?: string;
  className?: string;
  children: ReactNode;
};

function Panel({ title, className, children }: PanelProps) {
  return (
    <section className={`panel${className ? ` ${className}` : ""}`}>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  );
}

export default Panel;
