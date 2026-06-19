export type SessionStatus = "idle" | "running" | "error";

export type SessionInfo = {
  id: string;
  platform: string;
  name: string;
  status: SessionStatus;
  active_run_count: number;
  last_checked_at: string | null;
  created_at: string;
  updated_at: string;
  has_storage: boolean;
};

export type SessionLaunchResult = {
  session: SessionInfo;
  run_id: string;
  running: boolean;
  url: string;
};

export type SessionCheckResult = {
  session: SessionInfo;
  ok: boolean;
  logged_in: boolean;
  url: string;
  cookie_count: number;
};

export type StoredCookie = {
  name: string;
  domain: string;
  path: string;
  value: string;
  expires: number | null;
  http_only: boolean;
  secure: boolean;
  same_site: string;
};

export type SessionClosedPayload = {
  session_id: string;
  run_id?: string;
  running?: boolean;
  crashed?: boolean;
};
