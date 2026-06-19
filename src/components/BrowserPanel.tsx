import { useCallback, useEffect, useState } from "react";
import { Globe } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { BrowserApi, type BrowserEvent, type BrowserRun } from "@/lib/browser";

function shortId(runId: string) {
  return runId.slice(0, 8);
}

function isBrowserRun(value: unknown): value is BrowserRun {
  return (
    typeof value === "object" &&
    value !== null &&
    "run_id" in value &&
    typeof (value as BrowserRun).run_id === "string"
  );
}

function normalizeInstances(result: unknown): BrowserRun[] {
  if (
    typeof result === "object" &&
    result !== null &&
    "instances" in result &&
    Array.isArray((result as { instances: unknown }).instances)
  ) {
    return (result as { instances: BrowserRun[] }).instances;
  }
  if (isBrowserRun(result)) {
    return result.running ? [result] : [];
  }
  return [];
}

export function BrowserPanel() {
  const [headless, setHeadless] = useState(false);
  const [instances, setInstances] = useState<BrowserRun[]>([]);
  const [pending, setPending] = useState<"launch" | "stop" | null>(null);
  const [error, setError] = useState<string | null>(null);

  const syncStatus = useCallback(async () => {
    try {
      const result = await BrowserApi.status();
      setInstances(normalizeInstances(result));
    } catch {
      // ignore transient poll errors
    }
  }, []);

  useEffect(() => {
    syncStatus();
  }, [syncStatus]);

  useEffect(() => {
    const onEvent = (event: BrowserEvent) => {
      if (event.route === "browser.closed") {
        setInstances((prev) => prev.filter((i) => i.run_id !== event.payload.run_id));
        return;
      }
      if (event.route === "browser.updated") {
        const next = event.payload;
        if (!next.running) {
          setInstances((prev) => prev.filter((i) => i.run_id !== next.run_id));
          return;
        }
        setInstances((prev) => [
          ...prev.filter((i) => i.run_id !== next.run_id),
          next,
        ]);
      }
    };

    void BrowserApi.subscribe(onEvent);
    return () => BrowserApi.unsubscribe(onEvent);
  }, []);

  useEffect(() => {
    if (instances.length === 0) return;
    const interval = window.setInterval(syncStatus, 2000);
    return () => window.clearInterval(interval);
  }, [instances.length, syncStatus]);

  const busy = pending !== null;
  const runningCount = instances.filter((i) => i.running).length;

  const handleLaunch = async () => {
    setPending("launch");
    setError(null);
    try {
      const run = await BrowserApi.launch(headless);
      setInstances((prev) => [...prev.filter((i) => i.run_id !== run.run_id), run]);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to launch browser");
    } finally {
      setPending(null);
    }
  };

  const handleStop = async (runId: string) => {
    setPending("stop");
    setError(null);
    try {
      await BrowserApi.stop(runId);
      setInstances((prev) => prev.filter((i) => i.run_id !== runId));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to stop browser");
    } finally {
      setPending(null);
    }
  };

  const handleControl = async (runId: string, action: "pause" | "resume") => {
    setError(null);
    try {
      const updated = await BrowserApi.control(runId, action);
      setInstances((prev) =>
        prev.map((i) => (i.run_id === runId ? updated : i)),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : `Failed to ${action} browser`);
    }
  };

  return (
    <section className="flex max-w-2xl flex-col gap-4 rounded-lg border bg-card p-6">
      <div className="flex items-start gap-3">
        <Globe className="mt-0.5 size-5 text-muted-foreground" />
        <div className="flex flex-col gap-1">
          <h2 className="text-lg font-semibold tracking-tight">Browser</h2>
          <p className="text-sm text-muted-foreground">
            Launch Playwright Chromium instances for automation. Each instance gets a unique run id.
          </p>
        </div>
      </div>

      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        {busy && <Spinner className="size-4" />}
        <p>
          {pending === "launch"
            ? "Launching browser…"
            : pending === "stop"
              ? "Stopping browser…"
              : runningCount > 0
                ? `${runningCount} instance${runningCount === 1 ? "" : "s"} running`
                : "No browser instances running"}
        </p>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={headless}
          disabled={busy}
          onChange={(e) => setHeadless(e.target.checked)}
          className="size-4 rounded border"
        />
        Headless
      </label>

      <Button type="button" disabled={busy} onClick={handleLaunch}>
        {pending === "launch" ? (
          <>
            <Spinner className="size-4" />
            Launching…
          </>
        ) : (
          "Launch browser"
        )}
      </Button>

      {instances.length > 0 && (
        <ul className="flex flex-col gap-2">
          {instances.map((instance) => (
            <li
              key={instance.run_id}
              className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
            >
              <div className="flex flex-col gap-0.5">
                <span className="font-medium">{shortId(instance.run_id)}</span>
                <span className="text-xs text-muted-foreground">
                  {instance.headless ? "headless" : "visible"}
                  {instance.paused ? " · paused" : ""}
                  {instance.crashed ? " · crashed" : ""}
                  {instance.url ? ` · ${instance.url}` : ""}
                </span>
              </div>
              <div className="flex gap-2">
                {instance.running && !instance.paused && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => handleControl(instance.run_id, "pause")}
                  >
                    Pause
                  </Button>
                )}
                {instance.running && instance.paused && (
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => handleControl(instance.run_id, "resume")}
                  >
                    Resume
                  </Button>
                )}
                <Button
                  type="button"
                  variant="destructive"
                  size="sm"
                  disabled={busy}
                  onClick={() => handleStop(instance.run_id)}
                >
                  Stop
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {error && <p className="text-sm text-destructive">{error}</p>}
    </section>
  );
}
