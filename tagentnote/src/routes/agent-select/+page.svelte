<script lang="ts">
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	import { getAgentModels } from '$lib/apis/agent';

	type AgentType = 'qa' | 'notebook' | 'quiz';

	type AgentCard = {
		type: AgentType;
		name: string;
		description: string;
		accent: 'cyan' | 'violet' | 'green';
	};

	let models = $state<{ id: string; name: string }[]>([]);
	let selectedModelId = $state('');
	let modelsError = $state('');

	onMount(() => {
		void getAgentModels()
			.then((list) => {
				models = list.data.map((model) => ({
					id: model.id,
					name: model.name || model.id
				}));
				selectedModelId = models[0]?.id ?? '';
				if (models.length === 0) {
					modelsError = 'basic-agent 已连上，但还没有配置任何模型。';
				}
			})
			.catch(() => {
				modelsError = '读不到 basic-agent 的模型列表，请确认它已在 5001 端口启动。';
			});
	});

	const agents: AgentCard[] = [
		{
			type: 'qa',
			name: '答疑智能体',
			description: '课程答疑与论文辅助：检索增强问答、分章写作与交稿批改。',
			accent: 'cyan'
		},
		{
			type: 'notebook',
			name: '笔记本',
			description: '进入 OpenNoteBook 知识工作空间。',
			accent: 'violet'
		},
		{
			type: 'quiz',
			name: '测评智能体',
			description: '生成知识测验并对作答进行评分。',
			accent: 'green'
		}
	];

	const selectAgent = (type: AgentType) => {
		if (type === 'notebook') {
			void goto(resolve('/notebook'));
			return;
		}

		// 模型列表还没回来时点进去：不带 model，到了那边按列表选默认的（别带一个空的 model=）
		const query = selectedModelId ? `?model=${encodeURIComponent(selectedModelId)}` : '';
		void goto(resolve(`${type === 'quiz' ? '/exam' : '/qa'}${query}`));
	};

	const getIconBackground = (accent: AgentCard['accent']) => {
		if (accent === 'cyan') {
			return 'bg-cyan-400/10 text-cyan-300 ring-cyan-400/20';
		}

		if (accent === 'violet') {
			return 'bg-violet-400/10 text-violet-300 ring-violet-400/20';
		}

		return 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/20';
	};

	const getCardHover = (accent: AgentCard['accent']) => {
		if (accent === 'cyan') {
			return 'hover:border-cyan-400/50 hover:shadow-cyan-950/30 focus:ring-cyan-400';
		}

		if (accent === 'violet') {
			return 'hover:border-violet-400/50 hover:shadow-violet-950/30 focus:ring-violet-400';
		}

		return 'hover:border-emerald-400/50 hover:shadow-emerald-950/30 focus:ring-emerald-400';
	};
</script>

<svelte:head>
	<title>选择智能体 | 系统建模与仿真智能教学平台</title>
</svelte:head>

