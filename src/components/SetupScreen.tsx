import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { Spinner } from "@/components/ui/spinner";
import { BrowserApi, type BrowserInstallProgress } from "@/lib/browser";

type SetupScreenProps = {
  onReady: () => void;
};

export function SetupScreen({ onReady }: SetupScreenProps) {
  const [installing, setInstalling] = useState(false);
  const [progress, setProgress] = useState<BrowserInstallProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!installing) {
      return;
    }

    const onProgress = (event: BrowserInstallProgress) => {
      setProgress(event);
    };

    void BrowserApi.subscribeInstallProgress(onProgress);

    return () => {
      BrowserApi.unsubscribeInstallProgress(onProgress);
    };
  }, [installing]);

  const handleInstall = async () => {
    setInstalling(true);
    setProgress({ message: "Preparing Chromium install…", percent: 0 });
    setError(null);
    try {
      const result = await BrowserApi.installRun();
      if (result.installed) {
        onReady();
        return;
      }
      setError(result.error ?? "Chromium install failed");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Chromium install failed");
    } finally {
      setInstalling(false);
      setProgress(null);
    }
  };

  const percent = progress?.percent;

  return (
    <main className="flex min-h-svh flex-col items-center justify-center gap-6 p-8">
      <div className="flex max-w-md flex-col items-center gap-3 text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Set up Chromium</h1>
        <p className="text-sm text-muted-foreground">
          Playwright needs a local Chromium browser before you can launch automation
          sessions. This one-time download is tailored to your operating system.
        </p>
      </div>

      <Button type="button" disabled={installing} onClick={handleInstall}>
        {installing ? (
          <>
            <Spinner className="size-4" />
            Installing Chromium…
          </>
        ) : (
          "Install Chromium"
        )}
      </Button>

      {installing && progress && (
        <div className="flex w-full max-w-md flex-col gap-2">
          {percent != null && (
            <div className="flex items-center gap-3">
              <div className="h-2 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                <div
                  className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out"
                  style={{ width: `${percent}%` }}
                />
              </div>
              <span className="w-10 shrink-0 text-right text-sm tabular-nums text-muted-foreground">
                {percent}%
              </span>
            </div>
          )}
          <p className="text-center text-sm text-muted-foreground">{progress.message}</p>
        </div>
      )}

      {error && (
        <p className="max-w-md text-center text-sm text-destructive">{error}</p>
      )}
    </main>
  );
}
