/**
 * 前端端口上 /opennotebook-api 这条转发放行哪些请求（vite.config.ts 用；单测见 scripts/notebook-proxy.test.mjs）。
 *
 * 只放前端用到的那几种请求（$lib/apis/opennotebook.ts），连查询参数也逐个核对：从前端端口进来的
 * 可能是任何人，不该能读改笔记本服务的设置、模型和密钥，不该能删东西，也不该能往参数里塞别的
 * （笔记本服务有的接口会把排序之类的参数拼进数据库语句）。其余一律不转。
 */

export const NOTEBOOK_PROXY_PREFIX = '/opennotebook-api';

// 笔记本服务的记录编号：表名:随机串，例如 notebook:8m6qkcoq3hyn1uhcgmm1
const RECORD_ID = /^[a-z_]+:[A-Za-z0-9_-]+$/;

type Rule = {
	method: 'GET' | 'POST';
	path: RegExp;
	/** 允许的查询参数和各自的取值；没写的参数一律不放 */
	query?: Record<string, RegExp>;
};

const RULES: Rule[] = [
	{
		method: 'GET',
		path: /^\/api\/notebooks$/,
		query: { archived: /^(true|false)$/, order_by: /^(updated|created|name) (asc|desc)$/ }
	},
	{ method: 'GET', path: /^\/api\/notes$/, query: { notebook_id: RECORD_ID } },
	{
		method: 'GET',
		path: /^\/api\/sources$/,
		query: {
			notebook_id: RECORD_ID,
			limit: /^\d{1,3}$/,
			sort_by: /^(updated|created|title)$/,
			sort_order: /^(asc|desc)$/
		}
	},
	// 单条笔记 / 来源：编号在路径里（前端用 encodeURIComponent，冒号会写成 %3A）
	{ method: 'GET', path: /^\/api\/(notes|sources)\/[a-z_]+(:|%3[Aa])[A-Za-z0-9_-]+$/ },
	{ method: 'POST', path: /^\/api\/(notebooks|notes|search)$/ }
];

export function notebookRouteAllowed(method: string | undefined, url: string | undefined) {
	const raw = url ?? '';
	const rest = raw.startsWith(NOTEBOOK_PROXY_PREFIX)
		? raw.slice(NOTEBOOK_PROXY_PREFIX.length)
		: raw;
	// 上一级目录、反斜杠、片段：转发时会按网址规则规整成别的路径（实测 /api/notes/%2e%2e
	// 到了上游成了 /api/）。下面的格式核对已经挡得住（编号只许字母数字），这里先挡一道，免得以后放宽格式时漏掉
	if (/\.\.|\\|#/.test(rest)) return false;
	const mark = rest.indexOf('?');
	const path = mark < 0 ? rest : rest.slice(0, mark);
	const search = mark < 0 ? '' : rest.slice(mark + 1);
	const rule = RULES.find((item) => item.method === method && item.path.test(path));
	if (!rule) return false;
	if (!search) return true;
	const params = new URLSearchParams(search);
	const seen = new Set<string>();
	for (const [key, value] of params) {
		const pattern = rule.query?.[key];
		// 同一个参数出现两次：上游取哪一个说不准，不放
		if (!pattern || seen.has(key) || !pattern.test(value)) return false;
		seen.add(key);
	}
	return true;
}
