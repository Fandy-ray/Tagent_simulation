import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

import { NOTEBOOK_PROXY_PREFIX, notebookRouteAllowed } from './notebook-proxy';

// 笔记本服务的口令：和 basic-agent 读的是同几个名字（启动脚本把 .env.runtime 导进了进程环境）
const notebookPassword =
	process.env.OPEN_NOTEBOOK_PASSWORD ||
	process.env.OPEN_NOTEBOOK_TOKEN ||
	process.env.NOTEBOOK_TOKEN ||
	'';

export default defineConfig({
	server: {
		proxy: {
			'/agent-api': {
				// 默认连本机 5001；压测或连别的后端时用 AGENT_API_TARGET 指过去（正式的 basic-agent 照样占着 5001）
				target: process.env.AGENT_API_TARGET || 'http://127.0.0.1:5001',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/agent-api/, ''),
				// 给转发的每个请求盖上这个头（小写键：正好覆盖客户端自己写的同名头，客户端去不掉它）。
				// basic-agent 凭它认出「这是从前端端口进来的」：开了 --lan 时那可能是局域网里的任何人，
				// 所以原样转发给模型的 /v1/raw 不对这类请求开放（见 basic-agent 的 app/api/security.py）。
				headers: { 'x-tagent-via-frontend': '1' }
			},
			[NOTEBOOK_PROXY_PREFIX]: {
				// 只对外开了 5173 的服务器上用：tagentnote/.env 里写 PUBLIC_OPENNOTEBOOK_API_URL=/opennotebook-api，
				// 浏览器就经这里连本机的笔记本服务，不用另开 5055；笔记本服务设了口令时由这里代为带上，口令不进浏览器。
				// 本机开发不写那一项时用不到这条，照旧由 $lib/apis/opennotebook.ts 直连 5055
				target: process.env.OPENNOTEBOOK_API_TARGET || 'http://127.0.0.1:5055',
				changeOrigin: true,
				rewrite: (path) => path.slice(NOTEBOOK_PROXY_PREFIX.length),
				headers: notebookPassword
					? { authorization: `Bearer ${notebookPassword}`, 'x-password': notebookPassword }
					: {},
				// 返回 false 时 Vite 直接回 404、不转发
				bypass: (req) => (notebookRouteAllowed(req.method, req.url) ? undefined : false)
			}
		}
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
