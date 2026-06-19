import { useCallback, useEffect, useState } from "react";
import { CheckIcon, CopyIcon, ExternalLinkIcon } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useRunItems } from "@/hooks/useRuns";
import { RunsApi, type RunInput } from "@/lib/runs";

import type { LinkedInMedia, LinkedInPost } from "../types";

function asPost(item: { data: Record<string, unknown> }): LinkedInPost {
  return item.data as unknown as LinkedInPost;
}

function inputLabel(input: RunInput): string {
  const data = input.data as { profile_url?: string };
  return data.profile_url || `Input #${input.ordinal + 1}`;
}

function countNumber(value: number | null): string {
  return value == null ? "-" : String(value);
}

function formatPostForCopy(post: LinkedInPost): string {
  const lines = [post.text?.trim() || ""];
  if (post.post_url) lines.push("", post.post_url);
  return lines.join("\n").trim();
}

function PostMediaItem({ media }: { media: LinkedInMedia }) {
  if (media.kind === "video") {
    return (
      <video
        src={media.url}
        poster={media.poster}
        controls
        preload="metadata"
        className="max-h-96 w-full rounded-md bg-black"
      />
    );
  }

  if (media.kind === "document") {
    return (
      <a
        href={media.url}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 rounded-md border px-3 py-2 text-sm text-primary underline-offset-4 hover:underline"
      >
        <ExternalLinkIcon className="size-3.5 shrink-0" />
        {media.label || "Open document"}
      </a>
    );
  }

  return (
    <img
      src={media.url}
      alt={media.label || "Post media"}
      loading="lazy"
      className="max-h-96 w-full rounded-md object-contain bg-muted/30"
    />
  );
}

function CopyPostButton({
  post,
  size = "xs",
  showLabel = true,
}: {
  post: LinkedInPost;
  size?: "xs" | "sm" | "icon-xs";
  showLabel?: boolean;
}) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    await navigator.clipboard.writeText(formatPostForCopy(post));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  return (
    <Button
      variant="ghost"
      size={size}
      onClick={() => void copy()}
      title="Copy post text and link"
    >
      {copied ? <CheckIcon /> : <CopyIcon />}
      {showLabel ? (copied ? "Copied" : "Copy") : null}
    </Button>
  );
}

