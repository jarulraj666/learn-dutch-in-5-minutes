import clsx from "clsx";
import type { TopicStatus } from "@/lib/types";

const MAP: Record<TopicStatus, string> = {
  pending: "bg-yellow-500/20 text-yellow-300 border border-yellow-500/30",
  generated: "bg-blue-500/20 text-blue-300 border border-blue-500/30",
  done: "bg-green-500/20 text-green-300 border border-green-500/30",
};

export function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={clsx(
        "inline-block px-2 py-0.5 rounded text-xs font-medium",
        MAP[status as TopicStatus] ?? "bg-gray-700 text-gray-300"
      )}
    >
      {status}
    </span>
  );
}
