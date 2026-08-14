/**
 * Timezone utilities — all display and input is in Europe/Amsterdam (NL time).
 * Internally everything is stored as UTC ISO strings.
 */

export const NL_TZ = "Europe/Amsterdam";

/**
 * Format any date/timestamp for display in Netherlands time.
 * Returns e.g. "14-8-2026 16:36"
 */
export function formatNL(
  value: string | Date | null | undefined,
  opts: Intl.DateTimeFormatOptions = { dateStyle: "short", timeStyle: "short" },
): string {
  if (!value) return "—";
  try {
    return new Date(value).toLocaleString("nl-NL", { timeZone: NL_TZ, ...opts });
  } catch {
    return String(value);
  }
}

/**
 * Convert a datetime-local input string (treated as Netherlands time) to a UTC ISO string.
 *
 * datetime-local gives "YYYY-MM-DDTHH:MM" without timezone info.
 * We interpret this as Europe/Amsterdam and return the correct UTC equivalent,
 * handling DST automatically (UTC+1 in winter, UTC+2 in summer).
 */
export function nlInputToUtcIso(dtLocalStr: string): string {
  if (!dtLocalStr) return "";

  // Normalise to "YYYY-MM-DDTHH:MM:SS"
  const s = dtLocalStr.length === 16 ? dtLocalStr + ":00" : dtLocalStr;
  const [datePart, timePart] = s.split("T");
  const [y, mo, d] = datePart.split("-").map(Number);
  const [h, m, sec = 0] = timePart.split(":").map(Number);

  // Start with an estimate: treat the input as UTC and see what NL time that gives.
  const utcGuess = Date.UTC(y, mo - 1, d, h, m, sec);

  const nlStr = new Date(utcGuess).toLocaleString("en-US", {
    timeZone: NL_TZ,
    hour12: false,
    year: "numeric", month: "2-digit", day: "2-digit",
    hour: "2-digit", minute: "2-digit",
  });

  // Parse the NL representation of our guess
  const match = nlStr.match(/(\d+)\/(\d+)\/(\d+),\s*(\d+):(\d+)/);
  if (match) {
    const nlH = parseInt(match[4]) % 24; // guard against "24:00"
    const nlM = parseInt(match[5]);
    // Shift UTC guess so NL shows the desired time
    const diffMs = ((h - nlH) * 60 + (m - nlM)) * 60000;
    return new Date(utcGuess + diffMs).toISOString();
  }

  // Fallback: just treat as UTC (shouldn't happen)
  return new Date(utcGuess).toISOString();
}

/**
 * Returns the current time as a datetime-local string in Netherlands time.
 * Useful for pre-filling date inputs.
 */
export function nowNLInput(): string {
  const now = new Date();
  const nlStr = now.toLocaleString("sv-SE", { timeZone: NL_TZ }); // "YYYY-MM-DD HH:MM:SS"
  return nlStr.slice(0, 16).replace(" ", "T");
}
