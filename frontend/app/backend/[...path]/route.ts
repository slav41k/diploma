import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";

/** У Docker: http://api:8000. Локально: http://127.0.0.1:8000 */
const BACKEND =
  process.env.BACKEND_INTERNAL_URL?.replace(/\/$/, "") ||
  process.env.API_INTERNAL_URL?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

async function proxy(request: NextRequest, pathParts: string[]) {
  const path = pathParts.join("/");
  const target = `${BACKEND}/${path}${request.nextUrl.search}`;

  const headers = new Headers();
  const accept = request.headers.get("accept");
  if (accept) headers.set("Accept", accept);
  const contentType = request.headers.get("content-type");
  if (
    contentType &&
    request.method !== "GET" &&
    request.method !== "HEAD"
  ) {
    headers.set("Content-Type", contentType);
  }

  let body: ArrayBuffer | undefined;
  if (request.method !== "GET" && request.method !== "HEAD") {
    body = await request.arrayBuffer();
  }

  try {
    const res = await fetch(target, {
      method: request.method,
      headers,
      body: body && body.byteLength ? body : undefined,
    });
    const out = new NextResponse(res.body, { status: res.status });
    const ct = res.headers.get("content-type");
    if (ct) out.headers.set("Content-Type", ct);
    return out;
  } catch (e) {
    return NextResponse.json(
      {
        detail: "Помилка з'єднання з FastAPI (перевірте BACKEND_INTERNAL_URL та сервіс api).",
        error: String(e),
      },
      { status: 502 },
    );
  }
}

export async function GET(
  request: NextRequest,
  ctx: { params: { path: string[] } },
) {
  return proxy(request, ctx.params.path);
}

export async function POST(
  request: NextRequest,
  ctx: { params: { path: string[] } },
) {
  return proxy(request, ctx.params.path);
}
