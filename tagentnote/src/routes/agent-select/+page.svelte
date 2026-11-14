<script lang="ts">
	import '$lib/styles/space-theme.css';
	import OrbitMark from '$lib/components/icons/OrbitMark.svelte';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	import { getAgentModels } from '$lib/apis/agent';

	type AgentType = 'qa' | 'notebook' | 'quiz';

	type AgentCard = {
		type: AgentType;
		name: string;
		description: string;
		action: string;
	};

	let models = $state<{ id: string; name: string }[]>([]);
	let selectedModelId = $state('');
	let modelsError = $state('');
	let modelsLoading = $state(true);

	onMount(() => {
		void getAgentModels()
			.then((list) => {
				models = list.data.map((model) => ({
					id: model.id,
					name: model.name || model.id
				}));
				selectedModelId = models[0]?.id ?? '';
				if (models.length === 0) {
					modelsError = '当前没有可用模型，请先登记模型。';
				}
			})
			.catch(() => {
				modelsError = '暂时无法读取模型列表，请确认模型服务已启动。';
			})
			.finally(() => {
				modelsLoading = false;
			});
	});

	const agents: AgentCard[] = [
		{
			type: 'qa',
			name: '课程答疑',
			description: '围绕课程提问、查阅引用，也可以分章写作和提交论文批改。',
			action: '进入答疑'
		},
		{
			type: 'notebook',
			name: '知识笔记本',
			description: '在 OpenNotebook 中整理笔记和课程资料。',
			action: '打开笔记本'
		},
		{
			type: 'quiz',
			name: '智能测评',
			description: '根据学习资料生成闪卡或整卷，练习后查看作答反馈。',
			action: '开始练习'
		}
	];

	const agentHref = (type: AgentType) => {
		if (type === 'notebook') {
			return resolve('/notebook');
		}

		// 模型列表还没回来时点进去：不带 model，到了那边按列表选默认的（别带一个空的 model=）
		const query = selectedModelId ? `?model=${encodeURIComponent(selectedModelId)}` : '';
		return resolve(`${type === 'quiz' ? '/exam' : '/qa'}${query}`);
	};
</script>

<svelte:head>
	<title>选择智能体 | 系统建模与仿真智能教学平台</title>
</svelte:head>

