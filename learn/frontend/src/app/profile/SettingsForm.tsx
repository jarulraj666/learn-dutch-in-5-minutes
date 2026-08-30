"use client";

import { useState } from "react";
import { callApi } from "@/lib/format";

type Settings = { locale: string; email_opt_in: boolean };

export function SettingsForm({ initial }: { initial: Settings }) {
  const [settings, setSettings] = useState(initial);
  const [state, setState] = useState<"idle" | "saving" | "saved" | "error">("idle");

  async function save() {
    setState("saving");
    try {
      await callApi("me/settings", { method: "PATCH", body: JSON.stringify(settings) });
      setState("saved");
    } catch {
      setState("error");
    }
  }

  return (
    <section className="card p-6">
      <h2 className="font-semibold">Settings</h2>

      <label className="mt-4 flex items-center gap-2 text-sm text-slate-600">
        <input
          type="checkbox"
          checked={settings.email_opt_in}
          onChange={(e) => setSettings((s) => ({ ...s, email_opt_in: e.target.checked }))}
          className="accent-brand-600"
        />
        Email me when new lessons are published
      </label>

      <div className="mt-5 flex items-center gap-3">
        <button onClick={save} disabled={state === "saving"} className="btn-primary px-5 py-2 text-sm">
          {state === "saving" ? "Saving…" : "Save settings"}
        </button>
        {state === "saved" && <span className="text-sm text-emerald-600">Saved</span>}
        {state === "error" && <span className="text-sm text-rose-600">Could not save</span>}
      </div>
    </section>
  );
}
