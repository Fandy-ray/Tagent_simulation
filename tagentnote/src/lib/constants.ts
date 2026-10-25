import { browser, dev } from '$app/environment';
import { env } from '$env/dynamic/public';

export const APP_NAME = 'TAgent';

/**
 * Open WebUI / tagent 后端。
 * 开发默认空字符串，请求走同源 `/api/v1/*`（见 vite proxy -> :8080）。
 * 需要直连时可设 PUBLIC_WEBUI_BASE_URL=http://localhost:8080
 */
export const WEBUI_BASE_URL = browser ? (env.PUBLIC_WEBUI_BASE_URL ?? (dev ? `` : ``)) : ``;

export const WEBUI_API_BASE_URL = `${WEBUI_BASE_URL}/api/v1`;
