export type PlatformId =
  | "telegram"
  | "twitter"
  | "reddit"
  | "instagram"
  | "facebook"
  | "news_portal";

/**
 * У браузері всі запити йдуть на той самий origin під `/backend/*` — їх проксує
 * `app/backend/[...path]/route.ts` на FastAPI (`BACKEND_INTERNAL_URL` у Docker).
 */
export function getApiPrefix(): string {
  if (typeof window !== "undefined") {
    return "/backend";
  }
  return (
    process.env.BACKEND_INTERNAL_URL?.replace(/\/$/, "") ||
    process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ||
    "http://localhost:8000"
  );
}

/** Рядок для підказки в UI (лише клієнт). */
export function getApiConnectionHint(): string {
  if (typeof window !== "undefined") {
    return `${window.location.origin}/backend → FastAPI`;
  }
  return "Проксі Next.js /backend";
}

/** Telegram: останні пости каналу → збір коментарів (не «повідомлення» як у інших мережах). */
export type StartTelegramBody = {
  platform: "telegram";
  target: string;
  post_count: number;
};

export type StartOtherSocialBody = {
  platform: Exclude<PlatformId, "news_portal" | "telegram">;
  target: string;
  message_count: number;
};

export type StartNewsBody = {
  platform: "news_portal";
  article_url: string;
};

function parseErrorBody(text: string): string {
  try {
    const j = JSON.parse(text) as { detail?: unknown };
    if (typeof j.detail === "string") return j.detail;
    if (Array.isArray(j.detail)) {
      return j.detail
        .map((d: { msg?: string }) => d.msg || JSON.stringify(d))
        .join("; ");
    }
    if (j.detail != null) return JSON.stringify(j.detail);
  } catch {
    /* ignore */
  }
  return text;
}

export async function startAnalysis(
  body: StartTelegramBody | StartOtherSocialBody | StartNewsBody,
): Promise<{ job_id: string }> {
  const prefix = getApiPrefix();
  const res = await fetch(`${prefix}/api/v1/analysis/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const text = await res.text();
  if (!res.ok) {
    throw new Error(parseErrorBody(text) || `HTTP ${res.status}`);
  }
  const data = JSON.parse(text) as { job_id: string };
  return data;
}

export type PollResult =
  | { status: "pending"; job_id: string }
  | (Record<string, unknown> & { status?: string });

export async function fetchResult(jobId: string): Promise<PollResult> {
  const prefix = getApiPrefix();
  const res = await fetch(`${prefix}/api/v1/analysis/${jobId}/result`, {
    cache: "no-store",
  });
  if (!res.ok) {
    const t = await res.text();
    throw new Error(parseErrorBody(t) || `HTTP ${res.status}`);
  }
  return (await res.json()) as PollResult;
}