<div class="space-theme learning-page">
	<header class="topbar frame">
		<a class="brand" href={resolve('/space-exploration')}>
			<span class="brand-mark" aria-hidden="true">
				<OrbitMark />
			</span>
			航天探索实验室
		</a>
		<a class="home-link" href={resolve('/space-exploration')}>
			<svg
				viewBox="0 0 24 24"
				fill="none"
				stroke="currentColor"
				stroke-width="1.8"
				stroke-linecap="round"
				stroke-linejoin="round"
				aria-hidden="true"><path d="m10 6-6 6 6 6M4 12h16" /></svg
			>
			返回首页
		</a>
	</header>

	<main class="frame">
		<section class="course" aria-labelledby="course-title">
			<img class="course-image" src={resolve('/images/hubble-orbit.jpg')} alt="" />
			<div class="course-copy">
				<h1 id="course-title">系统建模与仿真</h1>
				<p>课程答疑、论文辅助、笔记整理与测评</p>
			</div>
		</section>

		<section class="workspace" aria-labelledby="agent-mode-title">
			<div class="workspace-heading">
				<h2 id="agent-mode-title">选择智能体</h2>
				<div class="model-field">
					<label for="agent-model">当前模型</label>
					<div class="model-select">
						<select
							id="agent-model"
							bind:value={selectedModelId}
							disabled={models.length === 0}
							aria-describedby={modelsError ? 'model-error' : undefined}
						>
							{#if models.length === 0}
								<option value="">{modelsLoading ? '正在加载模型…' : '暂无可用模型'}</option>
							{:else}
								{#each models as model (model.id)}
									<option value={model.id}>{model.name}</option>
								{/each}
							{/if}
						</select>
						<svg
							viewBox="0 0 24 24"
							fill="none"
							stroke="currentColor"
							stroke-width="1.8"
							stroke-linecap="round"
							stroke-linejoin="round"
							aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg
						>
					</div>
				</div>
			</div>
			{#if modelsError}
				<p class="model-error" id="model-error" role="status">{modelsError}</p>
			{/if}

			<div class="agent-list">
				{#each agents as agent (agent.type)}
					<a
						class="agent-card"
						href={agentHref(agent.type)}
						aria-label={agent.action}
						aria-describedby={`agent-description-${agent.type}`}
					>
						<div class="tool-mark" data-tool={agent.type}>
							{#if agent.type === 'qa'}
								<svg
									class="tool-icon"
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
									class="tool-icon"
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
									class="tool-icon"
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
						<div class="tool-content">
							<h3>{agent.name}</h3>
							<p id={`agent-description-${agent.type}`}>{agent.description}</p>
						</div>
						<span class="card-action" aria-hidden="true">
							{agent.action}
							<svg
								viewBox="0 0 24 24"
								fill="none"
								stroke="currentColor"
								stroke-width="1.8"
								stroke-linecap="round"
								stroke-linejoin="round"><path d="M5 12h14m-6-6 6 6-6 6" /></svg
							>
						</span>
					</a>
				{/each}
			</div>

			<div class="model-footer">
				<a href={resolve('/models')}>登记 / 管理模型</a>
			</div>
		</section>
	</main>
</div>

<style>
	.learning-page {
		min-height: 100dvh;
		background: var(--m3-background);
		color: var(--m3-on-surface);
		color-scheme: dark;
		font-family: var(--space-font);
	}

	.frame {
		width: min(1320px, calc(100% - 88px));
		margin-inline: auto;
	}

	.topbar {
		min-height: 76px;
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		border-bottom: 1px solid var(--m3-outline-variant);
	}

	.brand,
	.home-link {
		display: inline-flex;
		align-items: center;
		gap: 10px;
		font-size: 15px;
		font-weight: 600;
	}

	.brand-mark {
		display: grid;
		flex: none;
		width: 34px;
		height: 34px;
		place-items: center;
		border: 1px solid rgb(246 180 95 / 52%);
		border-radius: 50%;
		color: var(--space-amber);
		font-size: 21px;
	}

	.home-link {
		min-height: 44px;
		padding-inline: 14px;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 999px;
		color: var(--m3-on-surface-variant);
		font-size: 13px;
		font-weight: 500;
		white-space: nowrap;
		transition: background-color 180ms ease;
	}

	.home-link:hover {
		background: var(--m3-surface-high);
	}
	.home-link svg {
		width: 16px;
		height: 16px;
		color: var(--space-amber);
	}

	main {
		padding-block: 32px 48px;
	}

	.course {
		position: relative;
		isolation: isolate;
		display: flex;
		min-height: 238px;
		align-items: center;
		overflow: hidden;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 16px;
		background: #191724;
	}

	.course-image {
		position: absolute;
		z-index: -2;
		inset: 0 0 0 auto;
		width: 68%;
		height: 100%;
		object-fit: cover;
		object-position: center 56%;
	}

	.course::after {
		position: absolute;
		z-index: -1;
		inset: 0;
		background: linear-gradient(
			90deg,
			#191724 30%,
			rgb(25 23 36 / 88%) 42%,
			rgb(25 23 36 / 12%) 78%
		);
		content: '';
	}

	.course-copy {
		padding: 36px clamp(24px, 5vw, 64px);
	}

	h1 {
		margin: 0;
		font-size: clamp(29px, 3.5vw, 48px);
		font-weight: 500;
		line-height: 1.2;
		text-wrap: balance;
	}

	.course p {
		margin: 15px 0 0;
		color: var(--m3-on-surface-variant);
		font-size: 15px;
		line-height: 1.6;
	}

	.workspace {
		margin-top: 36px;
	}

	.workspace-heading {
		display: flex;
		align-items: end;
		justify-content: space-between;
		gap: 18px;
		margin-bottom: 18px;
	}

	h2 {
		margin: 0 0 4px;
		font-size: 27px;
		font-weight: 600;
		line-height: 1.3;
	}

	.model-field {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 10px 14px;
	}

	.model-field label,
	.model-error {
		color: var(--m3-on-surface-variant);
		font-size: 13px;
	}

	.model-select {
		position: relative;
	}

	.model-select select {
		width: min(230px, 100%);
		min-height: 44px;
		appearance: none;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 10px;
		background: var(--m3-surface-low);
		color: var(--m3-on-surface);
		padding: 8px 38px 8px 13px;
		font-size: 14px;
	}

	.model-select select:not(:disabled):hover {
		border-color: var(--m3-primary);
	}
	.model-select select:disabled {
		color: var(--m3-on-surface-variant);
	}
	.model-select svg {
		position: absolute;
		inset: 50% 13px auto auto;
		width: 16px;
		height: 16px;
		transform: translateY(-50%);
		pointer-events: none;
		color: var(--m3-on-surface-variant);
	}

	.model-error {
		margin: 0 0 16px;
		color: var(--space-amber);
	}

	.agent-list {
		display: grid;
		grid-template-columns: repeat(3, minmax(0, 1fr));
		gap: 16px;
	}

	.agent-card {
		display: flex;
		min-width: 0;
		flex-direction: column;
		gap: 18px;
		padding: 20px;
		border: 1px solid var(--m3-outline-variant);
		border-radius: 15px;
		background: var(--m3-surface-low);
		transition:
			background-color 180ms ease,
			border-color 180ms ease;
	}

	.agent-card:hover {
		border-color: var(--m3-primary);
		background: var(--m3-surface-high);
	}

	.tool-mark {
		--tool-accent: var(--m3-primary);
		display: grid;
		width: 44px;
		height: 44px;
		place-items: center;
		border: 1px solid color-mix(in srgb, var(--tool-accent), transparent 72%);
		border-radius: 12px;
		background: color-mix(in srgb, var(--tool-accent), transparent 90%);
		color: var(--tool-accent);
	}

	.tool-mark[data-tool='notebook'] {
		--tool-accent: var(--space-blue);
	}
	.tool-mark[data-tool='quiz'] {
		--tool-accent: var(--space-amber);
	}
	.tool-icon {
		width: 22px;
		height: 22px;
	}

	h3 {
		margin: 0;
		font-size: 20px;
		font-weight: 600;
		line-height: 1.4;
	}

	.tool-content p {
		margin: 7px 0 0;
		color: var(--m3-on-surface-variant);
		font-size: 14px;
		line-height: 1.65;
	}

	.card-action {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-top: auto;
		padding-top: 14px;
		border-top: 1px solid var(--m3-outline-variant);
		color: var(--m3-primary);
		font-size: 14px;
		font-weight: 600;
	}

	.card-action svg {
		width: 18px;
		height: 18px;
		transition: transform 180ms ease;
	}
	.agent-card:hover .card-action svg {
		transform: translateX(3px);
	}

	.model-footer {
		display: flex;
		justify-content: end;
		margin-top: 8px;
	}
	.model-footer a {
		display: inline-flex;
		min-height: 44px;
		align-items: center;
		color: var(--m3-on-surface-variant);
		font-size: 13px;
		text-underline-offset: 4px;
	}
	.model-footer a:hover {
		color: var(--m3-primary);
		text-decoration: underline;
	}

	a:focus-visible,
	select:focus-visible {
		outline: 2px solid var(--m3-primary);
		outline-offset: 3px;
	}
	.learning-page :global(::selection) {
		background: var(--m3-primary);
		color: var(--m3-on-primary);
	}

	@media (max-width: 820px) {
		.frame {
			width: calc(100% - 48px);
		}
		.agent-card {
			padding: 16px;
		}
	}

	@media (max-width: 650px) {
		.frame {
			width: calc(100% - 32px);
		}
		.topbar {
			min-height: 64px;
		}
		.brand {
			font-size: 14px;
		}
		main {
			padding-top: 20px;
		}
		.course {
			min-height: 196px;
		}
		.course-image {
			width: 100%;
		}
		.course::after {
			background: linear-gradient(
				90deg,
				rgb(25 23 36 / 98%),
				rgb(25 23 36 / 82%) 50%,
				rgb(25 23 36 / 34%)
			);
		}
		.workspace {
			margin-top: 27px;
		}
		.workspace-heading {
			align-items: start;
			flex-direction: column;
			gap: 12px;
		}
		.model-field {
			width: 100%;
			flex-wrap: nowrap;
		}
		.model-field label {
			flex: none;
		}
		.model-select {
			flex: 1;
			min-width: 0;
		}
		.model-select select {
			width: 100%;
		}
		.agent-list {
			grid-template-columns: 1fr;
			gap: 12px;
		}
		.agent-card {
			display: grid;
			grid-template-columns: auto minmax(0, 1fr);
			gap: 12px;
		}
		.card-action {
			grid-column: 2;
			padding-top: 10px;
		}
	}

	@media (prefers-reduced-motion: reduce) {
		.home-link,
		.agent-card,
		.card-action svg {
			transition: none;
		}
	}
</style>