<main class="relative min-h-screen overflow-hidden bg-gray-900 text-gray-100">
	<div
		class="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_25%_10%,rgba(8,145,178,0.10),transparent_28%),radial-gradient(circle_at_80%_80%,rgba(124,58,237,0.08),transparent_30%)]"
	></div>

	<div
		class="relative mx-auto flex min-h-screen w-full max-w-6xl flex-col justify-center px-5 py-10 sm:px-8 lg:px-10"
	>
		<header class="border-b border-white/10 pb-8">
			<div class="flex items-center gap-4">
				<div
					class="flex size-12 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-cyan-300 to-sky-500 text-base font-black text-gray-950 shadow-lg shadow-cyan-950/40"
				>
					T
				</div>

				<div>
					<h1 class="text-2xl font-semibold tracking-tight text-white">
						系统建模与仿真智能教学平台
					</h1>
					<p class="mt-1 text-sm text-gray-400">系统建模与仿真</p>
				</div>
			</div>
		</header>

		<section class="py-9" aria-labelledby="agent-mode-title">
			<div class="flex flex-col justify-between gap-6 md:flex-row md:items-end">
				<div>
					<p class="text-xs font-medium tracking-[0.22em] text-cyan-400 uppercase"></p>

					<h2 id="agent-mode-title" class="mt-2 text-2xl font-semibold tracking-tight text-white">
						选择智能体
					</h2>

					<p class="mt-2 text-sm leading-6 text-gray-400">
						选择答疑、笔记本或测评功能，开始本次教学任务。
					</p>
				</div>

				<div class="w-full md:w-80">
					<label for="agent-model" class="mb-2 block text-xs font-medium text-gray-400">
						当前模型
					</label>

					<div class="relative">
						<select
							id="agent-model"
							class="h-12 w-full appearance-none rounded-xl border border-white/15 bg-white/[0.04] px-4 pr-11 text-sm text-gray-100 transition outline-none hover:border-white/25 focus:border-cyan-400 focus:ring-2 focus:ring-cyan-400/20"
							bind:value={selectedModelId}
						>
							{#each models as model (model.id)}
								<option value={model.id}>{model.name}</option>
							{/each}
						</select>

						<svg
							class="pointer-events-none absolute top-1/2 right-4 size-4 -translate-y-1/2 text-gray-500"
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="2"
							aria-hidden="true"
						>
							<path d="m6 9 6 6 6-6"></path>
						</svg>
					</div>
				</div>
			</div>

			<div class="mt-8 grid grid-cols-1 gap-5 md:grid-cols-3">
				{#each agents as agent (agent.type)}
					<button
						type="button"
						class={`group flex min-h-64 flex-col justify-between rounded-2xl border border-white/10 bg-white/[0.035] p-6 text-left shadow-2xl shadow-black/10 backdrop-blur-sm transition duration-300 hover:-translate-y-1 hover:bg-white/[0.055] hover:shadow-2xl focus:ring-2 focus:outline-none ${getCardHover(agent.accent)}`}
						onclick={() => selectAgent(agent.type)}
					>
						<div>
							<div
								class={`flex size-12 items-center justify-center rounded-xl ring-1 ${getIconBackground(agent.accent)}`}
							>
								{#if agent.type === 'qa'}
									<svg
										class="size-6"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.8"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M21 15a4 4 0 0 1-4 4H8l-5 3V7a4 4 0 0 1 4-4h10a4 4 0 0 1 4 4z"></path>
										<path d="M8 9h8M8 13h5"></path>
									</svg>
								{:else if agent.type === 'notebook'}
									<svg
										class="size-6"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.8"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M6 3h12a2 2 0 0 1 2 2v16H8a4 4 0 0 1-4-4V5a2 2 0 0 1 2-2z"></path>
										<path d="M8 3v18M11 8h6M11 12h6"></path>
									</svg>
								{:else}
									<svg
										class="size-6"
										viewBox="0 0 24 24"
										fill="none"
										stroke="currentColor"
										stroke-width="1.8"
										stroke-linecap="round"
										stroke-linejoin="round"
										aria-hidden="true"
									>
										<path d="M9 11l3 3L22 4"></path>
										<path d="M21 12v7a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11"></path>
									</svg>
								{/if}
							</div>

							<h3 class="mt-6 text-lg font-medium text-white">
								{agent.name}
							</h3>

							<p class="mt-2 text-sm leading-6 text-gray-400">
								{agent.description}
							</p>
						</div>

						<div class="mt-8 flex items-center justify-end">
							<span
								class="flex size-9 items-center justify-center rounded-full border border-white/10 text-gray-500 transition duration-300 group-hover:translate-x-1 group-hover:border-white/20 group-hover:text-white"
							>
								<svg
									class="size-4"
									viewBox="0 0 24 24"
									fill="none"
									stroke="currentColor"
									stroke-width="2"
									stroke-linecap="round"
									stroke-linejoin="round"
									aria-hidden="true"
								>
									<path d="M5 12h14M13 6l6 6-6 6"></path>
								</svg>
							</span>
						</div>
					</button>
				{/each}
			</div>

			<div class="mt-6 flex items-center gap-2 text-xs text-gray-600">
				<!-- 正常时不再常驻一行状态说明，只在读不到模型时提示；登记模型的入口一直在 -->
				{#if modelsError}
					<span class="size-1.5 rounded-full bg-amber-400"></span>
					<span>{modelsError}</span>
				{/if}
				<a
					href={resolve('/models')}
					class="ml-auto text-gray-500 underline-offset-2 transition hover:text-white hover:underline"
				>
					{models.length === 0 ? '去登记模型' : '登记 / 管理模型'}
				</a>
			</div>
		</section>
	</div>
</main>
