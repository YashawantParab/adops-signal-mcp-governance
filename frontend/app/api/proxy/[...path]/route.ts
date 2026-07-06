import { NextRequest, NextResponse } from "next/server";

const API_BASE = process.env.API_BASE_URL ?? process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  const target = new URL(path.join("/"), `${API_BASE.replace(/\/$/, "")}/`);
  target.search = request.nextUrl.search;

  const headers = new Headers();
  const authorization = request.headers.get("authorization");
  const requestId = request.headers.get("x-request-id");
  if (authorization) headers.set("authorization", authorization);
  if (requestId) headers.set("x-request-id", requestId);
  if (request.headers.get("content-type")) headers.set("content-type", request.headers.get("content-type")!);

  const body = request.method === "GET" || request.method === "HEAD" ? undefined : await request.text();
  const response = await fetch(target, {
    method: request.method,
    headers,
    body,
    cache: "no-store"
  });

  return new NextResponse(response.body, {
    status: response.status,
    headers: {
      "content-type": response.headers.get("content-type") ?? "application/json",
      ...(response.headers.get("x-request-id") ? { "x-request-id": response.headers.get("x-request-id")! } : {})
    }
  });
}

export const GET = proxy;
export const POST = proxy;
