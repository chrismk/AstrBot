interface LoadingProps {
  message?: string;
}

export function Loading({ message = '加载中...' }: LoadingProps) {
  return (
    <div className="flex flex-col items-center justify-center min-h-screen">
      <div className="w-8 h-8 border-4 border-tg-button border-t-transparent rounded-full animate-spin mb-4" />
      <p className="text-tg-hint text-sm">{message}</p>
    </div>
  );
}
