/**
 * 模型登记（basic-agent 的 /admin/model-providers）。
 *
 * 要管理口令（TAgent重写版/.env.runtime 里的 AGENT_ADMIN_TOKEN，启动脚本会自动生成）。
 * 口令由调用方传进来、随请求头发出去，这里不存（记住口令见 $lib/apis/admin）。
 */
import { agentBase } from '$lib/apis/agent';

export type ModelProvider = {
	name: string;
	served_model_id: string;
	base_url: string;
	upstream_model: string;
	auth_mode: 'bearer' | 'none';
	temperature: number;
	enabled: boolean;
	created_at: string;
	updated_at: string;
	extra_body: Record<string, unknown>;
	/** 只有出题、批改带的厂商参数，答疑不带 */
	structured_extra_body: Record<string, unknown>;
	api_key_masked: string;
	has_api_key: boolean;
};

export type ModelRegistry = {
	version: number;
	default_model_id: string;
	providers: ModelProvider[];
};

export type ModelProviderInput = {
	name: string;
	served_model_id: string;
	base_url: string;
	upstream_model: string;
	auth_mode: 'bearer' | 'none';
	/** 修改时留空 = 沿用原来的 Key */
	api_key: string;
	temperature: number;
	enabled: boolean;
	extra_body: Record<string, unknown>;
	structured_extra_body: Record<string, unknown>;
};

/** 后端校验的英文报错 → 中文。没对上的原样附在后面，免得把真正的原因藏起来。 */
const VALIDATION_HINTS: [string, string][] = [
	['api_key is required', '要填 API Key'],
	['base_url must', '接口地址要以 http:// 或 https:// 开头，且不能带用户名密码'],
	['served_model_id contains', '模型 ID 只能用英文字母、数字和 . _ : -，最长 128 个字符'],
	['already exists', '这个模型 ID 已经登记过了，换一个，或者去改原来那条'],
	[
		'extra_body must not set',
		'附加参数不能改 model、messages、max_tokens、temperature、stream 等由系统决定的字段'
	],
	['extra_body must be at most', '附加参数太长了（JSON 不能超过 2000 个字符）'],
	['extra_body', '附加参数要写成一个 JSON 对象，例如 {"thinking": {"type": "disabled"}}'],
	['temperature', '温度要在 0 到 2 之间'],
	['name is required', '要填名称'],
	['upstream_model is required', '要填上游模型名']
];

export class ModelAdminError extends Error {
	constructor(
		message: string,
		readonly status: number
	) {
		super(message);
		this.name = 'ModelAdminError';
	}
}

function explain(status: number, payload: unknown): string {
	const error = (payload as { error?: { message?: string; code?: string } })?.error;
	const code = error?.code ?? '';
	const message = error?.message ?? '';

	if (code === 'admin_token_not_configured') {
		return '后端还没有管理口令：跑一次启动脚本（start.command / start.bat）会自动生成。';
	}
	if (status === 403) {
		return '管理口令不对。它在 TAgent重写版/.env.runtime 里，AGENT_ADMIN_TOKEN= 后面那一串。';
	}
	if (code === 'model_not_found' || status === 404) {
		return '没有这个模型（可能已经被删了），刷新列表再看看。';
	}
	if (code === 'validation_error') {
		const hint = VALIDATION_HINTS.find(([needle]) => message.includes(needle));
		return hint ? hint[1] : `登记没通过：${message}`;
	}
	if (status === 502 || status === 503 || status === 504) {
		return 'basic-agent 没有响应：它可能没有启动。';
	}
	return message ? `请求失败（${status}）：${message}` : `请求失败（${status}）`;
}

async function call<T>(token: string, path: string, method = 'GET', body?: unknown): Promise<T> {
	let response: Response;
	try {
		response = await fetch(`${agentBase()}/admin/model-providers${path}`, {
			method,
			headers: {
				'Content-Type': 'application/json',
				'X-Agent-Admin-Token': token.trim()
			},
			body: body === undefined ? undefined : JSON.stringify(body)
		});
	} catch {
		throw new ModelAdminError('连不上 basic-agent，确认它已经启动。', 0);
	}
	const payload = await response.json().catch(() => ({}));
	if (!response.ok) {
		throw new ModelAdminError(explain(response.status, payload), response.status);
	}
	return payload as T;
}

export const listModelProviders = (token: string) => call<ModelRegistry>(token, '');

export const createModelProvider = (token: string, input: ModelProviderInput) =>
	call<ModelProvider>(token, '', 'POST', withoutBlankKey(input));

export const updateModelProvider = (token: string, id: string, input: ModelProviderInput) =>
	call<ModelProvider>(token, `/${encodeURIComponent(id)}`, 'PUT', withoutBlankKey(input));

