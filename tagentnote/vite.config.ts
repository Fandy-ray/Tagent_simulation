import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig, type ProxyOptions } from 'vite';
import { timingSafeEqual } from 'node:crypto';
import { isIP } from 'node:net';

import { NOTEBOOK_PROXY_PREFIX, notebookRouteAllowed } from './notebook-proxy.ts';

// 笔记本服务的口令：和 basic-agent 读的是同几个名字（启动脚本把 .env.runtime 导进了进程环境）
const notebookPassword =
	process.env.OPEN_NOTEBOOK_PASSWORD ||
	process.env.OPEN_NOTEBOOK_TOKEN ||
	process.env.NOTEBOOK_TOKEN ||
	'';
const agentTarget = process.env.AGENT_API_TARGET || 'http://127.0.0.1:5001';
let cachedIdentityMode: { enabled: boolean; until: number } | null = null;

async function identityEnabled(): Promise<boolean> {
	if (cachedIdentityMode && Date.now() < cachedIdentityMode.until)
		return cachedIdentityMode.enabled;
	let enabled = true; // 连不上后端时不把共享笔记本口令暴露出去。
	try {
		const response = await fetch(new URL('/auth/status', agentTarget), {
			signal: AbortSignal.timeout(3000)
		});
		if (response.status === 404)
			enabled = false; // 旧匿名后端没有此接口。
		else if (response.ok)
			enabled = ((await response.json()) as { enabled?: boolean }).enabled !== false;
	} catch {
		// 保持 fail closed。
	}
	cachedIdentityMode = enabled ? { enabled, until: Date.now() + 5000 } : null;
	return enabled;
}

const equalToken = (a: string, b: string): boolean => {
	const left = Buffer.from(a);
	const right = Buffer.from(b);
	return left.length === right.length && timingSafeEqual(left, right);
};

function clientIp(request: import('node:http').IncomingMessage): string {
	const socket = request.socket.remoteAddress || '';
	const normalized = socket.startsWith('::ffff:') ? socket.slice(7) : socket;
	// HTTPS 反向代理必须覆盖 X-Real-IP；仅当实际连接来自本机代理时才信此头。
	const forwarded = request.headers['x-real-ip'];
	if (
		(normalized === '127.0.0.1' || normalized === '::1') &&
		typeof forwarded === 'string' &&
		isIP(forwarded)
	)
		return forwarded;
	return socket || 'unknown';
}

async function notebookCallerAllowed(
	request: import('node:http').IncomingMessage
): Promise<boolean> {
	if (!(await identityEnabled())) return true;
	const cookie = request.headers.cookie;
	if (!cookie) return false;
	try {
		const response = await fetch(new URL('/auth/me', agentTarget), {
			headers: { cookie, 'x-tagent-via-frontend': '1' },
			signal: AbortSignal.timeout(3000)
		});
		if (!response.ok) return false;
		const session = (await response.json()) as { user?: { role?: string }; csrf?: string };
		const path = new URL(request.url || '/', 'http://localhost').pathname.slice(
			NOTEBOOK_PROXY_PREFIX.length
		);
		if (request.method === 'GET' || request.method === 'HEAD') return true;
		const origin = request.headers.origin;
		const csrf = request.headers['x-tagent-csrf'];
		if (
			!origin ||
			origin !== process.env.TAGENT_PUBLIC_ORIGIN ||
			typeof csrf !== 'string' ||
			!session.csrf ||
			!equalToken(csrf, session.csrf)
		)
			return false;
		return path === '/api/search' || session.user?.role === 'admin';
	} catch {
		return false;
	}
}

const agentProxy = (): ProxyOptions => ({
	target: agentTarget,
	changeOrigin: true,
	rewrite: (path) => path.replace(/^\/agent-api/, ''),
	headers: { 'x-tagent-via-frontend': '1' },
	configure(proxy) {
		proxy.on('proxyReq', (proxyReq, request) => {
			// 只信 Vite 实际接入的 socket 地址，覆盖浏览器自带的同名头。
			proxyReq.setHeader('x-tagent-client-ip', clientIp(request));
		});
	}
});

const notebookProxy = (): ProxyOptions => ({
	target: process.env.OPENNOTEBOOK_API_TARGET || 'http://127.0.0.1:5055',
	changeOrigin: true,
	rewrite: (path) => path.slice(NOTEBOOK_PROXY_PREFIX.length),
	headers: notebookPassword
		? { authorization: `Bearer ${notebookPassword}`, 'x-password': notebookPassword }
		: {},
	bypass: async (req) =>
		notebookRouteAllowed(req.method, req.url) && (await notebookCallerAllowed(req))
			? undefined
			: false
});

export default defineConfig({
	server: {
		proxy: {
			'/agent-api': agentProxy(),
			[NOTEBOOK_PROXY_PREFIX]: notebookProxy()
		}
	},
	preview: {
		proxy: { '/agent-api': agentProxy(), [NOTEBOOK_PROXY_PREFIX]: notebookProxy() }
	},
	plugins: [
		tailwindcss(),
		sveltekit({
			compilerOptions: {
				// Force runes mode for the project, except for libraries. Can be removed in svelte 6.
				runes: ({ filename }) =>
					filename.split(/[/\\]/).includes('node_modules') ? undefined : true
			},

			// adapter-auto only supports some environments, see https://svelte.dev/docs/kit/adapter-auto for a list.
			// If your environment is not supported, or you settled on a specific environment, switch out the adapter.
			// See https://svelte.dev/docs/kit/adapters for more information about adapters.
			adapter: adapter()
		})
	]
});
