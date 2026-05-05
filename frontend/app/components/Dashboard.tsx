"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  fetchResult,
  getApiConnectionHint,
  startAnalysis,
  type PlatformId,
  type PollResult,
} from "../lib/api";

type PlatformCard = {
  id: PlatformId;
  label: string;
  hint: string;
  accent: string;
};

const PLATFORMS: PlatformCard[] = [
  {
    id: "telegram",
    label: "Telegram",
    hint: "Посилання на канал і кількість останніх постів (коментарі)",
    accent:
      "from-sky-500/25 to-sky-600/10 border-sky-500/40 hover:border-sky-400",
  },
  {
    id: "twitter",
    label: "Twitter / X",
    hint: "Профілі та пошук",
    accent:
      "from-slate-400/25 to-slate-600/10 border-slate-400/40 hover:border-slate-300",
  },
  {
    id: "reddit",
    label: "Reddit",
    hint: "Сабредити та юзери",
    accent:
      "from-orange-500/25 to-orange-700/10 border-orange-500/40 hover:border-orange-400",
  },
  {
    id: "instagram",
    label: "Instagram",
    hint: "Профілі та контент",
    accent:
      "from-fuchsia-500/25 to-pink-700/10 border-fuchsia-500/40 hover:border-fuchsia-400",
  },
  {
    id: "facebook",
    label: "Facebook",
    hint: "Сторінки та групи",
    accent:
      "from-blue-600/25 to-blue-900/10 border-blue-500/40 hover:border-blue-400",
  },
  {
    id: "news_portal",
    label: "Новинний портал",
    hint: "Пряме посилання на статтю",
    accent:
      "from-emerald-500/25 to-teal-800/10 border-emerald-500/40 hover:border-emerald-400",
  },
];

function accountAgeBandStyles(band: unknown): { card: string; ageLine: string } {
  if (band === "new_account") {
    return {
      card: "border-l-4 border-red-500/85 bg-red-950/30 border-slate-800",
      ageLine: "text-red-300",
    };
  }
  if (band === "young_account") {
    return {
      card: "border-l-4 border-amber-500/80 bg-amber-950/25 border-slate-800",
      ageLine: "text-amber-200",
    };
  }
  if (band === "established") {
    return {
      card: "border-l-4 border-emerald-600/55 bg-emerald-950/20 border-slate-800",
      ageLine: "text-emerald-200/95",
    };
  }
  return {
    card: "border border-slate-800 bg-slate-950/50",
    ageLine: "text-slate-400",
  };
}

function threatBadge(level: unknown): string {
  const s = String(level || "").toLowerCase();
  if (s.includes("not_applicable") || s === "none") return "Не застосовується";
  if (s.includes("high")) return "Високий";
  if (s.includes("medium")) return "Середній";
  if (s.includes("low")) return "Низький";
  return String(level ?? "—");
}

