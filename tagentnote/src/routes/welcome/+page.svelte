<script>
	import { goto } from '$app/navigation';
	import { resolve } from '$app/paths';
	import { onMount } from 'svelte';

	let phase = $state(0); // 0=hidden, 1=badge, 2=title, 3=cta

	onMount(() => {
		try {
			localStorage.setItem('theme', 'dark');
		} catch {
			// 本地存储不可用时保持当前主题
		}

		document.documentElement.classList.remove('light', 'dark', 'oled-dark', 'system');
		document.documentElement.classList.add('dark');

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
	<title>系统建模与仿真智能教学平台</title>
</svelte:head>

<div class="wrap">
	<!-- animated grid canvas -->
	<div class="grid-layer" aria-hidden="true"></div>

	<!-- SVG node-link decoration -->
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
		<!-- 节点只摆在外圈，连线也绕开正中间的文字区（画布里大约 x 280~620、y 190~410）。
		     原来「仿真引擎」「知识图谱」两个点正好落在大标题和比赛名称上 -->
		<!-- connector lines -->
		<line class="node-line" x1="120" y1="140" x2="170" y2="380" />
		<line class="node-line" x1="170" y1="380" x2="240" y2="520" />
		<line class="node-line" x1="120" y1="140" x2="760" y2="130" />
		<line class="node-line" x1="760" y1="130" x2="790" y2="400" />
		<line class="node-line" x1="790" y1="400" x2="650" y2="520" />
		<line class="node-line" x1="240" y1="520" x2="650" y2="520" />
		<!-- nodes -->
		<circle class="node-dot" cx="120" cy="140" r="7" filter="url(#glow)" />
		<circle class="node-dot" cx="170" cy="380" r="10" filter="url(#glow)" />
		<circle class="node-dot" cx="760" cy="130" r="8" filter="url(#glow)" />
		<circle class="node-dot" cx="790" cy="400" r="6" filter="url(#glow)" />
		<circle class="node-dot" cx="240" cy="520" r="6" filter="url(#glow)" />
		<circle class="node-dot" cx="650" cy="520" r="7" filter="url(#glow)" />
		<!-- labels -->
		<text class="node-label" x="100" y="125">系统模型</text>
		<text class="node-label" x="80" y="410">仿真引擎</text>
		<text class="node-label" x="735" y="115">知识图谱</text>
		<text class="node-label" x="805" y="405">智能体</text>
	</svg>

	<!-- main content -->
	<div class="content">
		<div class="badge" class:show={phase >= 1}>
			<span class="badge-dot"></span>
			“AI+教育”创新应用技能大赛 · “高等教育-AI+教学”方向
		</div>

		<h1 class="title" class:show={phase >= 2}>
			系统建模与仿真<br />智能教学平台
		</h1>

		<p class="subtitle" class:show={phase >= 2}>课程答疑 · 论文辅助 · 知识笔记本 · 智能测评</p>

		<button class="cta-btn" class:show={phase >= 3} onclick={() => goto(resolve('/agent-select'))}>
			<span class="cta-text">进入平台</span>
			<span class="cta-arrow">→</span>
		</button>
	</div>

	<!-- corner watermark -->
	<div class="watermark" class:show={phase >= 3}>系统建模与仿真智能体 v1.0</div>
</div>

<style>
	/* 不要写 :global(body) { overflow: hidden }：页面间跳转不刷新，全局样式会留着，
	   从这里点进去的页面（比如模型登记）就都滚不动了。铺满窗口、不滚动由这个容器自己管 */
	.wrap {
		position: fixed;
		inset: 0;
		background-color: #050d1a;
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
			linear-gradient(rgba(80, 140, 255, 0.1) 1px, transparent 1px),
			linear-gradient(90deg, rgba(80, 140, 255, 0.1) 1px, transparent 1px);
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
		stroke: rgba(80, 180, 255, 0.3);
		stroke-width: 1.5;
		stroke-dasharray: 8 4;
		animation: dash-flow 3s linear infinite;
	}
	.node-line:nth-child(2) {
		animation-delay: -0.8s;
	}
	.node-line:nth-child(3) {
		animation-delay: -1.5s;
	}
	.node-line:nth-child(4) {
		animation-delay: -2.2s;
	}
	.node-line:nth-child(5) {
		animation-delay: -0.4s;
	}
	.node-line:nth-child(6) {
		animation-delay: -1.1s;
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
		fill: rgba(0, 230, 255, 0.85);
		animation: node-pulse 2.5s ease-in-out infinite alternate;
	}
	.node-dot:nth-child(odd) {
		animation-delay: -1.2s;
	}
	@keyframes node-pulse {
		from {
			opacity: 0.55;
			r: 6;
		}
		to {
			opacity: 1;
			r: 9;
		}
	}
	.node-label {
		fill: rgba(0, 200, 255, 0.45);
		font-size: 11px;
		font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
		letter-spacing: 0.05em;
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
		color: rgba(0, 230, 255, 0.8);
		background: rgba(0, 230, 255, 0.07);
		border: 1px solid rgba(0, 230, 255, 0.22);
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
		background: #00e5ff;
		box-shadow: 0 0 6px #00e5ff;
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
		font-size: clamp(2.4rem, 5.5vw, 4.2rem);
		font-weight: 900;
		line-height: 1.15;
		letter-spacing: 0.06em;
		background: linear-gradient(135deg, #e0f4ff 0%, #00e5ff 45%, #6c8eff 100%);
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
		color: rgba(140, 180, 220, 0.75);
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
		background: linear-gradient(135deg, #00c8e8, #4060f0);
		border: none;
		cursor: pointer;
		font-size: 1.05rem;
		font-weight: 700;
		font-family: 'Songti SC', 'Noto Serif SC', 'Source Han Serif SC', serif;
		color: #030c18;
		letter-spacing: 0.06em;
		box-shadow:
			0 0 24px rgba(0, 200, 240, 0.3),
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
			0 0 40px rgba(0, 200, 240, 0.5),
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
		color: rgba(80, 140, 200, 0.35);
		letter-spacing: 0.06em;
		opacity: 0;
		transition: opacity 1s ease 0.5s;
	}
	.watermark.show {
		opacity: 1;
	}
</style>
