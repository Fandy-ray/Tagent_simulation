<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	let phase = $state(0); // 0=hidden, 1=badge, 2=title, 3=cta

	onMount(() => {
		const t1 = setTimeout(() => {
			phase = 1;
		}, 200);
		const t2 = setTimeout(() => {
			phase = 2;
		}, 600);
		const t3 = setTimeout(() => {
			phase = 3;
		}, 1100);

		return () => {
			clearTimeout(t1);
			clearTimeout(t2);
			clearTimeout(t3);
		};
	});
</script>

<svelte:head>
	<title>航空航天探索实验室</title>
</svelte:head>

<div class="wrap space-theme">
	<!-- animated grid canvas -->
	<div class="grid-layer" aria-hidden="true"></div>

	<!-- Orbital star map -->
	<svg
		class="nodes-svg"
		aria-hidden="true"
		viewBox="0 0 900 600"
		preserveAspectRatio="xMidYMid slice"
	>
		<defs>
			<filter id="glow">
				<feGaussianBlur stdDeviation="3" result="blur" />
				<feMerge><feMergeNode in="blur" /><feMergeNode in="SourceGraphic" /></feMerge>
			</filter>
		</defs>
		<g transform="rotate(-19 450 300)">
			<ellipse class="node-line" cx="450" cy="300" rx="375" ry="202" />
			<circle class="node-dot" cx="75" cy="300" r="4" filter="url(#glow)" />
			<circle class="node-dot" cx="450" cy="98" r="5" filter="url(#glow)" />
			<circle class="node-dot" cx="825" cy="300" r="6" filter="url(#glow)" />
			<circle class="node-dot" cx="450" cy="502" r="4" filter="url(#glow)" />
		</g>
		<g class="node-label">
			<text x="83" y="448" text-anchor="middle">仿真引擎</text>
			<text x="384" y="89" text-anchor="middle">系统模型</text>
			<text x="817" y="160" text-anchor="middle">知识图谱</text>
			<text x="516" y="522" text-anchor="middle">智能体</text>
		</g>
		<g class="distant-stars">
			<circle cx="195" cy="100" r="2" />
			<circle cx="694" cy="94" r="2.5" />
			<circle cx="774" cy="389" r="1.75" />
			<circle cx="230" cy="487" r="2.5" />
			<circle cx="577" cy="540" r="2" />
		</g>
	</svg>

	<!-- main content -->
	<div class="content">
		<div class="badge" class:show={phase >= 1}>
			<span class="badge-dot"></span>
			“AI+教育”创新应用技能大赛 · “高等教育-AI+教学”方向
		</div>

		<h1 class="title" class:show={phase >= 2}>
			航空航天<wbr />探索实验室
		</h1>

		<p class="subtitle" class:show={phase >= 2}>课程答疑 · 论文辅助 · 知识笔记本 · 智能测评</p>

		<button class="cta-btn" class:show={phase >= 3} onclick={() => goto(resolve('/agent-select'))}>
			<span class="cta-text">进入平台</span>
			<span class="cta-arrow">→</span>
		</button>
	</div>

	<!-- corner watermark -->
	<div class="watermark" class:show={phase >= 3}>航空航天探索实验室 v1.0</div>
</div>