export default function Dashboard() {
  const [selected, setSelected] = useState<PlatformId | null>(null);
  const [target, setTarget] = useState("");
  const [articleUrl, setArticleUrl] = useState("");
  const [messageCount, setMessageCount] = useState(25);
  /** Лише Telegram: скільки останніх постів перевіряти на коментарі (1–50). */
  const [postCount, setPostCount] = useState(10);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);
  const [polling, setPolling] = useState(false);
  const [result, setResult] = useState<PollResult | null>(null);

  const apiHint = useMemo(() => getApiConnectionHint(), []);

  const resetFlow = useCallback(() => {
    setJobId(null);
    setResult(null);
    setError(null);
    setPolling(false);
  }, []);

  useEffect(() => {
    resetFlow();
    setTarget("");
    setArticleUrl("");
    setMessageCount(25);
    setPostCount(10);
  }, [selected, resetFlow]);

  useEffect(() => {
    if (!jobId) return;
    let cancelled = false;
    const maxAttempts = 90;

    setPolling(true);
    setResult(null);

    const run = async () => {
      for (let i = 0; i < maxAttempts; i++) {
        if (cancelled) return;
        try {
          const data = await fetchResult(jobId);
          if (cancelled) return;
          if ("status" in data && data.status === "pending") {
            await new Promise((r) => setTimeout(r, 2000));
            continue;
          }
          setResult(data);
          setPolling(false);
          return;
        } catch (e) {
          if (!cancelled) {
            setPolling(false);
            setError(e instanceof Error ? e.message : "Помилка поллінгу");
          }
          return;
        }
      }
      if (!cancelled) {
        setPolling(false);
        setError(
          "Час очікування вичерпано. Перевірте, що Redis, Kafka, collector та analytics запущені.",
        );
      }
    };

    void run();
    return () => {
      cancelled = true;
    };
  }, [jobId]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      if (!selected) return;
      if (selected === "news_portal") {
        const { job_id } = await startAnalysis({
          platform: "news_portal",
          article_url: articleUrl.trim(),
        });
        setJobId(job_id);
      } else if (selected === "telegram") {
        const { job_id } = await startAnalysis({
          platform: "telegram",
          target: target.trim(),
          post_count: postCount,
        });
        setJobId(job_id);
      } else {
        const { job_id } = await startAnalysis({
          platform: selected,
          target: target.trim(),
          message_count: messageCount,
        });
        setJobId(job_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Запит не вдався");
    } finally {
      setSubmitting(false);
    }
  }

  const completed =
    result &&
    typeof result === "object" &&
    "status" in result &&
    result.status === "completed";

  return (
    <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6 lg:px-8">
      <header className="mb-10 text-center sm:text-left">
        <p className="text-xs font-semibold uppercase tracking-[0.2em] text-sky-400/90">
          Прототип ІС
        </p>
        <h1 className="mt-2 text-3xl font-bold tracking-tight text-white sm:text-4xl">
          Виявлення дезінформації та неавтентичної поведінки
        </h1>
        <p className="mt-3 max-w-2xl text-sm text-slate-400">
          Оберіть джерело, запустіть збір і перегляньте рівень загрози та висновки
          моделей (RF + LLM).
        </p>
        <p className="mt-2 text-xs text-slate-500">
          Зв&apos;язок з API:{" "}
          <code className="rounded bg-slate-900 px-2 py-0.5 text-slate-300">
            {apiHint}
          </code>
        </p>
      </header>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {PLATFORMS.map((p) => {
          const active = selected === p.id;
          return (
            <button
              key={p.id}
              type="button"
              onClick={() => setSelected(p.id)}
              className={`group relative overflow-hidden rounded-2xl border bg-gradient-to-br p-5 text-left shadow-lg transition ${
                p.accent
              } ${active ? "ring-2 ring-sky-400 ring-offset-2 ring-offset-slate-950" : ""}`}
            >
              <span className="text-lg font-semibold text-white">{p.label}</span>
              <p className="mt-1 text-xs text-slate-300/90">{p.hint}</p>
              <span className="mt-4 inline-flex text-[11px] font-medium uppercase tracking-wide text-slate-400 group-hover:text-white">
                {active ? "Обрано" : "Обрати"}
              </span>
            </button>
          );
        })}
      </section>

      {selected && (
        <section className="mt-10 rounded-2xl border border-slate-800 bg-slate-900/60 p-6 shadow-xl backdrop-blur">
          <h2 className="text-lg font-semibold text-white">
            Параметри моніторингу —{" "}
            {PLATFORMS.find((p) => p.id === selected)?.label}
          </h2>

          <form className="mt-6 space-y-5" onSubmit={onSubmit}>
            {selected === "news_portal" ? (
              <div>
                <label
                  htmlFor="article_url"
                  className="block text-sm font-medium text-slate-300"
                >
                  URL статті
                </label>
                <input
                  id="article_url"
                  type="url"
                  required
                  placeholder="https://…"
                  value={articleUrl}
                  onChange={(e) => setArticleUrl(e.target.value)}
                  className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none ring-sky-500/40 placeholder:text-slate-600 focus:border-sky-500 focus:ring-2"
                />
              </div>
            ) : selected === "telegram" ? (
              <>
                <div>
                  <label
                    htmlFor="tg_target"
                    className="block text-sm font-medium text-slate-300"
                  >
                    Посилання на канал або @username
                  </label>
                  <input
                    id="tg_target"
                    type="text"
                    required
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none ring-sky-500/40 placeholder:text-slate-600 focus:border-sky-500 focus:ring-2"
                    placeholder="https://t.me/channel або @channel"
                  />
                </div>
                <div>
                  <label
                    htmlFor="post_count"
                    className="block text-sm font-medium text-slate-300"
                  >
                    Скільки останніх постів перевірити на коментарі (1–50)
                  </label>
                  <input
                    id="post_count"
                    type="number"
                    min={1}
                    max={50}
                    required
                    value={postCount}
                    onChange={(e) =>
                      setPostCount(
                        Math.min(
                          50,
                          Math.max(1, Number.parseInt(e.target.value, 10) || 1),
                        ),
                      )
                    }
                    className="mt-2 w-full max-w-xs rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/30"
                  />
                  <p className="mt-2 text-xs text-slate-500">
                    Бекенд читає коментарі під цими постами (потрібні ключі Telegram у
                    collector).
                  </p>
                </div>
              </>
            ) : (
              <>
                <div>
                  <label
                    htmlFor="target"
                    className="block text-sm font-medium text-slate-300"
                  >
                    Ціль (URL або User ID)
                  </label>
                  <input
                    id="target"
                    type="text"
                    required
                    value={target}
                    onChange={(e) => setTarget(e.target.value)}
                    className="mt-2 w-full rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none ring-sky-500/40 placeholder:text-slate-600 focus:border-sky-500 focus:ring-2"
                    placeholder="@channel або посилання"
                  />
                </div>
                <div>
                  <label
                    htmlFor="msg_count"
                    className="block text-sm font-medium text-slate-300"
                  >
                    Кількість повідомлень для аналізу (10–100)
                  </label>
                  <input
                    id="msg_count"
                    type="number"
                    min={10}
                    max={100}
                    required
                    value={messageCount}
                    onChange={(e) =>
                      setMessageCount(Number.parseInt(e.target.value, 10) || 10)
                    }
                    className="mt-2 w-full max-w-xs rounded-xl border border-slate-700 bg-slate-950/80 px-4 py-3 text-sm text-white outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/30"
                  />
                </div>
              </>
            )}

            {error && (
              <p className="rounded-lg border border-red-500/40 bg-red-950/40 px-4 py-3 text-sm text-red-200">
                {error}
              </p>
            )}

            <div className="flex flex-wrap gap-3">
              <button
                type="submit"
                disabled={submitting}
                className="rounded-xl bg-sky-600 px-6 py-3 text-sm font-semibold text-white shadow-lg shadow-sky-900/40 transition hover:bg-sky-500 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {submitting ? "Надсилання…" : "Розпочати моніторинг"}
              </button>
              <button
                type="button"
                onClick={() => {
                  setSelected(null);
                  resetFlow();
                }}
                className="rounded-xl border border-slate-600 px-5 py-3 text-sm font-medium text-slate-300 hover:border-slate-500 hover:text-white"
              >
                Скасувати
              </button>
            </div>
          </form>
        </section>
      )}

      {(jobId || polling || result) && (
        <section className="mt-10 rounded-2xl border border-slate-800 bg-slate-900/50 p-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold text-white">
              Результати аналізу
            </h2>
            {jobId && (
              <span className="font-mono text-xs text-slate-500">
                job_id: {jobId}
              </span>
            )}
          </div>

          {polling && (
            <p className="mt-4 flex items-center gap-2 text-sm text-slate-400">
              <span className="inline-block h-4 w-4 animate-spin rounded-full border-2 border-sky-400 border-t-transparent" />
              Очікування обробки (Kafka → collector → analytics)…
            </p>
          )}

          {completed && result && typeof result === "object" && (
            <div className="mt-6 space-y-6">
              {Boolean(
                "configuration_error" in result &&
                  (result as { configuration_error?: boolean })
                    .configuration_error,
              ) ? (
                <div className="rounded-xl border border-amber-500/50 bg-amber-950/40 px-4 py-3 text-sm text-amber-100">
                  <strong>Налаштування Telegram.</strong> Створіть файл{" "}
                  <code className="rounded bg-slate-900 px-1.5 py-0.5 text-amber-50">
                    .env
                  </code>{" "}
                  з <code className="rounded bg-slate-900 px-1.5">.env.example</code>
                  , додайте <code>TELEGRAM_API_ID</code>,{" "}
                  <code>TELEGRAM_API_HASH</code>, <code>TELEGRAM_SESSION_STRING</code>{" "}
                  і перезапустіть <code>collector</code> (
                  <code>docker compose up -d --build collector</code>).
                </div>
              ) : null}
              <div className="rounded-xl border border-slate-700 bg-slate-950/60 px-5 py-4">
                <p className="text-xs uppercase tracking-wide text-slate-500">
                  Рівень загрози (Threat Level)
                </p>
                <p className="mt-1 text-2xl font-bold text-sky-300">
                  {threatBadge(
                    "threat_level" in result ? result.threat_level : "",
                  )}
                  <span className="ml-2 text-sm font-normal text-slate-500">
                    (
                    {String(
                      "threat_level" in result ? result.threat_level : "",
                    )}
                    )
                  </span>
                </p>
              </div>

              {"users" in result && Array.isArray(result.users) && (
                <div>
                  <p className="mb-3 text-sm font-medium text-slate-300">
                    Користувачі / записи
                  </p>
                  <ul className="space-y-3">
                    {(result.users as Record<string, unknown>[]).map((u, i) => (
                      <li
                        key={i}
                        className={`flex flex-wrap items-start gap-3 rounded-xl px-4 py-3 ${accountAgeBandStyles(u.account_age_band).card}`}
                      >
                        <span className="text-xl leading-none">
                          {String(u.emoji ?? "⚪")}
                        </span>
                        <div className="min-w-0 flex-1">
                          {"telegram_user_id" in u ||
                          ("telegram_tag" in u && u.telegram_tag != null) ? (
                            <>
                              {u.telegram_tag != null &&
                              String(u.telegram_tag) !== "" ? (
                                <p className="font-medium text-sky-200">
                                  Тег TG:{" "}
                                  <span className="text-white">
                                    {String(u.telegram_tag)}
                                  </span>
                                </p>
                              ) : (
                                <p className="text-sm text-amber-200/90">
                                  Публічного тегу (@username) немає
                                  {u.telegram_user_id != null && (
                                    <>
                                      {" "}
                                      · numeric id:{" "}
                                      <code className="text-slate-300">
                                        {String(u.telegram_user_id)}
                                      </code>
                                    </>
                                  )}
                                </p>
                              )}
                              <p className="mt-0.5 text-xs text-slate-500">
                                У даних:{" "}
                                <code className="text-slate-400">
                                  {String(u.user_id ?? "—")}
                                </code>
                              </p>
                            </>
                          ) : (
                            <p className="font-medium text-white">
                              {String(u.user_id ?? "—")}
                            </p>
                          )}
                          {"telegram_display_name" in u &&
                            u.telegram_display_name != null && (
                              <p className="text-xs text-slate-500">
                                Ім&apos;я в профілі:{" "}
                                {String(u.telegram_display_name)}
                              </p>
                            )}
                          {"account_age_days" in u &&
                            u.account_age_days != null && (
                              <p
                                className={`mt-1 text-xs ${accountAgeBandStyles(u.account_age_band).ageLine}`}
                              >
                                Вік акаунта (днів):{" "}
                                <span className="font-semibold">
                                  {Number(u.account_age_days).toLocaleString(
                                    "uk-UA",
                                    {
                                      maximumFractionDigits: 0,
                                    },
                                  )}
                                </span>
                                {u.account_age_band === "new_account" ? (
                                  <span className="ml-1 opacity-90">
                                    (новий акаунт, &lt;10 д)
                                  </span>
                                ) : null}
                                {u.account_age_band === "young_account" ? (
                                  <span className="ml-1 opacity-90">
                                    (10–100 д, підозрілий діапазон)
                                  </span>
                                ) : null}
                                {u.account_age_band === "established" ? (
                                  <span className="ml-1 text-emerald-400/80">
                                    (100+ д)
                                  </span>
                                ) : null}
                                {"tier1_synthetic" in u && u.tier1_synthetic === true ? (
                                  <span className="block text-slate-500">
                                    У MVP оцінка синтетична (детерміновано від id)
                                  </span>
                                ) : null}
                              </p>
                            )}
                          {"verdict_reasons" in u &&
                            Array.isArray(u.verdict_reasons) &&
                            (u.verdict_reasons as unknown[]).length > 0 && (
                              <ul className="mt-2 space-y-1 rounded-lg border border-red-900/50 bg-red-950/40 px-3 py-2 text-xs text-red-200/95">
                                {(u.verdict_reasons as string[]).map((line, j) => (
                                  <li key={j}>• {line}</li>
                                ))}
                              </ul>
                            )}
                          <p className="text-sm text-slate-400">
                            {String(u.verdict ?? "")}
                          </p>
                          {u.preview != null && (
                            <p className="mt-1 line-clamp-3 text-xs text-slate-500">
                              Коментар: {String(u.preview)}
                            </p>
                          )}
                        </div>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {"llm" in result && result.llm != null && (
                <details className="rounded-xl border border-slate-700 bg-slate-950/40 open:shadow-inner">
                  <summary className="cursor-pointer select-none px-5 py-4 text-sm font-medium text-sky-200 hover:text-white">
                    Детальне JSON-пояснення (LLM)
                  </summary>
                  <pre className="max-h-[420px] overflow-auto border-t border-slate-800 p-4 text-xs leading-relaxed text-slate-300">
                    {JSON.stringify(result.llm, null, 2)}
                  </pre>
                </details>
              )}
            </div>
          )}

          {!polling &&
            result &&
            typeof result === "object" &&
            "status" in result &&
            result.status === "pending" && (
              <p className="mt-4 text-sm text-amber-200/90">
                Результат ще не готовий (pending).
              </p>
            )}
        </section>
      )}
    </div>
  );
}
