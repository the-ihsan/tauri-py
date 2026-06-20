import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Activity, ExternalLink, Globe, PanelRight } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/ui/confirm-dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from "@/components/ui/sheet";
import {
  Tabs,
  TabsContent,
  TabsList,
  TabsTrigger,
} from "@/components/ui/tabs";
import { useBrowserInstances } from "@/hooks/useBrowserInstances";
import { useRunLog, useRuns } from "@/hooks/useRuns";
import { type BrowserRun } from "@/lib/browser";
import { LogApi, type LogEvent, type LogLine } from "@/lib/log";
import { isActiveRun, isResumableRun, type RunInfo } from "@/lib/runs";
import { getTaskType, taskLabel } from "@/lib/tasks";

function browserUrlFromRun(run: RunInfo): string {
  const profileUrl = run.pause_info?.profile_url;
  if (typeof profileUrl === "string" && profileUrl.trim()) {
    return profileUrl.trim();
  }
  return taskLabel(run.task);
}

function taskBrowserInstances(runs: RunInfo[]): BrowserRun[] {
  return runs.filter(isActiveRun).map((run) => ({
    ok: true,
    run_id: run.id,
    running: true,
    headless: Boolean(run.params.headless ?? true),
    url: browserUrlFromRun(run),
    paused: run.status === "paused",
    crashed: false,
  }));
}

const STATUS_TONE: Record<string, string> = {
  running: "bg-primary",
  paused: "bg-amber-500",
  stopping: "bg-amber-500",
  completed: "bg-emerald-500",
  failed: "bg-destructive",
  stopped: "bg-muted-foreground",
  shutdown: "bg-muted-foreground",
  idle: "bg-muted-foreground",
};

function shortId(runId: string) {
  return runId.slice(0, 8);
}

function formatTime(ts: number) {
  return new Date(ts * 1000).toLocaleTimeString();
}

function InstanceRow({
  instance,
  source,
}: {
  instance: BrowserRun;
  source?: "task" | "registry";
}) {
  return (
    <li className="rounded-md border px-3 py-2 text-sm">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          {source === "task" ? instance.url : shortId(instance.run_id)}
        </span>
        <span className="text-xs text-muted-foreground">
          {instance.headless ? "headless" : "visible"}
          {source === "task" ? " · task" : ""}
        </span>
      </div>
      <p className="mt-1 truncate text-xs text-muted-foreground">
        {source === "task"
          ? shortId(instance.run_id)
          : instance.url || "about:blank"}
      </p>
      <div className="mt-1 flex gap-2 text-xs text-muted-foreground">
        {instance.paused && <span>paused</span>}
        {instance.crashed && <span className="text-destructive">crashed</span>}
      </div>
    </li>
  );
}

function LogRow({ line }: { line: LogLine }) {
  return (
    <div className="font-mono text-xs leading-relaxed">
      <span className="text-muted-foreground">{formatTime(line.ts)}</span>{" "}
      <span className="text-muted-foreground">[{line.source}]</span>{" "}
      <span>{line.message}</span>
    </div>
  );
}

function BrowserRuntimePanel({
  open,
  instances,
  registryInstances,
}: {
  open: boolean;
  instances: BrowserRun[];
  registryInstances: BrowserRun[];
}) {
  const [logs, setLogs] = useState<LogLine[]>([]);
  const logEndRef = useRef<HTMLDivElement>(null);

  const syncLogs = useCallback(async () => {
    try {
      const result = await LogApi.lines();
      if (result.ok) {
        setLogs(result.lines);
      }
    } catch {
      // ignore transient errors
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    void syncLogs();
  }, [open, syncLogs]);

  const instanceSource = new Map<string, "task" | "registry">();
  for (const instance of registryInstances) {
    if (instance.running) {
      instanceSource.set(instance.run_id, "registry");
    }
  }
  for (const instance of instances) {
    if (!instanceSource.has(instance.run_id)) {
      instanceSource.set(instance.run_id, "task");
    }
  }

  useEffect(() => {
    const onLog = (event: LogEvent) => {
      if (event.route !== "log.line" || !open) return;
      setLogs((prev) => [...prev.slice(-499), event.payload]);
    };

    void LogApi.subscribe(onLog);
    return () => LogApi.unsubscribe(onLog);
  }, [open]);

  useEffect(() => {
    if (!open) return;
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs, open]);

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="flex min-h-0 flex-3 flex-col gap-2 px-4 py-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-medium">Browser instances</h3>
          <span className="text-xs text-muted-foreground">
            {instances.length} running
          </span>
        </div>
        <ScrollArea className="min-h-0 flex-1">
          {instances.length === 0 ? (
            <p className="text-sm text-muted-foreground">No browsers running.</p>
          ) : (
            <ul className="flex flex-col gap-2 pr-3">
              {instances.map((instance) => (
                <InstanceRow
                  key={instance.run_id}
                  instance={instance}
                  source={instanceSource.get(instance.run_id)}
                />
              ))}
            </ul>
          )}
        </ScrollArea>
      </div>

      <Separator />

      <div className="flex min-h-0 flex-2 flex-col gap-2 px-4 py-3">
        <h3 className="text-sm font-medium">Logs</h3>
        <ScrollArea className="min-h-0 flex-1 rounded-md border bg-muted/30 p-2">
          <div className="flex flex-col gap-1 pr-3">
            {logs.length === 0 ? (
              <p className="text-xs text-muted-foreground">No log output yet.</p>
            ) : (
              logs.map((line, index) => (
                <LogRow key={`${line.ts}-${index}`} line={line} />
              ))
            )}
            <div ref={logEndRef} />
          </div>
        </ScrollArea>
      </div>
    </div>
  );
}

