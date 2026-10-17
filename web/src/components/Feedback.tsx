import { AlertCircle, CheckCircle2, RefreshCw } from "lucide-react";

interface ErrorNoticeProps {
  message: string;
  onRetry?: () => void;
  compact?: boolean;
}

export function ErrorNotice({ message, onRetry, compact = false }: ErrorNoticeProps) {
  return (
    <div className={`feedback feedback--error ${compact ? "feedback--compact" : ""}`} role="alert">
      <AlertCircle size={18} aria-hidden="true" />
      <span>{message}</span>
      {onRetry && (
        <button type="button" className="text-button" onClick={onRetry}>
          <RefreshCw size={15} aria-hidden="true" />
          重试
        </button>
      )}
    </div>
  );
}

interface SuccessNoticeProps {
  message: string;
}

export function SuccessNotice({ message }: SuccessNoticeProps) {
  return (
    <div className="feedback feedback--success" role="status">
      <CheckCircle2 size={18} aria-hidden="true" />
      <span>{message}</span>
    </div>
  );
}
