import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ArrowLeft } from "lucide-react";

import { Button } from "@/components/ui/button";
import { RunsApi, type RunInfo } from "@/lib/runs";

import { PostsResultsView } from "./PostsResultsView";

export function PostsResultsPage() {
  const { runId } = useParams<{ runId: string }>();
  const [run, setRun] = useState<RunInfo | null>(null);

  useEffect(() => {
    if (!runId) return;
    void RunsApi.get(runId)
      .then(setRun)
      .catch(() => setRun(null));
  }, [runId]);

  if (!runId) {
    return (
      <div className="p-6 text-sm text-muted-foreground">No run selected.</div>
    );
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 p-6">
      <div className="flex items-center gap-3">
        <Button
          variant="ghost"
          size="icon-sm"
          render={<Link to="/platforms/linkedin/posts" />}
        >
          <ArrowLeft />
        </Button>
        <div>
          <h1 className="text-xl font-semibold tracking-tight">
            Scrape results
          </h1>
          <p className="text-sm text-muted-foreground">
            Run {runId.slice(0, 8)}
            {run ? ` · ${run.status} · ${run.item_count} posts` : ""}
          </p>
        </div>
      </div>

      <PostsResultsView runId={runId} />
    </div>
  );
}
