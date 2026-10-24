<script lang="ts">
	import Switch from '$lib/components/common/Switch.svelte';
	import Textarea from '$lib/components/common/Textarea.svelte';
	import Tooltip from '$lib/components/common/Tooltip.svelte';
	import Plus from '$lib/components/icons/Plus.svelte';

	const zh: Record<string, string> = {
		'When enabled, the model will respond to each chat message in real-time, generating a response as soon as the user sends a message. This mode is useful for live chat applications, but may impact performance on slower hardware.':
			'启用后，模型会实时流式返回回答。',
		'Stream Chat Response': '流式对话响应 (Stream Chat Response)',
		On: '开启',
		Off: '关闭',
		Default: '默认',
		Custom: '自定义',
		'The stream delta chunk size for the model. Increasing the chunk size will make the model respond with larger pieces of text at once.':
			'流式增量块大小。增大后每次推送的文本块更大。',
		'Stream Delta Chunk Size': '流式增量输出的分块大小（Stream Delta Chunk Size）',
		"Default mode works with a wider range of models by calling tools once before execution. Native mode leverages the model's built-in tool-calling capabilities, but requires the model to inherently support this feature.":
			'默认模式兼容性更好；Native 模式使用模型原生工具调用能力。',
		'Function Calling': '函数调用 (Function Calling)',
		Native: '原生',
		'Enable, disable, or customize the reasoning tags used by the model. "Enabled" uses default tags, "Disabled" turns off reasoning tags, and "Custom" lets you specify your own start and end tags.':
			'启用、禁用或自定义推理标签。',
		'Reasoning Tags': '推理过程标签',
		Enabled: '已启用',
		Disabled: '已禁用',
		'Start Tag': '开始标签',
		'End Tag': '结束标签',
		'Sets the random number seed to use for generation. Setting this to a specific number will make the model generate the same text for the same prompt.':
			'设置随机种子，相同提示可复现相同输出。',
		Seed: '种子 (Seed)',
		'Enter Seed': '输入 Seed',
		'Sets the stop sequences to use. When this pattern is encountered, the LLM will stop generating text and return. Multiple stop patterns may be set by specifying multiple separate stop parameters in a modelfile.':
			'遇到停止序列时结束生成。',
		'Stop Sequence': '停止序列 (Stop Sequence)',
		'Enter stop sequence': '输入停止序列',
		'The temperature of the model. Increasing the temperature will make the model answer more creatively.':
			'温度越高，回答越有创造性。',
		Temperature: '温度 (Temperature)',
		'Constrains effort on reasoning for reasoning models. Only applicable to reasoning models from specific providers that support reasoning effort.':
			'约束推理模型的思考力度。',
		'Reasoning Effort': '推理努力 (Reasoning Effort)',
		'Enter reasoning effort': '输入推理力度',
		'Boosting or penalizing specific tokens for constrained responses. Bias values will be clamped between -100 and 100 (inclusive). (Default: none)':
			'对特定 token 施加偏置（-100~100）。',
		'Enter comma-separated "token:bias_value" pairs (example: 5432:100, 413:-100)':
			'逗号分隔 token:bias，如 5432:100,413:-100',
		'This option sets the maximum number of tokens the model can generate in its response. Increasing this limit allows the model to provide longer answers, but it may also increase the likelihood of unhelpful or irrelevant content being generated.':
			'限制回答的最大 token 数。',
		'Reduces the probability of generating nonsense. A higher value (e.g. 100) will give more diverse answers, while a lower value (e.g. 10) will be more conservative.':
			'top_k：越高越多样，越低越保守。',
		'Works together with top-k. A higher value (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text.':
			'与 top_k 配合；越高越多样。',
		'Alternative to the top_p, and aims to ensure a balance of quality and variety. The parameter p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.':
			'min_p：相对最高概率的最低阈值。',
		'Sets a scaling bias against tokens to penalize repetitions, based on how many times they have appeared. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient. At 0, it is disabled.':
			'按出现次数惩罚重复。',
		'Sets a flat bias against tokens that have appeared at least once. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient. At 0, it is disabled.':
			'对出现过的 token 施加固定惩罚。',
		'Enable Mirostat sampling for controlling perplexity.': '启用 Mirostat 采样以控制困惑度。',
		'Influences how quickly the algorithm responds to feedback from the generated text. A lower learning rate will result in slower adjustments, while a higher learning rate will make the algorithm more responsive.':
			'Mirostat 学习率。',
		'Controls the balance between coherence and diversity of the output. A lower value will result in more focused and coherent text.':
			'Mirostat 目标困惑度。',
		'Sets how far back for the model to look back to prevent repetition.':
			'回看多少 token 以防重复。',
		'Tail free sampling is used to reduce the impact of less probable tokens from the output. A higher value (e.g., 2.0) will reduce the impact more, while a value of 1.0 disables this setting.':
			'Tail Free Sampling。',
		'Control the repetition of token sequences in the generated text. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 1.1) will be more lenient. At 1, it is disabled.':
			'重复惩罚。',
		'Enable Memory Mapping (mmap) to load model data. This option allows the system to use disk storage as an extension of RAM by treating disk files as if they were in RAM. This can improve model performance by allowing for faster data access. However, it may not work correctly with all systems and can consume a significant amount of disk space.':
			'启用 mmap 加载模型。',
		"Enable Memory Locking (mlock) to prevent model data from being swapped out of RAM. This option locks the model's working set of pages into RAM, ensuring that they will not be swapped out to disk. This can help maintain performance by avoiding page faults and ensuring fast data access.":
			'启用 mlock 锁定模型内存。',
		'This option enables or disables the use of the reasoning feature in Ollama, which allows the model to think before generating a response. When enabled, the model can take a moment to process the conversation context and generate a more thoughtful response.':
			'启用 Ollama think 推理。',
		"e.g. 'low', 'medium', 'high'": "例如 'low'、'medium'、'high'",
		'The format to return a response in. Format can be json or a JSON schema.':
			'返回格式，可为 json 或 JSON schema。',
		JSON: 'JSON',
		'e.g. "json" or a JSON schema': '例如 "json" 或 JSON schema',
		'This option controls how many tokens are preserved when refreshing the context. For example, if set to 2, the last 2 tokens of the conversation context will be retained. Preserving context can help maintain the continuity of a conversation, but it may reduce the ability to respond to new topics.':
			'刷新上下文时保留的 token 数。',
		'Sets the size of the context window used to generate the next token.': '上下文窗口大小。',
		'The batch size determines how many text requests are processed together at once. A higher batch size can increase the performance and speed of the model, but it also requires more memory.':
			'批处理大小。',
		'Set the number of worker threads used for computation. This option controls how many threads are used to process incoming requests concurrently. Increasing this value can improve performance under high concurrency workloads but may also consume more CPU resources.':
			'计算线程数。',
		'Set the number of layers, which will be off-loaded to GPU. Increasing this value can significantly improve performance for models that are optimized for GPU acceleration but may also consume more power and GPU resources.':
			'卸载到 GPU 的层数。',
		'This option controls how long the model will stay loaded into memory following the request (default: 5m)':
			'请求后模型在内存中保留多久（默认 5m）。',
		"e.g. '30s','10m'. Valid time units are 's', 'm', 'h'.": "例如 '30s'、'10m'。单位：s / m / h",
		'Custom Parameter Name': '自定义参数名',
		Remove: '移除',
		'Custom Parameter Value': '自定义参数值',
		'Add Custom Parameter': '添加自定义参数',
		Ollama: 'Ollama'
	};
	const t = (key: string) => zh[key] ?? key;
	type AdvancedParams = Record<string, unknown> & {
		reasoning_tags: boolean | [string, string] | null;
		use_mmap?: boolean | null;
		use_mlock?: boolean | null;
		format?: string;
		custom_params: Record<string, string>;
	};

	type Props = {
		onChange?: (params: Record<string, unknown>) => void;
		admin?: boolean;
		custom?: boolean;
		params?: AdvancedParams;
		showAll?: boolean;
	};

	let {
		onChange = () => {},
		admin = false,
		custom = false,
		/** 连后端不认的旋钮一起显示。默认只显示真正生效的那几项，见文件顶部说明。 */
		showAll = false,
		params = $bindable({
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
			format: undefined,
			keep_alive: null,
			num_keep: null,
			num_ctx: null,
			num_batch: null,
			num_thread: null,
			num_gpu: null,
			custom_params: {}
		} as unknown as AdvancedParams)
	}: Props = $props();

	const emitChange = () => {
		onChange(params);
	};
	void emitChange;
