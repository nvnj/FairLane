type Decision = "approve" | "deny" | "refer";

const styles: Record<Decision, string> = {
  approve: "bg-green-100 text-green-800 border border-green-200",
  deny: "bg-red-100 text-red-800 border border-red-200",
  refer: "bg-amber-100 text-amber-800 border border-amber-200",
};

const labels: Record<Decision, string> = {
  approve: "APPROVE",
  deny: "DENY",
  refer: "REFER",
};

export function DecisionBadge({ decision }: { decision: Decision }) {
  return (
    <span
      className={`inline-flex items-center px-3 py-1 rounded text-sm font-semibold tracking-wide ${styles[decision]}`}
    >
      {labels[decision]}
    </span>
  );
}
