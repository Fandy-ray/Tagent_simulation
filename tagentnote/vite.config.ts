import tailwindcss from '@tailwindcss/vite';
import adapter from '@sveltejs/adapter-auto';
import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	server: {
		proxy: {
			// OpenNoteBook 的 5055 由 $lib/apis/opennotebook.ts 直连，不走代理。
			'/agent-api': {
				// 默认连本机 5001；压测或连别的后端时用 AGENT_API_TARGET 指过去（正式的 basic-agent 照样占着 5001）
				target: process.env.AGENT_API_TARGET || 'http://127.0.0.1:5001',
				changeOrigin: true,
				rewrite: (path) => path.replace(/^\/agent-api/, ''),
				// 给转发的每个请求盖上这个头（小写键：正好覆盖客户端自己写的同名头，客户端去不掉它）。
				// basic-agent 凭它认出「这是从前端端口进来的」：开了 --lan 时那可能是局域网里的任何人，
				// 所以原样转发给模型的 /v1/raw 不对这类请求开放（见 basic-agent 的 app/api/security.py）。
				headers: { 'x-tagent-via-frontend': '1' }
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
