import { Eye, EyeOff } from "lucide-react";
import { useId, useState, type InputHTMLAttributes } from "react";

interface FormFieldProps extends Omit<InputHTMLAttributes<HTMLInputElement>, "id"> {
  label: string;
  hint?: string;
  error?: string;
  password?: boolean;
  revealLabel?: string;
  hideLabel?: string;
}

export function FormField({
  label,
  hint,
  error,
  password = false,
  revealLabel = "显示密码",
  hideLabel = "隐藏密码",
  ...inputProps
}: FormFieldProps) {
  const id = useId();
  const [revealed, setRevealed] = useState(false);
  const descriptionId = `${id}-description`;

  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <div className={`input-wrap ${error ? "input-wrap--error" : ""}`}>
        <input
          {...inputProps}
          id={id}
          type={password && revealed ? "text" : inputProps.type}
          aria-invalid={Boolean(error)}
          aria-describedby={error || hint ? descriptionId : undefined}
        />
        {password && (
          <button
            type="button"
            className="password-toggle"
            aria-label={revealed ? hideLabel : revealLabel}
            onClick={() => setRevealed((value) => !value)}
          >
            {revealed ? <EyeOff size={18} /> : <Eye size={18} />}
          </button>
        )}
      </div>
      {(error || hint) && (
        <p id={descriptionId} className={error ? "field-error" : "field-hint"}>
          {error || hint}
        </p>
      )}
    </div>
  );
}
