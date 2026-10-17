import { LoaderCircle } from "lucide-react";

interface FullPageStateProps {
  kind?: "loading";
  title: string;
  detail?: string;
}

export function FullPageState({ kind = "loading", title, detail }: FullPageStateProps) {
  return (
    <div className="full-page-state" role={kind === "loading" ? "status" : "alert"}>
      <LoaderCircle className="spin" size={24} aria-hidden="true" />
      <strong>{title}</strong>
      {detail && <span>{detail}</span>}
    </div>
  );
}
