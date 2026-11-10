import { Env } from "./db";
import { handleFactoryApi } from "./factory_api";
import { handleMakeApi } from "./make_api";
import { handleSite } from "./site";
import { scheduled as runScheduled } from "./scheduled";

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    const url = new URL(request.url);
    const path = url.pathname;
    if (path.startsWith("/api/factory/")) {
      return handleFactoryApi(env, request, path);
    }
    if (path.startsWith("/api/make/")) {
      return handleMakeApi(env, request, path);
    }
    if (path === "/privacy" || path === "/terms" || path === "/data-deletion" || path === "/chalisa" || path === "/dashboard" || path === "/") {
      return env.ASSETS.fetch(request);
    }
    if (path === "/status.json" || path === "/mediakit") {
      return handleSite(env, request, path);
    }
    return handleSite(env, request, path);
  },
  async scheduled(event: ScheduledEvent, env: Env, ctx: ExecutionContext): Promise<void> {
    ctx.waitUntil(runScheduled(env, event));
  },
};