function RunControls({
  run,
  pending,
  onControl,
  onRestart,
  onRemove,
  onNavigate,
}: {
  run: RunInfo;
  pending: boolean;
  onControl: (action: "pause" | "resume" | "stop") => void;
  onRestart: () => void;
  onRemove: () => void;
  onNavigate: () => void;
}) {
  const taskType = getTaskType(run.task);
  const caps = taskType?.capabilities ?? {
    pause: false,
    resume: false,
    stop: false,
    restart: false,
  };
  const resultsPath = taskType?.resultsPath?.(run.id);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <p className="text-sm font-medium">{taskLabel(run.task)}</p>
          <p className="text-xs text-muted-foreground">
            {shortId(run.id)} · {run.item_count} items · {run.re_run_count}{" "}
            re-runs
          </p>
        </div>
        <span className="text-xs capitalize text-muted-foreground">
          {run.status}
        </span>
      </div>

      {run.error && <p className="text-xs text-destructive">{run.error}</p>}

      <div className="flex flex-wrap gap-1.5">
        {caps.pause && run.status === "running" && (
          <Button
            variant="outline"
            size="xs"
            disabled={pending}
            onClick={() => onControl("pause")}
          >
            Pause
          </Button>
        )}
        {caps.resume && run.status === "paused" && (
          <Button
            variant="outline"
            size="xs"
            disabled={pending}
            onClick={() => onControl("resume")}
          >
            Resume
          </Button>
        )}
        {caps.stop &&
          (run.status === "running" ||
            run.status === "paused" ||
            run.status === "stopping") && (
            <Button
              variant="destructive"
              size="xs"
              disabled={pending}
              onClick={() => onControl("stop")}
            >
              Stop
            </Button>
          )}
        {caps.restart && isResumableRun(run) && (
          <Button
            variant="outline"
            size="xs"
            disabled={pending}
            onClick={onRestart}
          >
            Restart
          </Button>
        )}
        {resultsPath && (
          <Button
            variant="ghost"
            size="xs"
            render={<Link to={resultsPath} />}
            onClick={onNavigate}
          >
            <ExternalLink />
            Results
          </Button>
        )}
        <Button
          variant="ghost"
          size="xs"
          disabled={pending}
          onClick={onRemove}
        >
          Delete
        </Button>
      </div>
    </div>
  );
}

function RunLogPanel({ runId }: { runId: string }) {
  const lines = useRunLog(runId);
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  return (
    <ScrollArea className="min-h-0 flex-1 rounded-md border bg-muted/30 p-2">
      <div className="flex flex-col gap-0.5 pr-3">
        {lines.length === 0 ? (
          <p className="text-xs text-muted-foreground">No log output yet.</p>
        ) : (
          lines.map((line, index) => (
            <div
              key={`${index}-${line.slice(0, 12)}`}
              className="font-mono text-xs leading-relaxed wrap-break-word"
            >
              {line}
            </div>
          ))
        )}
        <div ref={endRef} />
      </div>
    </ScrollArea>
  );
}

