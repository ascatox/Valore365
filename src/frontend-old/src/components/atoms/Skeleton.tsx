export const Skeleton = ({ className }: { className?: string }) => {
  return <div className={`animate-pulse bg-slate-800 rounded-md ${className}`} />;
};