<style>
	/* 不要写 :global(body) { overflow: hidden }：页面间跳转不刷新，全局样式会留着，
	   从这里点进去的页面（比如模型登记）就都滚不动了。铺满窗口、不滚动由这个容器自己管 */
	.wrap {
		position: fixed;
		inset: 0;
		background-color: var(--m3-background);
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}

	/* ── Grid layer ── */
	.grid-layer {
		position: absolute;
		inset: 0;
		background-image:
			linear-gradient(color-mix(in srgb, var(--m3-primary) 10%, transparent) 1px, transparent 1px),
			linear-gradient(90deg, color-mix(in srgb, var(--m3-primary) 10%, transparent) 1px, transparent 1px);
		background-size: 52px 52px;
		animation: grid-drift 18s linear infinite;
		pointer-events: none;
	}
	@keyframes grid-drift {
		from {
			background-position: 0 0;
		}
		to {
			background-position: 52px 52px;
		}
	}

	/* ── SVG decoration ── */
	.nodes-svg {
		position: absolute;
		inset: 0;
		width: 100%;
		height: 100%;
		pointer-events: none;
		opacity: 0.55;
	}
	.node-line {
		fill: none;
		stroke: color-mix(in srgb, var(--m3-primary) 30%, transparent);
		stroke-width: 1.5;
		stroke-dasharray: 8 4;
		animation: dash-flow 3s linear infinite;
	}
	@keyframes dash-flow {
		from {
			stroke-dashoffset: 24;
		}
		to {
			stroke-dashoffset: 0;
		}
	}
	.node-dot {
		fill: var(--m3-primary);
		animation: node-pulse 2.5s ease-in-out infinite alternate;
	}
	.node-dot:nth-child(odd) {
		animation-delay: -1.2s;
	}
	@keyframes node-pulse {
		from {
			opacity: 0.55;
		}
		to {
			opacity: 1;
		}
	}
	.distant-stars {
		fill: var(--m3-primary);
		opacity: 0.55;
	}

	.node-label {
		fill: var(--m3-on-surface-variant);
		font-size: 10px;
		opacity: 0.7;
	}

	/* ── Content panel ── */
	.content {
		position: relative;
		z-index: 10;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 24px;
		text-align: center;
		padding: 0 24px;
	}

	/* badge */
	.badge {
		display: flex;
		align-items: center;
		gap: 8px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-size: 0.78rem;
		letter-spacing: 0.04em;
		color: var(--m3-primary);
		background: color-mix(in srgb, var(--m3-primary) 7%, transparent);
		border: 1px solid color-mix(in srgb, var(--m3-primary) 22%, transparent);
		padding: 6px 16px;
		border-radius: 100px;
		opacity: 0;
		transform: translateY(-10px);
		transition:
			opacity 0.6s ease,
			transform 0.6s ease;
	}
	.badge.show {
		opacity: 1;
		transform: translateY(0);
	}
	.badge-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--m3-primary);
		box-shadow: 0 0 6px var(--m3-primary);
		animation: dot-blink 1.4s infinite;
	}
	@keyframes dot-blink {
		0%,
		100% {
			opacity: 1;
		}
		50% {
			opacity: 0.3;
		}
	}

	/* main title */
	.title {
		font-family: 'Songti SC', 'Noto Serif SC', 'Source Han Serif SC', serif;
		font-size: clamp(1.9rem, 5.5vw, 4.2rem);
		font-weight: 900;
		line-height: 1.15;
		letter-spacing: 0.06em;
		background: linear-gradient(135deg, #f5edff 0%, var(--m3-primary) 45%, #af95eb 100%);
		-webkit-background-clip: text;
		-webkit-text-fill-color: transparent;
		background-clip: text;
		margin: 0;
		opacity: 0;
		transform: translateY(28px);
		transition:
			opacity 0.8s cubic-bezier(0.22, 1, 0.36, 1),
			transform 0.8s cubic-bezier(0.22, 1, 0.36, 1);
		text-shadow: none;
	}
	.title.show {
		opacity: 1;
		transform: translateY(0);
	}

	/* subtitle */
	.subtitle {
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-size: 0.88rem;
		letter-spacing: 0.04em;
		color: var(--m3-on-surface-variant);
		margin: -10px 0 0;
		opacity: 0;
		transition: opacity 0.7s ease 0.15s;
	}
	.subtitle.show {
		opacity: 1;
	}

	/* CTA button */
	.cta-btn {
		display: flex;
		align-items: center;
		gap: 12px;
		padding: 14px 40px;
		border-radius: 12px;
		background: linear-gradient(135deg, var(--m3-primary), #b69aef);
		border: none;
		cursor: pointer;
		font-size: 1.05rem;
		font-weight: 700;
		font-family: 'Songti SC', 'Noto Serif SC', 'Source Han Serif SC', serif;
		color: var(--m3-on-primary);
		letter-spacing: 0.06em;
		box-shadow:
			0 0 24px color-mix(in srgb, var(--m3-primary) 24%, transparent),
			0 4px 20px rgba(0, 0, 0, 0.4);
		opacity: 0;
		transform: translateY(12px);
		transition:
			opacity 0.6s ease,
			transform 0.6s ease,
			filter 0.25s,
			box-shadow 0.25s;
	}
	.cta-btn.show {
		opacity: 1;
		transform: translateY(0);
	}
	.cta-btn:hover {
		filter: brightness(1.15);
		box-shadow:
			0 0 40px color-mix(in srgb, var(--m3-primary) 36%, transparent),
			0 8px 32px rgba(0, 0, 0, 0.5);
		transform: translateY(-3px);
	}
	.cta-btn:active {
		transform: translateY(0) scale(0.97);
	}
	.cta-arrow {
		font-size: 1.2rem;
		transition: transform 0.2s ease;
	}
	.cta-btn:hover .cta-arrow {
		transform: translateX(5px);
	}

	/* watermark */
	.watermark {
		position: absolute;
		bottom: 20px;
		right: 24px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		font-size: 0.7rem;
		color: #9a8da9;
		letter-spacing: 0.06em;
		opacity: 0;
		transition: opacity 1s ease 0.5s;
	}
	.watermark.show {
		opacity: 1;
	}
	:global(html.light) .title {
		background-image: linear-gradient(135deg, #153465, var(--m3-primary), #326a9e);
	}
	:global(html.light) .cta-btn {
		background: var(--m3-primary);
	}
	:global(html.light) .watermark {
		color: var(--m3-on-surface-variant);
	}
</style>