function TasksRuntimePanel({
  open,
  onNavigate,
}: {
  open: boolean;
  onNavigate: () => void;
}) {
  const { runs, control, restart, remove, pendingRunId, refresh } = useRuns();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<RunInfo | null>(null);

  useEffect(() => {
    if (open) void refresh();
  }, [open, refresh]);

  useEffect(() => {
    if (runs.length === 0) {
      setSelectedId(null);
      return;
    }
    setSelectedId((current) =>
      current && runs.some((run) => run.id === current)
        ? current
        : runs[0].id,
    );
  }, [runs]);

  const selectedRun = runs.find((run) => run.id === selectedId) ?? null;

  if (runs.length === 0) {
    return (
      <div className="flex flex-1 items-center justify-center p-6">
        <p className="text-sm text-muted-foreground">
          No tasks yet. Start one from a module page.
        </p>
      </div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b px-4 py-3">
        <Tabs
          value={selectedId ?? undefined}
          onValueChange={(value) => setSelectedId(value as string)}
        >
          <ScrollArea>
            <TabsList className="w-max max-w-full">
              {runs.map((run) => (
                <TabsTrigger key={run.id} value={run.id}>
                  <span
                    className={`size-1.5 rounded-full ${
                      STATUS_TONE[run.status] ?? "bg-muted-foreground"
                    }`}
                  />
                  {shortId(run.id)}
                </TabsTrigger>
              ))}
            </TabsList>
          </ScrollArea>
        </Tabs>
      </div>

      {selectedRun && (
        <div className="border-b px-4 py-3">
          <RunControls
            run={selectedRun}
            pending={pendingRunId === selectedRun.id}
            onControl={(action) => void control(selectedRun.id, action)}
            onRestart={() => void restart(selectedRun.id)}
            onRemove={() => setDeleteTarget(selectedRun)}
            onNavigate={onNavigate}
          />
        </div>
      )}

      <div className="flex min-h-0 flex-1 flex-col gap-2 px-4 py-3">
        <h3 className="text-sm font-medium">Log</h3>
        {selectedRun ? (
          <RunLogPanel key={selectedRun.id} runId={selectedRun.id} />
        ) : (
          <p className="text-sm text-muted-foreground">
            Select a run to view its log.
          </p>
        )}
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        onOpenChange={(open) => {
          if (!open) setDeleteTarget(null);
        }}
        title="Delete run?"
        description={
          deleteTarget
            ? `Permanently delete run ${shortId(deleteTarget.id)} and all scraped results? This cannot be undone.`
            : ""
        }
        confirmLabel="Delete"
        destructive
        pending={deleteTarget !== null && pendingRunId === deleteTarget.id}
        onConfirm={async () => {
          if (!deleteTarget) return;
          const deleted = await remove(deleteTarget.id);
          if (deleted) setDeleteTarget(null);
        }}
      />
    </div>
  );
}

export function RuntimeDrawer() {
  const [open, setOpen] = useState(false);
  const [section, setSection] = useState<"browsers" | "tasks">("tasks");
  const { runs } = useRuns();

  const taskBrowsers = taskBrowserInstances(runs);
  const { instances: browserInstances, registryInstances } =
    useBrowserInstances(taskBrowsers);
  const activeTaskCount = runs.filter(isActiveRun).length;
  const badgeCount = browserInstances.length;

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            className="ml-auto cursor-pointer gap-2"
          />
        }
      >
        <PanelRight className="size-4" />
        Runtime
        {badgeCount > 0 && (
          <span className="rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-medium text-primary-foreground">
            {badgeCount}
          </span>
        )}
      </SheetTrigger>
      <SheetContent
        side="right"
        className="flex h-full w-full flex-col gap-0 p-0 sm:max-w-md"
      >
        <SheetHeader className="border-b px-4 py-3">
          <SheetTitle className="flex items-center gap-2">
            <Activity className="size-4" />
            Runtime
          </SheetTitle>
          <SheetDescription>
            Browser instances, sidecar logs, and module task runs.
          </SheetDescription>
        </SheetHeader>

        <Tabs
          value={section}
          onValueChange={(value) => setSection(value as "browsers" | "tasks")}
          className="flex min-h-0 flex-1 flex-col gap-0"
        >
          <div className="border-b px-4 py-3">
            <TabsList className="w-full">
              <TabsTrigger value="browsers" className="flex-1">
                <Globe className="size-3.5" />
                Browsers
                {browserInstances.length > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({browserInstances.length})
                  </span>
                )}
              </TabsTrigger>
              <TabsTrigger value="tasks" className="flex-1">
                <Activity className="size-3.5" />
                Tasks
                {activeTaskCount > 0 && (
                  <span className="text-xs text-muted-foreground">
                    ({activeTaskCount})
                  </span>
                )}
              </TabsTrigger>
            </TabsList>
          </div>

          <TabsContent value="browsers" className="min-h-0 flex-1" keepMounted>
            <BrowserRuntimePanel
              open={open}
              instances={browserInstances}
              registryInstances={registryInstances}
            />
          </TabsContent>

          <TabsContent value="tasks" className="min-h-0 flex-1" keepMounted>
            <TasksRuntimePanel
              open={open}
              onNavigate={() => setOpen(false)}
            />
          </TabsContent>
        </Tabs>
      </SheetContent>
    </Sheet>
  );
}