function PostDetailDialog({
  post,
  open,
  onOpenChange,
}: {
  post: LinkedInPost | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  if (!post) return null;

  const media = post.media_urls ?? [];

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="flex max-h-[85vh] w-[calc(100%-2rem)] max-w-3xl flex-col overflow-hidden p-0">
        <DialogHeader className="shrink-0 border-b px-6 py-4 pr-14">
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 space-y-1">
              <DialogTitle className="truncate">
                {post.author_name || "Post"}
              </DialogTitle>
              <DialogDescription className="truncate">
                {post.posted_at || post.post_url || "LinkedIn post"}
              </DialogDescription>
            </div>
            <CopyPostButton post={post} size="sm" />
          </div>
        </DialogHeader>

        <div className="min-h-0 min-w-0 flex-1 overflow-y-auto">
          <div className="space-y-4 px-6 py-4">
            <p className="whitespace-pre-wrap text-sm leading-relaxed">
              {post.text || "(no text)"}
            </p>

            {media.length > 0 ? (
              <div className="space-y-3">
                <p className="text-xs font-medium text-muted-foreground">
                  Media ({media.length})
                </p>
                <div className="space-y-3">
                  {media.map((item, index) => (
                    <div key={`${item.url}-${index}`} className="space-y-1">
                      <p className="text-xs capitalize text-muted-foreground">
                        {item.kind}
                        {item.label ? ` · ${item.label}` : ""}
                      </p>
                      <PostMediaItem media={item} />
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">No media attached.</p>
            )}

            <div className="flex flex-wrap gap-4 border-t pt-3 text-xs text-muted-foreground">
              <span>Likes: {countNumber(post.like_count)}</span>
              <span>Comments: {countNumber(post.comment_count)}</span>
              <span>Reposts: {countNumber(post.repost_count)}</span>
              {post.post_url ? (
                <a
                  href={post.post_url}
                  target="_blank"
                  rel="noreferrer"
                  className="inline-flex items-center gap-1 text-primary underline-offset-4 hover:underline"
                >
                  Open on LinkedIn
                  <ExternalLinkIcon className="size-3" />
                </a>
              ) : null}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

export function PostsResultsView({ runId }: { runId: string }) {
  const [inputs, setInputs] = useState<RunInput[]>([]);
  const [selectedInputId, setSelectedInputId] = useState<string | null>(null);
  const [inputsLoading, setInputsLoading] = useState(false);
  const [inputsError, setInputsError] = useState<string | null>(null);
  const [viewPost, setViewPost] = useState<LinkedInPost | null>(null);
  const {
    items,
    loading: itemsLoading,
    error: itemsError,
    refresh: refreshItems,
  } = useRunItems(runId, selectedInputId);

  const loadInputs = useCallback(async () => {
    setInputsLoading(true);
    setInputsError(null);
    try {
      setInputs(await RunsApi.inputs(runId));
    } catch (err) {
      setInputsError(err instanceof Error ? err.message : String(err));
    } finally {
      setInputsLoading(false);
    }
  }, [runId]);

  useEffect(() => {
    void loadInputs();
  }, [loadInputs]);

  const refresh = () => {
    void loadInputs();
    void refreshItems();
  };

  const error = inputsError ?? itemsError;

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">Inputs ({inputs.length})</h3>
        <Button variant="outline" size="sm" onClick={refresh}>
          Refresh
        </Button>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <div className="rounded-lg border">
        <table className="w-full text-sm">
          <thead className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
            <tr>
              <th className="px-3 py-2 font-medium">#</th>
              <th className="px-3 py-2 font-medium">Profile</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">Filter</th>
            </tr>
          </thead>
          <tbody>
            <tr
              className={
                selectedInputId === null
                  ? "bg-primary/10"
                  : "hover:bg-muted/40"
              }
            >
              <td className="px-3 py-2 text-muted-foreground" colSpan={3}>
                All inputs
              </td>
              <td className="px-3 py-2 text-right">
                <Button
                  variant={selectedInputId === null ? "secondary" : "ghost"}
                  size="xs"
                  onClick={() => setSelectedInputId(null)}
                >
                  All
                </Button>
              </td>
            </tr>
            {inputs.map((input) => (
              <tr
                key={input.id}
                className={
                  selectedInputId === input.id
                    ? "border-t bg-primary/10"
                    : "border-t hover:bg-muted/40"
                }
              >
                <td className="px-3 py-2 text-muted-foreground">
                  {input.ordinal + 1}
                </td>
                <td className="max-w-0 truncate px-3 py-2" title={inputLabel(input)}>
                  {inputLabel(input)}
                </td>
                <td className="px-3 py-2 capitalize text-muted-foreground">
                  {input.status}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant={
                      selectedInputId === input.id ? "secondary" : "ghost"
                    }
                    size="xs"
                    onClick={() => setSelectedInputId(input.id)}
                  >
                    Select
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between">
        <h3 className="text-sm font-medium">
          Posts ({items.length}
          {itemsLoading || inputsLoading ? ", loading…" : ""})
        </h3>
      </div>

      <ScrollArea className="min-h-0 flex-1 rounded-lg border">
        {items.length === 0 ? (
          <p className="p-4 text-sm text-muted-foreground">
            {itemsLoading ? "Loading results…" : "No posts scraped yet."}
          </p>
        ) : (
          <table className="w-full text-sm">
            <thead className="sticky top-0 border-b bg-muted/60 text-left text-xs text-muted-foreground">
              <tr>
                <th className="px-3 py-2 font-medium">#</th>
                <th className="px-3 py-2 font-medium">Author</th>
                <th className="px-3 py-2 font-medium">Post</th>
                <th className="px-3 py-2 font-medium">Likes</th>
                <th className="px-3 py-2 font-medium">Comments</th>
                <th className="px-3 py-2 font-medium">View</th>
                <th className="px-3 py-2 font-medium">Copy</th>
                <th className="px-3 py-2 font-medium">Link</th>
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const post = asPost(item);
                const mediaCount = post.media_urls?.length ?? 0;
                return (
                  <tr key={item.id} className="border-t align-top">
                    <td className="px-3 py-2 text-muted-foreground">
                      {item.ordinal}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {post.author_name || "-"}
                    </td>
                    <td className="max-w-md px-3 py-2">
                      <p className="line-clamp-3 whitespace-pre-wrap text-muted-foreground">
                        {post.text || "(no text)"}
                      </p>
                    </td>
                    <td className="px-3 py-2">{countNumber(post.like_count)}</td>
                    <td className="px-3 py-2">
                      {countNumber(post.comment_count)}
                    </td>
                    <td className="px-3 py-2">
                      <Button
                        variant="outline"
                        size="xs"
                        onClick={() => setViewPost(post)}
                      >
                        View{mediaCount > 0 ? ` (${mediaCount})` : ""}
                      </Button>
                    </td>
                    <td className="px-3 py-2">
                      <CopyPostButton post={post} size="icon-xs" showLabel={false} />
                    </td>
                    <td className="px-3 py-2">
                      {post.post_url ? (
                        <a
                          href={post.post_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-primary underline-offset-4 hover:underline"
                        >
                          Open
                        </a>
                      ) : (
                        "-"
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </ScrollArea>

      <PostDetailDialog
        post={viewPost}
        open={viewPost != null}
        onOpenChange={(open) => {
          if (!open) setViewPost(null);
        }}
      />
    </div>
  );
}
