import type { ToastItem } from "./toast-types";

type ToastStackProps = {
  toasts: ToastItem[];
};

function ToastStack({ toasts }: ToastStackProps) {
  return (
    <div className="toast-stack" aria-live="polite">
      {toasts.map((toast) => (
        <div key={toast.id} className={`toast toast-${toast.kind}`}>
          {toast.message}
        </div>
      ))}
    </div>
  );
}

export default ToastStack;