export const deleteModelProvider = (token: string, id: string) =>
	call<{ status: boolean; default_model_id: string }>(
		token,
		`/${encodeURIComponent(id)}`,
		'DELETE'
	);

export const setDefaultModelProvider = (token: string, id: string) =>
	call<ModelRegistry>(token, '/default', 'POST', { served_model_id: id });

/** 修改时 Key 留空表示不换：干脆不发这个字段，后端就沿用原来的 */
function withoutBlankKey(input: ModelProviderInput) {
	const { api_key, ...rest } = input;
	return api_key.trim() ? { ...rest, api_key: api_key.trim() } : rest;
}

export type ProbeResult =
	{ ok: true; reply: string; seconds: number } | { ok: false; reason: string };

/** 后端探测时给的输出额度（basic-agent admin.py 的 PROBE_MAX_TOKENS），只用来写提示 */
const PROBE_MAX_TOKENS = 64;
/** 回一个字用不了这么久；不设的话上游卡住时按钮要等后端 180 秒的超时 */
const PROBE_TIMEOUT_MS = 60_000;

/**
 * 用登记好的模型真发一句很短的话，看 Key、地址、模型名是不是都对。
 * 会真的调用一次模型，按量计费的话花费可以忽略。
 *
 * 走管理接口（要口令），发什么由后端定：只发一句固定的短话。以前直接走透传通道 /v1/raw，
 * 那条通道原样转发、什么都能发，现在不经前端端口开放了。
 */
export async function probeModel(token: string, servedModelId: string): Promise<ProbeResult> {
	const started = performance.now();
	let response: Response;
	try {
		response = await fetch(
			`${agentBase()}/admin/model-providers/${encodeURIComponent(servedModelId)}/probe`,
			{
				method: 'POST',
				headers: { 'X-Agent-Admin-Token': token.trim() },
				signal: AbortSignal.timeout(PROBE_TIMEOUT_MS)
			}
		);
	} catch (error) {
		if (error instanceof DOMException && error.name === 'TimeoutError') {
			return {
				ok: false,
				reason: `${PROBE_TIMEOUT_MS / 1000} 秒没有回应：检查接口地址，或者模型服务那边是否在排队。`
			};
		}
		return { ok: false, reason: '连不上 basic-agent，确认它已经启动。' };
	}
	const seconds = (performance.now() - started) / 1000;
	const payload = (await response.json().catch(() => ({}))) as {
		choices?: { message?: { content?: string }; finish_reason?: string }[];
		error?: { message?: string; code?: string } | string;
	};

	// 上游的原话带 X-Tagent-Upstream；不带的是 basic-agent 自己拦下的（口令不对、模型没登记）。
	// 不能看错误码分：上游也会回 403、404，OpenAI 一类的上游错误码也叫 model_not_found
	if (!response.ok && response.headers.get('X-Tagent-Upstream') !== '1') {
		const own = typeof payload.error === 'object' ? payload.error?.code : undefined;
		if (own === 'forbidden' || own === 'admin_token_not_configured') {
			return { ok: false, reason: '管理口令不对，或者 basic-agent 没有配置管理口令。' };
		}
		if (own === 'model_not_found') {
			return { ok: false, reason: '这个模型没有登记，或者已经停用。' };
		}
		const detail = typeof payload.error === 'string' ? payload.error : payload.error?.message;
		return {
			ok: false,
			reason: `没能连通模型服务（${response.status}）${detail ? `：${detail}` : ''}`
		};
	}

	if (!response.ok) {
		if (response.status === 401 || response.status === 403) {
			return {
				ok: false,
				reason: `模型服务拒绝了这个 Key（上游返回 ${response.status}），检查 Key 是否填对、是否还有余额。`
			};
		}
		if (response.status === 404) {
			return { ok: false, reason: '上游说没有这个模型（404）：检查接口地址和上游模型名。' };
		}
		const detail = typeof payload.error === 'string' ? payload.error : payload.error?.message;
		return { ok: false, reason: `调用失败（${response.status}）${detail ? `：${detail}` : ''}` };
	}

	const choice = payload.choices?.[0];
	const reply = choice?.message?.content?.trim() ?? '';
	if (!reply && choice?.finish_reason === 'length') {
		return {
			ok: false,
			reason: `连通了，但 ${PROBE_MAX_TOKENS} 个 token 都用在了思考上，正文是空的。正式回答时额度更大，可思考太长同样会挤掉正文，建议在附加参数里关闭思考。`
		};
	}
	if (!reply) {
		return { ok: false, reason: '连通了，但模型回了空内容。' };
	}
	return { ok: true, reply, seconds };
}
