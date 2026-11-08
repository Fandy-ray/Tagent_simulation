import { browser } from '$app/environment';
import { readPersonalCache, writePersonalCache } from '$lib/apis/auth';

export type ChatControlParams = Record<string, unknown>;

export const defaultChatControls = (): ChatControlParams => ({
	system: '',
	stream_response: null,
	stream_delta_chunk_size: null,
	function_calling: null,
	reasoning_tags: null,
	seed: null,
	stop: null,
	temperature: null,
	reasoning_effort: null,
	logit_bias: null,
	max_tokens: null,
	top_k: null,
	top_p: null,
	min_p: null,
	frequency_penalty: null,
	presence_penalty: null,
	mirostat: null,
	mirostat_eta: null,
	mirostat_tau: null,
	repeat_last_n: null,
	tfs_z: null,
	repeat_penalty: null,
	use_mmap: null,
	use_mlock: null,
	think: null,
	format: null,
	keep_alive: null,
	num_keep: null,
	num_ctx: null,
	num_batch: null,
	num_thread: null,
	num_gpu: null,
	custom_params: {}
});

export function loadChatControls(): ChatControlParams {
	const defaults = defaultChatControls();
	if (!browser) {
		return defaults;
	}

	try {
		const raw = readPersonalCache('controls');
		if (!raw) {
			return defaults;
		}
		const parsed = JSON.parse(raw) as Record<string, unknown> & {
			custom_params?: Record<string, unknown>;
		};
		return {
			...defaults,
			...(parsed as Record<string, unknown>),
			custom_params: {
				...(defaults.custom_params as Record<string, unknown>),
				...(parsed.custom_params ?? {})
			}
		};
	} catch {
		return defaults;
	}
}

export function saveChatControls(params: ChatControlParams) {
	if (!browser) {
		return;
	}

	try {
		writePersonalCache('controls', JSON.stringify(params));
	} catch {
		// ignore quota / private mode
	}
}

const PASSTHROUGH_KEYS = [
	'temperature',
	'top_p',
	'top_k',
	'min_p',
	'max_tokens',
	'frequency_penalty',
	'presence_penalty',
	'seed',
	'stop',
	'logit_bias',
	'reasoning_effort',
	'stream_response',
	'mirostat',
	'mirostat_eta',
	'mirostat_tau',
	'repeat_last_n',
	'tfs_z',
	'repeat_penalty',
	'think',
	'format',
	'num_keep',
	'num_ctx',
	'num_batch',
	'num_thread',
	'num_gpu',
	'keep_alive',
	'use_mmap',
	'use_mlock',
	'function_calling',
	'reasoning_tags',
	'stream_delta_chunk_size'
] as const;

/** 发给 basic-agent 时只带已自定义的字段 */
export function toAgentOptions(params: ChatControlParams) {
	const options: Record<string, unknown> = {};

	if (typeof params.system === 'string' && params.system.trim()) {
		options.system = params.system.trim();
	}

	for (const key of PASSTHROUGH_KEYS) {
		const value = params[key];
		if (value === null || value === undefined) continue;
		if (key === 'stop' && typeof value === 'string') {
			const stops = value
				.split(',')
				.map((item: string) => item.trim())
				.filter(Boolean);
			if (stops.length) options.stop = stops;
			continue;
		}
		options[key] = value;
	}

	const custom = params.custom_params;
	if (custom && typeof custom === 'object') {
		for (const [key, value] of Object.entries(custom)) {
			if (!key || key === 'custom_param_name') continue;
			options[key] = value;
		}
	}

	return options;
}