</script>

<!--
	这个面板是 Open WebUI 的遗留，列了二十多个旋钮，而本项目的后端只认
	temperature / top_p / max_tokens 三项（见 app/api/validators.py 的 chat_tuning
	与 app/infra/model_client_factory.py 的 TUNABLE）。其余的调了不会有任何变化——
	给学生一个没效果的滑块，比不给更糟。所以默认只显示生效的那几项。
	showAll 留给确实想看全部的场合（例如调试透传通道）。
-->
<div class=" pb-safe-bottom space-y-1 text-xs">
	<div>
		<Tooltip
			content={t(
				'When enabled, the model will respond to each chat message in real-time, generating a response as soon as the user sends a message. This mode is useful for live chat applications, but may impact performance on slower hardware.'
			)}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class=" flex w-full justify-between py-0.5">
				<div class=" self-center text-xs">
					{t('Stream Chat Response')}
				</div>
				<button
					class="flex rounded-sm p-1 px-3 text-xs transition"
					onclick={() => {
						params.stream_response =
							(params?.stream_response ?? null) === null
								? true
								: params.stream_response
									? false
									: null;
					}}
					type="button"
				>
					{#if params.stream_response === true}
						<span class="ml-2 self-center">{t('On')}</span>
					{:else if params.stream_response === false}
						<span class="ml-2 self-center">{t('Off')}</span>
					{:else}
						<span class="ml-2 self-center">{t('Default')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
	</div>

	{#if admin}
		<div>
			<Tooltip
				content={t(
					'The stream delta chunk size for the model. Increasing the chunk size will make the model respond with larger pieces of text at once.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						{t('Stream Delta Chunk Size')}
					</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.stream_delta_chunk_size =
								(params?.stream_delta_chunk_size ?? null) === null ? 1 : null;
						}}
					>
						{#if (params?.stream_delta_chunk_size ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.stream_delta_chunk_size ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="1"
							max="128"
							step="1"
							bind:value={params.stream_delta_chunk_size}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.stream_delta_chunk_size}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="1"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}

	<div>
		<Tooltip
			content={t(
				"Default mode works with a wider range of models by calling tools once before execution. Native mode leverages the model's built-in tool-calling capabilities, but requires the model to inherently support this feature."
			)}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class=" flex w-full justify-between py-0.5">
				<div class=" self-center text-xs">
					{t('Function Calling')}
				</div>
				<button
					class="flex rounded-sm p-1 px-3 text-xs transition"
					onclick={() => {
						params.function_calling = (params?.function_calling ?? null) === null ? 'native' : null;
					}}
					type="button"
				>
					{#if params.function_calling === 'native'}
						<span class="ml-2 self-center">{t('Native')}</span>
					{:else}
						<span class="ml-2 self-center">{t('Default')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>
	</div>

	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Enable, disable, or customize the reasoning tags used by the model. "Enabled" uses default tags, "Disabled" turns off reasoning tags, and "Custom" lets you specify your own start and end tags.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						{t('Reasoning Tags')}
					</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							if ((params?.reasoning_tags ?? null) === null) {
								params.reasoning_tags = ['', ''];
							} else if (
								Array.isArray(params.reasoning_tags) &&
								params.reasoning_tags.length === 2
							) {
								params.reasoning_tags = true;
							} else if ((params?.reasoning_tags ?? null) !== false) {
								params.reasoning_tags = false;
							} else {
								params.reasoning_tags = null;
							}
						}}
					>
						{#if (params?.reasoning_tags ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else if (params?.reasoning_tags ?? null) === true}
							<span class="ml-2 self-center"> {t('Enabled')} </span>
						{:else if (params?.reasoning_tags ?? null) === false}
							<span class="ml-2 self-center"> {t('Disabled')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if Array.isArray(params.reasoning_tags) && params.reasoning_tags.length === 2}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t('Start Tag')}
							bind:value={(params.reasoning_tags as [string, string])[0]}
							autocomplete="off"
						/>
					</div>

					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t('End Tag')}
							bind:value={(params.reasoning_tags as [string, string])[1]}
							autocomplete="off"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Sets the random number seed to use for generation. Setting this to a specific number will make the model generate the same text for the same prompt.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						{t('Seed')}
					</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.seed = (params?.seed ?? null) === null ? 0 : null;
						}}
					>
						{#if (params?.seed ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.seed ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="number"
							placeholder={t('Enter Seed')}
							bind:value={params.seed}
							autocomplete="off"
							min="0"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Sets the stop sequences to use. When this pattern is encountered, the LLM will stop generating text and return. Multiple stop patterns may be set by specifying multiple separate stop parameters in a modelfile.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						{t('Stop Sequence')}
					</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.stop = (params?.stop ?? null) === null ? '' : null;
						}}
					>
						{#if (params?.stop ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.stop ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t('Enter stop sequence')}
							bind:value={params.stop}
							autocomplete="off"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	<div class=" w-full justify-between py-0.5">
		<Tooltip
			content={t(
				'The temperature of the model. Increasing the temperature will make the model answer more creatively.'
			)}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">
					{t('Temperature')}
				</div>
				<button
					class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
					type="button"
					onclick={() => {
						params.temperature = (params?.temperature ?? null) === null ? 0.8 : null;
					}}
				>
					{#if (params?.temperature ?? null) === null}
						<span class="ml-2 self-center"> {t('Default')} </span>
					{:else}
						<span class="ml-2 self-center"> {t('Custom')} </span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.temperature ?? null) !== null}
			<div class="mt-0.5 flex space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="2"
						step="0.05"
						bind:value={params.temperature}
						class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.temperature}
						type="number"
						class=" w-14 bg-transparent text-center"
						min="0"
						max="2"
						step="any"
					/>
				</div>
			</div>
		{/if}
	</div>

	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Constrains effort on reasoning for reasoning models. Only applicable to reasoning models from specific providers that support reasoning effort.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						{t('Reasoning Effort')}
					</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.reasoning_effort =
								(params?.reasoning_effort ?? null) === null ? 'medium' : null;
						}}
					>
						{#if (params?.reasoning_effort ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.reasoning_effort ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t('Enter reasoning effort')}
							bind:value={params.reasoning_effort}
							autocomplete="off"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Boosting or penalizing specific tokens for constrained responses. Bias values will be clamped between -100 and 100 (inclusive). (Default: none)'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">logit_bias</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.logit_bias = (params?.logit_bias ?? null) === null ? '' : null;
						}}
					>
						{#if (params?.logit_bias ?? null) === null}
							<span class="ml-2 self-center"> {t('Default')} </span>
						{:else}
							<span class="ml-2 self-center"> {t('Custom')} </span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.logit_bias ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t(
								'Enter comma-separated "token:bias_value" pairs (example: 5432:100, 413:-100)'
							)}
							bind:value={params.logit_bias}
							autocomplete="off"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	<div class=" w-full justify-between py-0.5">
		<Tooltip
			content={t(
				'This option sets the maximum number of tokens the model can generate in its response. Increasing this limit allows the model to provide longer answers, but it may also increase the likelihood of unhelpful or irrelevant content being generated.'
			)}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">max_tokens</div>

				<button
					class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
					type="button"
					onclick={() => {
						params.max_tokens = (params?.max_tokens ?? null) === null ? 128 : null;
					}}
				>
					{#if (params?.max_tokens ?? null) === null}
						<span class="ml-2 self-center">{t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.max_tokens ?? null) !== null}
			<div class="mt-0.5 flex space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="-2"
						max="131072"
						step="1"
						bind:value={params.max_tokens}
						class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.max_tokens}
						type="number"
						class=" w-14 bg-transparent text-center"
						min="-2"
						step="1"
					/>
				</div>
			</div>
		{/if}
	</div>

	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Reduces the probability of generating nonsense. A higher value (e.g. 100) will give more diverse answers, while a lower value (e.g. 10) will be more conservative.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">top_k</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.top_k = (params?.top_k ?? null) === null ? 40 : null;
						}}
					>
						{#if (params?.top_k ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.top_k ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="1000"
							step="0.5"
							bind:value={params.top_k}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.top_k}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="100"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	<div class=" w-full justify-between py-0.5">
		<Tooltip
			content={t(
				'Works together with top-k. A higher value (e.g., 0.95) will lead to more diverse text, while a lower value (e.g., 0.5) will generate more focused and conservative text.'
			)}
			placement="top-start"
			className="inline-tooltip"
		>
			<div class="flex w-full justify-between">
				<div class=" self-center text-xs">top_p</div>

				<button
					class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
					type="button"
					onclick={() => {
						params.top_p = (params?.top_p ?? null) === null ? 0.9 : null;
					}}
				>
					{#if (params?.top_p ?? null) === null}
						<span class="ml-2 self-center">{t('Default')}</span>
					{:else}
						<span class="ml-2 self-center">{t('Custom')}</span>
					{/if}
				</button>
			</div>
		</Tooltip>

		{#if (params?.top_p ?? null) !== null}
			<div class="mt-0.5 flex space-x-2">
				<div class=" flex-1">
					<input
						id="steps-range"
						type="range"
						min="0"
						max="1"
						step="0.05"
						bind:value={params.top_p}
						class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
					/>
				</div>
				<div>
					<input
						bind:value={params.top_p}
						type="number"
						class=" w-14 bg-transparent text-center"
						min="0"
						max="1"
						step="any"
					/>
				</div>
			</div>
		{/if}
	</div>

	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Alternative to the top_p, and aims to ensure a balance of quality and variety. The parameter p represents the minimum probability for a token to be considered, relative to the probability of the most likely token. For example, with p=0.05 and the most likely token having a probability of 0.9, logits with a value less than 0.045 are filtered out.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">min_p</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.min_p = (params?.min_p ?? null) === null ? 0.0 : null;
						}}
					>
						{#if (params?.min_p ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.min_p ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="1"
							step="0.05"
							bind:value={params.min_p}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.min_p}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="1"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Sets a scaling bias against tokens to penalize repetitions, based on how many times they have appeared. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient. At 0, it is disabled.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">frequency_penalty</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.frequency_penalty = (params?.frequency_penalty ?? null) === null ? 1.1 : null;
						}}
					>
						{#if (params?.frequency_penalty ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.frequency_penalty ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-2"
							max="2"
							step="0.05"
							bind:value={params.frequency_penalty}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.frequency_penalty}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-2"
							max="2"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Sets a flat bias against tokens that have appeared at least once. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 0.9) will be more lenient. At 0, it is disabled.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">presence_penalty</div>

					<button
						class="flex flex-shrink-0 rounded p-1 px-3 text-xs transition outline-none"
						type="button"
						onclick={() => {
							params.presence_penalty = (params?.presence_penalty ?? null) === null ? 0.0 : null;
						}}
					>
						{#if (params?.presence_penalty ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.presence_penalty ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-2"
							max="2"
							step="0.05"
							bind:value={params.presence_penalty}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.presence_penalty}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-2"
							max="2"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t('Enable Mirostat sampling for controlling perplexity.')}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">mirostat</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.mirostat = (params?.mirostat ?? null) === null ? 0 : null;
						}}
					>
						{#if (params?.mirostat ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.mirostat ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="2"
							step="1"
							bind:value={params.mirostat}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.mirostat}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="2"
							step="1"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Influences how quickly the algorithm responds to feedback from the generated text. A lower learning rate will result in slower adjustments, while a higher learning rate will make the algorithm more responsive.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">mirostat_eta</div>
					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.mirostat_eta = (params?.mirostat_eta ?? null) === null ? 0.1 : null;
						}}
					>
						{#if (params?.mirostat_eta ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.mirostat_eta ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="1"
							step="0.05"
							bind:value={params.mirostat_eta}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.mirostat_eta}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="1"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Controls the balance between coherence and diversity of the output. A lower value will result in more focused and coherent text.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">mirostat_tau</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.mirostat_tau = (params?.mirostat_tau ?? null) === null ? 5.0 : null;
						}}
					>
						{#if (params?.mirostat_tau ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.mirostat_tau ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="10"
							step="0.5"
							bind:value={params.mirostat_tau}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.mirostat_tau}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="10"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t('Sets how far back for the model to look back to prevent repetition.')}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">repeat_last_n</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.repeat_last_n = (params?.repeat_last_n ?? null) === null ? 64 : null;
						}}
					>
						{#if (params?.repeat_last_n ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.repeat_last_n ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-1"
							max="128"
							step="1"
							bind:value={params.repeat_last_n}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.repeat_last_n}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-1"
							max="128"
							step="1"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Tail free sampling is used to reduce the impact of less probable tokens from the output. A higher value (e.g., 2.0) will reduce the impact more, while a value of 1.0 disables this setting.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">tfs_z</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.tfs_z = (params?.tfs_z ?? null) === null ? 1 : null;
						}}
					>
						{#if (params?.tfs_z ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.tfs_z ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="0"
							max="2"
							step="0.05"
							bind:value={params.tfs_z}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.tfs_z}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="0"
							max="2"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'Control the repetition of token sequences in the generated text. A higher value (e.g., 1.5) will penalize repetitions more strongly, while a lower value (e.g., 1.1) will be more lenient. At 1, it is disabled.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">repeat_penalty</div>

					<button
						class="flex flex-shrink-0 rounded p-1 px-3 text-xs transition outline-none"
						type="button"
						onclick={() => {
							params.repeat_penalty = (params?.repeat_penalty ?? null) === null ? 1.1 : null;
						}}
					>
						{#if (params?.repeat_penalty ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.repeat_penalty ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-2"
							max="2"
							step="0.05"
							bind:value={params.repeat_penalty}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.repeat_penalty}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-2"
							max="2"
							step="any"
						/>
					</div>
				</div>
			{/if}
		</div>

		{#if admin}
			<div class=" w-full justify-between py-0.5">
				<Tooltip
					content={t(
						'Enable Memory Mapping (mmap) to load model data. This option allows the system to use disk storage as an extension of RAM by treating disk files as if they were in RAM. This can improve model performance by allowing for faster data access. However, it may not work correctly with all systems and can consume a significant amount of disk space.'
					)}
					placement="top-start"
					className="inline-tooltip"
				>
					<div class="flex w-full justify-between">
						<div class=" self-center text-xs">use_mmap</div>
						<button
							class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
							type="button"
							onclick={() => {
								params.use_mmap = (params?.use_mmap ?? null) === null ? true : null;
							}}
						>
							{#if (params?.use_mmap ?? null) === null}
								<span class="ml-2 self-center">{t('Default')}</span>
							{:else}
								<span class="ml-2 self-center">{t('Custom')}</span>
							{/if}
						</button>
					</div>
				</Tooltip>

				{#if (params?.use_mmap ?? null) !== null}
					<div class="mt-1 flex items-center justify-between">
						<div class="text-xs text-gray-500">
							{params.use_mmap ? t('Enabled') : t('Disabled')}
						</div>
						<div class=" pr-2">
							<Switch
								state={params.use_mmap ?? false}
								onChange={() => (params.use_mmap = !(params.use_mmap ?? false))}
							/>
						</div>
					</div>
				{/if}
			</div>

			<div class=" w-full justify-between py-0.5">
				<Tooltip
					content={t(
						"Enable Memory Locking (mlock) to prevent model data from being swapped out of RAM. This option locks the model's working set of pages into RAM, ensuring that they will not be swapped out to disk. This can help maintain performance by avoiding page faults and ensuring fast data access."
					)}
					placement="top-start"
					className="inline-tooltip"
				>
					<div class="flex w-full justify-between">
						<div class=" self-center text-xs">use_mlock</div>

						<button
							class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
							type="button"
							onclick={() => {
								params.use_mlock = (params?.use_mlock ?? null) === null ? true : null;
							}}
						>
							{#if (params?.use_mlock ?? null) === null}
								<span class="ml-2 self-center">{t('Default')}</span>
							{:else}
								<span class="ml-2 self-center">{t('Custom')}</span>
							{/if}
						</button>
					</div>
				</Tooltip>

				{#if (params?.use_mlock ?? null) !== null}
					<div class="mt-1 flex items-center justify-between">
						<div class="text-xs text-gray-500">
							{params.use_mlock ? t('Enabled') : t('Disabled')}
						</div>

						<div class=" pr-2">
							<Switch
								state={params.use_mlock ?? false}
								onChange={() => (params.use_mlock = !(params.use_mlock ?? false))}
							/>
						</div>
					</div>
				{/if}
			</div>
		{/if}
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'This option enables or disables the use of the reasoning feature in Ollama, which allows the model to think before generating a response. When enabled, the model can take a moment to process the conversation context and generate a more thoughtful response.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class=" flex w-full justify-between py-0.5">
					<div class=" self-center text-xs">
						think ({t('Ollama')})
					</div>
					<button
						class="flex rounded-sm p-1 px-3 text-xs transition"
						onclick={() => {
							if ((params?.think ?? null) === null) {
								params.think = true;
							} else if (params.think === true) {
								params.think = 'medium';
							} else if (typeof params.think === 'string') {
								params.think = false;
							} else {
								params.think = null;
							}
						}}
						type="button"
					>
						{#if params.think === true}
							<span class="ml-2 self-center">{t('On')}</span>
						{:else if params.think === false}
							<span class="ml-2 self-center">{t('Off')}</span>
						{:else if typeof params.think === 'string'}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Default')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if typeof params.think === 'string'}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							class="w-full bg-transparent text-sm outline-hidden outline-none"
							type="text"
							placeholder={t("e.g. 'low', 'medium', 'high'")}
							bind:value={params.think}
							autocomplete="off"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t('The format to return a response in. Format can be json or a JSON schema.')}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class=" flex w-full justify-between py-0.5">
					<div class=" self-center text-xs">
						format ({t('Ollama')})
					</div>
					<button
						class="flex rounded-sm p-1 px-3 text-xs transition"
						onclick={() => {
							params.format = (params?.format ?? null) === null ? 'json' : undefined;
						}}
						type="button"
					>
						{#if (params?.format ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('JSON')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.format ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<Textarea
						className="w-full  text-sm bg-transparent outline-hidden"
						placeholder={t('e.g. "json" or a JSON schema')}
						bind:value={params.format}
					/>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'This option controls how many tokens are preserved when refreshing the context. For example, if set to 2, the last 2 tokens of the conversation context will be retained. Preserving context can help maintain the continuity of a conversation, but it may reduce the ability to respond to new topics.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						num_keep ({t('Ollama')})
					</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.num_keep = (params?.num_keep ?? null) === null ? 24 : null;
						}}
					>
						{#if (params?.num_keep ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.num_keep ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-1"
							max="10240000"
							step="1"
							bind:value={params.num_keep}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div class="">
						<input
							bind:value={params.num_keep}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-1"
							step="1"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t('Sets the size of the context window used to generate the next token.')}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						num_ctx ({t('Ollama')})
					</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.num_ctx = (params?.num_ctx ?? null) === null ? 2048 : null;
						}}
					>
						{#if (params?.num_ctx ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.num_ctx ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="-1"
							max="10240000"
							step="1"
							bind:value={params.num_ctx}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div class="">
						<input
							bind:value={params.num_ctx}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="-1"
							step="1"
						/>
					</div>
				</div>
			{/if}
		</div>
	{/if}
	{#if showAll}
		<div class=" w-full justify-between py-0.5">
			<Tooltip
				content={t(
					'The batch size determines how many text requests are processed together at once. A higher batch size can increase the performance and speed of the model, but it also requires more memory.'
				)}
				placement="top-start"
				className="inline-tooltip"
			>
				<div class="flex w-full justify-between">
					<div class=" self-center text-xs">
						num_batch ({t('Ollama')})
					</div>

					<button
						class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
						type="button"
						onclick={() => {
							params.num_batch = (params?.num_batch ?? null) === null ? 512 : null;
						}}
					>
						{#if (params?.num_batch ?? null) === null}
							<span class="ml-2 self-center">{t('Default')}</span>
						{:else}
							<span class="ml-2 self-center">{t('Custom')}</span>
						{/if}
					</button>
				</div>
			</Tooltip>

			{#if (params?.num_batch ?? null) !== null}
				<div class="mt-0.5 flex space-x-2">
					<div class=" flex-1">
						<input
							id="steps-range"
							type="range"
							min="256"
							max="8192"
							step="256"
							bind:value={params.num_batch}
							class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
						/>
					</div>
					<div>
						<input
							bind:value={params.num_batch}
							type="number"
							class=" w-14 bg-transparent text-center"
							min="256"
							step="256"
						/>
					</div>
				</div>
			{/if}
		</div>

		{#if admin}
			<div class=" w-full justify-between py-0.5">
				<Tooltip
					content={t(
						'Set the number of worker threads used for computation. This option controls how many threads are used to process incoming requests concurrently. Increasing this value can improve performance under high concurrency workloads but may also consume more CPU resources.'
					)}
					placement="top-start"
					className="inline-tooltip"
				>
					<div class="flex w-full justify-between">
						<div class=" self-center text-xs">
							num_thread ({t('Ollama')})
						</div>

						<button
							class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
							type="button"
							onclick={() => {
								params.num_thread = (params?.num_thread ?? null) === null ? 2 : null;
							}}
						>
							{#if (params?.num_thread ?? null) === null}
								<span class="ml-2 self-center">{t('Default')}</span>
							{:else}
								<span class="ml-2 self-center">{t('Custom')}</span>
							{/if}
						</button>
					</div>
				</Tooltip>

				{#if (params?.num_thread ?? null) !== null}
					<div class="mt-0.5 flex space-x-2">
						<div class=" flex-1">
							<input
								id="steps-range"
								type="range"
								min="1"
								max="256"
								step="1"
								bind:value={params.num_thread}
								class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
							/>
						</div>
						<div class="">
							<input
								bind:value={params.num_thread}
								type="number"
								class=" w-14 bg-transparent text-center"
								min="1"
								max="256"
								step="1"
							/>
						</div>
					</div>
				{/if}
			</div>

			<div class=" w-full justify-between py-0.5">
				<Tooltip
					content={t(
						'Set the number of layers, which will be off-loaded to GPU. Increasing this value can significantly improve performance for models that are optimized for GPU acceleration but may also consume more power and GPU resources.'
					)}
					placement="top-start"
					className="inline-tooltip"
				>
					<div class="flex w-full justify-between">
						<div class=" self-center text-xs">
							num_gpu ({t('Ollama')})
						</div>

						<button
							class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
							type="button"
							onclick={() => {
								params.num_gpu = (params?.num_gpu ?? null) === null ? 0 : null;
							}}
						>
							{#if (params?.num_gpu ?? null) === null}
								<span class="ml-2 self-center">{t('Default')}</span>
							{:else}
								<span class="ml-2 self-center">{t('Custom')}</span>
							{/if}
						</button>
					</div>
				</Tooltip>

				{#if (params?.num_gpu ?? null) !== null}
					<div class="mt-0.5 flex space-x-2">
						<div class=" flex-1">
							<input
								id="steps-range"
								type="range"
								min="0"
								max="256"
								step="1"
								bind:value={params.num_gpu}
								class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700"
							/>
						</div>
						<div class="">
							<input
								bind:value={params.num_gpu}
								type="number"
								class=" w-14 bg-transparent text-center"
								min="0"
								max="256"
								step="1"
							/>
						</div>
					</div>
				{/if}
			</div>

			<div class=" w-full justify-between py-0.5">
				<Tooltip
					content={t(
						'This option controls how long the model will stay loaded into memory following the request (default: 5m)'
					)}
					placement="top-start"
					className="inline-tooltip"
				>
					<div class=" flex w-full justify-between py-0.5">
						<div class=" self-center text-xs">
							keep_alive ({t('Ollama')})
						</div>
						<button
							class="flex rounded-sm p-1 px-3 text-xs transition"
							onclick={() => {
								params.keep_alive = (params?.keep_alive ?? null) === null ? '5m' : null;
							}}
							type="button"
						>
							{#if (params?.keep_alive ?? null) === null}
								<span class="ml-2 self-center">{t('Default')}</span>
							{:else}
								<span class="ml-2 self-center">{t('Custom')}</span>
							{/if}
						</button>
					</div>
				</Tooltip>

				{#if (params?.keep_alive ?? null) !== null}
					<div class="mt-0.5 flex space-x-2">
						<input
							class="w-full bg-transparent text-sm outline-hidden"
							type="text"
							placeholder={t("e.g. '30s','10m'. Valid time units are 's', 'm', 'h'.")}
							bind:value={params.keep_alive}
						/>
					</div>
				{/if}
			</div>

			{#if custom && admin}
				<div class="flex flex-col justify-center">
					{#each Object.keys(params?.custom_params ?? {}) as key (key)}
						<div class=" mb-1 w-full justify-between py-0.5">
							<div class="flex w-full justify-between">
								<div class=" self-center text-xs">
									<input
										type="text"
										class=" w-full bg-transparent text-xs outline-none"
										placeholder={t('Custom Parameter Name')}
										value={key}
										onchange={(e) => {
											const newKey = (e.target as HTMLInputElement).value.trim();
											if (newKey && newKey !== key) {
												params.custom_params[newKey] = params.custom_params[key];
												delete params.custom_params[key];
												params = {
													...params,
													custom_params: { ...params.custom_params }
												};
											}
										}}
									/>
								</div>
								<button
									class="flex shrink-0 rounded-sm p-1 px-3 text-xs outline-hidden transition"
									type="button"
									onclick={() => {
										delete params.custom_params[key];
										params = {
											...params,
											custom_params: { ...params.custom_params }
										};
									}}
								>
									{t('Remove')}
								</button>
							</div>
							<div class="mt-0.5 flex space-x-2">
								<div class=" flex-1">
									<input
										bind:value={params.custom_params[key]}
										type="text"
										class="w-full bg-transparent text-sm outline-hidden outline-none"
										placeholder={t('Custom Parameter Value')}
									/>
								</div>
							</div>
						</div>
					{/each}

					<button
						class=" mt-1 mb-5 flex w-full items-center justify-center gap-2 text-center"
						type="button"
						onclick={() => {
							params.custom_params = (params?.custom_params ?? {}) || {};
							params.custom_params['custom_param_name'] = 'custom_param_value';
						}}
					>
						<div>
							<Plus />
						</div>
						<div>{t('Add Custom Parameter')}</div>
					</button>
				</div>
			{/if}
		{/if}
	{/if}
</div>
