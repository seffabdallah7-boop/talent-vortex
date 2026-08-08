import { Clock, CheckCircle2, XCircle } from "lucide-react";

const MAP = {
  pending: { label: "En attente", cls: "status-pending", Icon: Clock },
  accepted: { label: "Acceptée", cls: "status-accepted", Icon: CheckCircle2 },
  rejected: { label: "Refusée", cls: "status-rejected", Icon: XCircle },
};

export default function StatusBadge({ status, className = "" }) {
  const s = MAP[status] || MAP.pending;
  const { Icon } = s;
  return (
    <span
      data-testid={`status-badge-${status}`}
      className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-semibold ${s.cls} ${className}`}
    >
      <Icon className="h-3.5 w-3.5" />
      {s.label}
    </span>
  );
}
