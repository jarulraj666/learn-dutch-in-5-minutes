import Link from "next/link";
import { Lock } from "lucide-react";

const CLASSES =
  "inline-flex items-center gap-1 rounded-full bg-brand px-3 py-1 text-xs font-semibold text-white";

/** Small pill flagging premium-only content; links to pricing unless nested inside another link. */
export function PremiumBadge({ label = "Premium", linkToPricing = true }: { label?: string; linkToPricing?: boolean }) {
  if (!linkToPricing) {
    return (
      <span className={CLASSES}>
        <Lock size={12} />
        {label}
      </span>
    );
  }
  return (
    <Link href="/pricing" className={`${CLASSES} transition hover:opacity-90`}>
      <Lock size={12} />
      {label}
    </Link>
  );
}
