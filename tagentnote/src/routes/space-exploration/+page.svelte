<script lang="ts">
	let activeLesson = $state<string | null>(null);
	let launchSpeed = $state(72);
	let launchAngle = $state(48);
	let atmosphere = $state(38);
	let isRunning = $state(false);
	let runCount = $state(0);

	const backgroundStars = [
		{ x: 5, y: 14, delay: 0.2, duration: 5.4, bright: true },
		{ x: 12, y: 38, delay: 2.1, duration: 6.2 },
		{ x: 18, y: 78, delay: 1.4, duration: 4.9 },
		{ x: 24, y: 22, delay: 3.7, duration: 7.1, bright: true },
		{ x: 29, y: 61, delay: 0.8, duration: 5.7 },
		{ x: 34, y: 91, delay: 4.4, duration: 6.8 },
		{ x: 39, y: 43, delay: 2.8, duration: 5.1, bright: true },
		{ x: 44, y: 12, delay: 5.2, duration: 7.4 },
		{ x: 49, y: 71, delay: 1.7, duration: 5.9 },
		{ x: 54, y: 31, delay: 3.1, duration: 6.5, bright: true },
		{ x: 59, y: 85, delay: 0.5, duration: 5.3 },
		{ x: 64, y: 55, delay: 4.8, duration: 7.2 },
		{ x: 69, y: 17, delay: 2.5, duration: 5.6, bright: true },
		{ x: 74, y: 68, delay: 5.7, duration: 6.1 },
		{ x: 79, y: 37, delay: 1.1, duration: 7.6 },
		{ x: 84, y: 88, delay: 3.4, duration: 5.2, bright: true },
		{ x: 89, y: 25, delay: 0.9, duration: 6.7 },
		{ x: 94, y: 58, delay: 4.1, duration: 5.8 },
		{ x: 8, y: 55, delay: 3.9, duration: 7.3 },
		{ x: 31, y: 7, delay: 1.9, duration: 5.5 },
		{ x: 47, y: 96, delay: 5.4, duration: 6.4 },
		{ x: 72, y: 48, delay: 2.3, duration: 5.0 },
		{ x: 96, y: 9, delay: 0.6, duration: 7.0, bright: true },
		{ x: 16, y: 93, delay: 4.6, duration: 6.0 }
	];

	const meteorTrails = [
		{ x: 93, y: 3, width: 132, dx: -340, dy: 280, angle: -35, delay: 0 },
		{ x: 79, y: 16, width: 112, dx: -300, dy: 250, angle: -38, delay: 2 },
		{ x: 66, y: 7, width: 142, dx: -360, dy: 290, angle: -33, delay: 4 },
		{ x: 48, y: 21, width: 108, dx: -290, dy: 240, angle: -37, delay: 6 },
		{ x: 35, y: 9, width: 126, dx: -320, dy: 270, angle: -34, delay: 8 }
	];

	const lessons = [
		{
			level: '小学',
			title: '火箭为什么能回来？',
			copy: '观察火箭回收的过程，试着调整条件，看看怎样才能更稳定地落回地面。',
			tag: '火箭回收',
			kind: 'rocket'
		},
		{
			level: '初中',
			title: '什么会改变卫星轨道？',
			copy: '调整轨道高度、速度等条件，探索它们如何影响卫星的运行轨道。',
			tag: '卫星轨道',
			kind: 'orbit'
		},
		{
			level: '高中',
			title: '速度变化会带来什么影响？',
			copy: '设置速度变化的时机与幅度，观察轨道如何改变，分析其中的规律。',
			tag: '速度与轨道',
			kind: 'velocity'
		}
	];

	function openSimulation(lesson?: string) {
		activeLesson = lesson ?? '轨道高度';
		isRunning = false;
	}

	function runSimulation() {
		isRunning = !isRunning;
		if (isRunning) runCount += 1;
	}

	function handleKeydown(event: KeyboardEvent) {
		if (event.key === 'Escape' && activeLesson) activeLesson = null;
	}
</script>

<svelte:window onkeydown={handleKeydown} />

<svelte:head>
	<title>航天探索实验室 · 把问题变成一次亲手探索</title>
	<meta
		name="description"
		content="面向中小学生的航天科普智能体。调整条件、运行模拟，在探索中理解航天。"
	/>
</svelte:head>

<div class="space-page">
	<div class="cosmic-layer" aria-hidden="true">
		{#each backgroundStars as star}
			<span
				class="twinkle-star"
				class:bright={star.bright}
				style={`--star-x:${star.x}%;--star-y:${star.y}%;--star-delay:${star.delay}s;--star-duration:${star.duration}s`}
			></span>
		{/each}
		{#each meteorTrails as meteor}
			<span
				class="meteor"
				style={`--meteor-x:${meteor.x}%;--meteor-y:${meteor.y}%;--meteor-width:${meteor.width}px;--meteor-dx:${meteor.dx}px;--meteor-dy:${meteor.dy}px;--meteor-angle:${meteor.angle}deg;--meteor-delay:${meteor.delay}s`}
			></span>
		{/each}
	</div>
	<header class="topbar">
		<a class="brand" href="#top" aria-label="航天探索实验室首页">
			<span class="brand-mark" aria-hidden="true">
				<svg viewBox="0 0 32 32" fill="none"><path d="M16 3.5c5 3.6 8.3 8.1 8.3 13.2S21 26.4 16 28.5c-5-2.1-8.3-6.7-8.3-11.8S11 7.1 16 3.5Z"/><path d="M4.3 16.7c3.6-5 8.1-8.3 13.2-8.3s9.7 3.3 11.8 8.3c-2.1 5-6.7 8.3-11.8 8.3S7.9 21.7 4.3 16.7Z"/><circle cx="16" cy="16.5" r="2.2"/></svg>
			</span>
			<span>航天探索实验室</span>
		</a>
		<nav class="topnav" aria-label="页面导航">
			<a href="#lessons">学习场景</a>
			<a href="#about">关于项目</a>
		</nav>
		<button class="top-cta" onclick={() => openSimulation()}>开始探索 <span aria-hidden="true">↗</span></button>
	</header>

	<main id="top">
		<section class="hero" aria-labelledby="hero-title">
			<div class="hero-copy">
				<p class="eyebrow"><span class="live-dot"></span> 面向中小学生的航天科普智能体</p>
				<h1 id="hero-title">把一个航天问题，<br /><span>变成一次亲手探索</span></h1>
				<p class="hero-summary">从小学到高中，跟着一个航天问题，看懂过程、尝试调整、检验自己的想法。</p>

				<div class="hero-actions">
					<button class="primary-button" onclick={() => openSimulation()}>开始体验</button>
					<p class="status-note"><span class="status-mark" aria-hidden="true">✳</span><span>当前体验课程：系统建模与仿真<br />航天主题体验仍在项目规划中</span></p>
				</div>
			</div>

			<div class="hero-art" aria-label="哈勃望远镜在地球轨道上运行的实拍图">
				<img class="hero-image" src="/images/hubble-orbit.jpg" alt="哈勃太空望远镜漂浮在地球轨道上方" />
				<div class="art-topline"><span>ORBITAL LAB · 01</span><span>北纬 39°54′</span></div>
				<div class="orbit orbit-one"></div><div class="orbit orbit-two"></div>
				<div class="earth"><div class="earth-glow"></div><div class="earth-land land-one"></div><div class="earth-land land-two"></div></div>
				<div class="launch-trail"></div>
				<div class="rocket" aria-hidden="true">
					<svg viewBox="0 0 64 112" fill="none"><path d="M32 5C20 17 18 37 20 61l12 14 12-14C46 37 44 17 32 5Z" fill="#E9EEF8"/><path d="M32 5C20 17 18 37 20 61l12 14V5Z" fill="#B9C9E1"/><path d="M20 53 8 68v18l15-12M44 53l12 15v18L41 74" fill="#EB8C50"/><circle cx="32" cy="35" r="6" fill="#326F9C" stroke="#D8F2FF" stroke-width="3"/><path d="M25 76h14l-3 14h-8l-3-14Z" fill="#D0BCFF"/><path d="M28 89h8l-4 19-4-19Z" fill="#FFB05D"/><path d="m30 91 2 13 2-13" fill="#FFF1C6"/></svg>
				</div>
				<div class="art-caption"><span class="caption-point"></span><span>近地轨道 · 模拟任务</span><span class="caption-coord">高度 408 km</span></div>
				<div class="art-index">地球<br />01 / 03</div>
			</div>
		</section>

		<section class="lesson-section" id="lessons" aria-labelledby="lesson-title">
			<div class="section-heading">
				<div><p class="eyebrow section-eyebrow">从好奇出发，逐步看懂航天</p><h2 id="lesson-title">挑一个问题，开始你的探索</h2></div>
				<p>围绕你感兴趣的航天问题，在探索中积累知识，发现航天世界的奥妙与魅力。</p>
			</div>

			<div class="lesson-list">
				{#each lessons as lesson, index}
					<article class="lesson-card">
						<div class="lesson-title-row">
							<span class="grade-tag">{lesson.level}</span>
							<h3>{lesson.title}</h3>
							<span class="lesson-index">0{index + 1}</span>
						</div>
						<button class="scene-button" aria-label="体验：{lesson.title}" onclick={() => openSimulation(lesson.title)}>
							{#if lesson.kind === 'rocket'}
								<svg class="scene-svg" viewBox="0 0 560 220" role="img" aria-label="火箭从发射台升空">
									<defs><linearGradient id="sky-a" x2="0" y2="1"><stop stop-color="#173967"/><stop offset="1" stop-color="#397EB5"/></linearGradient></defs>
									<rect width="560" height="220" fill="url(#sky-a)"/><circle cx="420" cy="42" r="1.5" fill="#D9E8FF"/><circle cx="108" cy="51" r="1" fill="#D9E8FF"/><path d="M0 166c64-31 105-17 158-4 73 18 122-19 182-12 67 8 120 46 220 11v59H0Z" fill="#82A9C9" opacity=".42"/>
									<path d="M88 202h382" stroke="#D3E5EE" stroke-opacity=".5"/><path d="M278 195 295 73l16 122" fill="#53687C"/><path d="m278 195 18-122 2 122" fill="#8193A1"/><path d="M287 113h18M285 144h22M281 176h28" stroke="#D1D9DB" stroke-width="3"/><path d="M300 73V50" stroke="#E8F0F6" stroke-width="2" stroke-dasharray="3 6"/><path d="M305 66c31-42 87-36 118-8" stroke="#FFB765" stroke-width="2" stroke-dasharray="4 7"/><circle cx="420" cy="58" r="3" fill="#FFE3A6"/><path d="M293 191c-16 13-18 20-16 27 8-6 16-7 24-2 3-6 2-15-8-25Z" fill="#FFA64D"/>
									<rect x="28" y="22" width="98" height="25" rx="12.5" fill="#122C4D" fill-opacity=".8"/><text x="44" y="39" fill="#D7E8F8" font-size="11" font-family="sans-serif">RETURN PATH</text>
								</svg>
							{:else if lesson.kind === 'orbit'}
								<svg class="scene-svg" viewBox="0 0 560 220" role="img" aria-label="卫星围绕地球运行">
									<defs><linearGradient id="sky-b" x2="1" y2="1"><stop stop-color="#112B50"/><stop offset="1" stop-color="#184B79"/></linearGradient><radialGradient id="planet-b"><stop stop-color="#78D0FA"/><stop offset=".8" stop-color="#3576B9"/><stop offset="1" stop-color="#1E4A84"/></radialGradient></defs>
									<rect width="560" height="220" fill="url(#sky-b)"/><circle cx="271" cy="127" r="58" fill="url(#planet-b)"/><path d="M239 81c12-13 25-10 32 0l-10 11-22-1Zm54 37 25 8 8 19-17 9-12-13-12-4Zm-70 31 25-9 13 12-6 21-23 5-15-15Z" fill="#71B8B4" opacity=".8"/><ellipse cx="271" cy="127" rx="122" ry="49" transform="rotate(-24 271 127)" stroke="#FFF0BF" stroke-width="2" stroke-dasharray="6 7"/><ellipse cx="271" cy="127" rx="164" ry="67" transform="rotate(-24 271 127)" stroke="#65C8F2" stroke-opacity=".6"/><circle cx="411" cy="69" r="5" fill="#FFD071"/><path d="m406 64-10-9m17 9 10-9m-13 20-4 11m12-12 9 5" stroke="#EAF4FC" stroke-width="2"/><circle cx="97" cy="48" r="1.3" fill="white"/><circle cx="459" cy="163" r="1.5" fill="white"/><circle cx="161" cy="171" r="1" fill="white"/>
									</svg>
							{:else}
								<svg class="scene-svg" viewBox="0 0 560 220" role="img" aria-label="速度变化让卫星进入新的轨道">
									<defs><linearGradient id="sky-c" x2="1" y2="1"><stop stop-color="#192E55"/><stop offset="1" stop-color="#315B89"/></linearGradient></defs>
									<rect width="560" height="220" fill="url(#sky-c)"/><circle cx="199" cy="181" r="93" fill="#337AB3"/><path d="M142 115c26-17 40-8 46 0l-19 19-30-2Zm65 37 27 12-12 22-29-5-10-16Zm-81 38 29-21 19 17-9 25h-35Z" fill="#71B9A5"/><path d="M93 123c49-79 174-91 238-21 50 55-9 100-65 58-34-25-70-38-102-24" fill="none" stroke="#F8D56E" stroke-width="2.4"/><path d="M107 151c50-56 125-59 170-18" fill="none" stroke="#DDEBFA" stroke-width="1.5" stroke-dasharray="5 6"/><circle cx="334" cy="84" r="4" fill="#FFE27E"/><rect x="384" y="28" width="139" height="165" rx="9" fill="#102949" stroke="#7DA6C7" stroke-opacity=".6"/><path d="M400 155h107M400 111h107M400 67h107" stroke="#6685A2" stroke-opacity=".3"/><path d="m402 144 20-2 18-31 19 3 19-51 23-2" fill="none" stroke="#F8C95D" stroke-width="2.5"/><path d="M402 153v-90" stroke="#B8D0E8" stroke-opacity=".5"/><text x="400" y="49" fill="#DCEBFA" font-size="10" font-family="sans-serif">速度变化</text>
									</svg>
							{/if}
							<span class="scene-label">{lesson.tag}<span aria-hidden="true">↗</span></span>
						</button>
						<p class="lesson-copy">{lesson.copy}</p>
					</article>
				{/each}
			</div>
		</section>

		<section class="closing" id="about">
			<div class="closing-star" aria-hidden="true">✳</div>
			<div><h2>从好奇出发，逐步看懂航天</h2><p>沿着一个问题走进去，把每一次观察都变成下一次发现。</p></div>
			<button class="text-button" onclick={() => openSimulation()}>进入探索 <span aria-hidden="true">→</span></button>
		</section>
	</main>

	<footer class="footer"><span>航天探索实验室</span><span>学习场景构想 · 课程内容以项目规划为准</span><span>EARTH · ORBIT · DISCOVERY</span></footer>
</div>

{#if activeLesson}
	<div class="dialog-scrim" role="presentation" onclick={(event) => event.target === event.currentTarget && (activeLesson = null)}>
		<dialog class="simulation-dialog" open aria-modal="true" aria-labelledby="sim-title">
			<div class="dialog-heading"><div><p class="eyebrow">探索与尝试 · 模拟实验</p><h2 id="sim-title">{activeLesson}</h2></div><button class="close-button" aria-label="关闭模拟实验" onclick={() => (activeLesson = null)}>×</button></div>
			<div class="sim-content">
				<div class="sim-visual" class:running={isRunning}>
					<div class="sim-stars"></div><div class="sim-planet"></div><div class="sim-orbit-path"></div><div class="sim-satellite"><span></span></div>
					<div class="sim-readout"><span>近地点</span><b>{Math.round(220 + launchSpeed * 4.1)} km</b></div>
					<div class="sim-readout right"><span>轨道周期</span><b>{Math.round(88 + launchAngle * 0.16)} 分钟</b></div>
				</div>
				<div class="sim-controls">
					<label><span>初始速度 <output>{launchSpeed} %</output></span><input type="range" min="20" max="100" bind:value={launchSpeed} aria-label="初始速度" /></label>
					<label><span>飞行角度 <output>{launchAngle}°</output></span><input type="range" min="10" max="80" bind:value={launchAngle} aria-label="飞行角度" /></label>
					<label><span>大气密度 <output>{atmosphere} %</output></span><input type="range" min="0" max="100" bind:value={atmosphere} aria-label="大气密度" /></label>
					<div class="sim-actions"><p>{runCount > 0 ? `已运行 ${runCount} 次 · 调整参数，再观察变化` : '调整参数，再运行模拟观察轨道变化'}</p><button class="run-button" onclick={runSimulation}><span aria-hidden="true">{isRunning ? 'Ⅱ' : '▶'}</span>{isRunning ? '暂停模拟' : '运行模拟'}</button></div>
				</div>
			</div>
			<p class="demo-note">模拟演示 · 结果为示意数据，用于观察参数变化关系</p>
		</dialog>
	</div>
{/if}

<style>
	.space-page {
		/* Material 3 Typescale / Baseline; source styles use Roboto and these five metrics. */
		--m3-display-large: 400 57px/64px Roboto, 'Noto Sans SC', sans-serif;
		--m3-display-large-emphasized: 500 57px/64px Roboto, 'Noto Sans SC', sans-serif;
		--m3-display-medium: 400 45px/52px Roboto, 'Noto Sans SC', sans-serif;
		--m3-display-medium-emphasized: 500 45px/52px Roboto, 'Noto Sans SC', sans-serif;
		--m3-display-small: 400 36px/44px Roboto, 'Noto Sans SC', sans-serif;
		--m3-display-small-emphasized: 500 36px/44px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-large: 400 32px/40px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-large-emphasized: 500 32px/40px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-medium: 400 28px/36px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-medium-emphasized: 500 28px/36px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-small: 400 24px/32px Roboto, 'Noto Sans SC', sans-serif;
		--m3-headline-small-emphasized: 500 24px/32px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-large: 400 22px/28px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-large-emphasized: 500 22px/28px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-medium: 500 16px/24px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-medium-emphasized: 600 16px/24px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-small: 500 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-title-small-emphasized: 600 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-large: 500 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-large-emphasized: 600 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-medium: 500 12px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-medium-emphasized: 600 12px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-small: 500 11px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-label-small-emphasized: 600 11px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-large: 400 16px/24px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-large-emphasized: 500 16px/24px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-medium: 400 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-medium-emphasized: 500 14px/20px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-small: 400 12px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-body-small-emphasized: 500 12px/16px Roboto, 'Noto Sans SC', sans-serif;
		--m3-tracking-display-large: -0.25px;
		--m3-tracking-display-medium: 0px;
		--m3-tracking-display-small: 0px;
		--m3-tracking-headline: 0px;
		--m3-tracking-title-large: 0px;
		--m3-tracking-title-medium: 0.15px;
		--m3-tracking-title-small: 0.1px;
		--m3-tracking-label-large: 0.1px;
		--m3-tracking-label-medium: 0.5px;
		--m3-tracking-label-small: 0.5px;
		--m3-tracking-body-large: 0.5px;
		--m3-tracking-body-medium: 0.25px;
		--m3-tracking-body-small: 0.4px;
		--m3-background: #141218;
		--m3-surface: #141218;
		--m3-surface-low: #1d1b20;
		--m3-surface-container: #211f26;
		--m3-surface-high: #2b2930;
		--m3-on-surface: #e6e0e9;
		--m3-on-surface-variant: #cac4d0;
		--m3-outline: #938f99;
		--m3-outline-variant: #49454f;
		--m3-primary: #d0bcff;
		--m3-on-primary: #381e72;
		--m3-state-on-primary-08: rgb(56 30 114 / 8%);
		--m3-primary-container: #4f378b;
		--m3-on-primary-container: #eaddff;
		--m3-secondary-container: #4a4458;
		--m3-on-secondary-container: #e8def8;
		--m3-inverse-surface: #e6e0e9;
		--m3-inverse-on-surface: #322f35;
		--space-amber: #f6b45f;
		--space-blue: #55a9d7;
		min-height: 100vh;
		position: relative;
		isolation: isolate;
		background-color: var(--m3-background);
		background-image: url('../../lib/assets/starfield.png');
		background-position: center top;
		background-size: cover;
		background-attachment: fixed;
		background-repeat: no-repeat;
		color: var(--m3-on-surface);
		font-family: Roboto, 'Noto Sans SC', 'Microsoft YaHei', sans-serif;
		font-synthesis: none;
		text-rendering: optimizeLegibility;
	}
	.space-page :global(*) { box-sizing: border-box; }
	.space-page :global(button), .space-page :global(a) { -webkit-tap-highlight-color: transparent; }
	.space-page :global(button:focus-visible), .space-page :global(a:focus-visible), .space-page :global(input:focus-visible) { outline: 3px solid var(--m3-primary); outline-offset: 3px; }
	.space-page :global(::selection) { color: var(--m3-on-primary); background: var(--m3-primary); }
	.cosmic-layer { position: fixed; z-index: 0; inset: 0; overflow: hidden; pointer-events: none; }
	.twinkle-star { position: absolute; left: var(--star-x); top: var(--star-y); width: 2px; height: 2px; border-radius: 50%; background: #eaf4ff; opacity: .24; box-shadow: 0 0 5px 1px rgb(159 207 255 / 45%); animation: star-twinkle var(--star-duration) ease-in-out var(--star-delay) infinite; }
	.twinkle-star.bright { width: 3px; height: 3px; background: #fff2c9; box-shadow: 0 0 8px 2px rgb(255 205 125 / 55%); }
	.meteor { position: absolute; left: var(--meteor-x); top: var(--meteor-y); width: var(--meteor-width); height: 1.5px; border-radius: 50%; opacity: 0; background: linear-gradient(90deg, transparent 0%, rgb(203 231 255 / 30%) 28%, #fff4d6 82%, transparent 100%); box-shadow: 0 0 8px 1px rgb(137 197 255 / 35%); transform: translate3d(0, 0, 0) rotate(var(--meteor-angle)); animation: meteor-sweep 10s linear var(--meteor-delay) infinite; }
	@keyframes star-twinkle { 0%, 100% { opacity: .2; transform: scale(.78); } 50% { opacity: .88; transform: scale(1.3); } }
	@keyframes meteor-sweep { 0%, 4% { opacity: 0; transform: translate3d(0, 0, 0) rotate(var(--meteor-angle)); } 6% { opacity: .92; } 15% { opacity: 0; transform: translate3d(var(--meteor-dx), var(--meteor-dy), 0) rotate(var(--meteor-angle)); } 100% { opacity: 0; transform: translate3d(var(--meteor-dx), var(--meteor-dy), 0) rotate(var(--meteor-angle)); } }
	@media (prefers-reduced-motion: reduce) {
		.twinkle-star { animation-name: star-twinkle-reduced; animation-duration: 12s; }
		.meteor { animation: none; opacity: 0; }
	}
	@keyframes star-twinkle-reduced { 0%, 100% { opacity: .34; } 50% { opacity: .72; } }
	.topbar, main, .footer { position: relative; z-index: 1; width: min(1320px, calc(100% - 88px)); margin-inline: auto; }
	.topbar { height: 76px; display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid color-mix(in srgb, var(--m3-outline-variant), transparent 35%); }
	.brand { display: inline-flex; align-items: center; gap: 11px; color: var(--m3-on-surface); text-decoration: none; font-size: 15px; font-weight: 600; letter-spacing: .01em; }
	.brand-mark { width: 34px; height: 34px; display: grid; place-items: center; color: var(--space-amber); border: 1px solid color-mix(in srgb, var(--space-amber), transparent 48%); border-radius: 50%; }
	.brand-mark svg { width: 21px; height: 21px; stroke: currentColor; stroke-width: 1.2; }
	.topnav { display: flex; gap: 36px; margin-left: 8%; }
	.topnav a, .top-cta { color: var(--m3-on-surface-variant); text-decoration: none; font: 500 13px/20px Roboto, 'Noto Sans SC', sans-serif; transition: color .18s ease, background-color .18s ease; }
	.topnav a:hover { color: var(--m3-on-surface); }
	.top-cta { border: 1px solid var(--m3-outline); border-radius: 999px; background: transparent; padding: 9px 17px; color: var(--m3-on-surface); cursor: pointer; }
	.top-cta span { color: var(--space-amber); margin-left: 6px; }
	.top-cta:hover { background: var(--m3-surface-high); }
	.hero { display: grid; grid-template-columns: 1.03fr .97fr; align-items: center; gap: clamp(32px, 5.5vw, 86px); padding: 68px 0 72px; }
	.hero-copy { min-width: 0; }
	.eyebrow { display: flex; align-items: center; gap: 9px; margin: 0 0 20px; color: var(--m3-on-surface-variant); font-size: 12px; line-height: 18px; letter-spacing: .08em; }
	.live-dot, .caption-point { width: 7px; height: 7px; border-radius: 50%; background: var(--space-amber); box-shadow: 0 0 12px color-mix(in srgb, var(--space-amber), transparent 30%); }
	h1 { margin: 0; max-width: 690px; font: var(--m3-display-large-emphasized); letter-spacing: var(--m3-tracking-display-large); }
	h1 span { color: var(--m3-on-surface); text-decoration: underline; text-decoration-color: var(--space-amber); text-decoration-thickness: 2px; text-underline-offset: 9px; }
	.hero-summary { max-width: 550px; margin: 22px 0 28px; color: var(--m3-on-surface-variant); font: var(--m3-body-large); letter-spacing: var(--m3-tracking-body-large); }
	.hero-actions { display: flex; align-items: center; gap: 24px; }
	.primary-button { display: inline-flex; align-items: center; justify-content: center; min-height: 66px; padding: 0 32px; border: 1px solid rgb(220 239 255 / 52%); border-radius: 16px; color: #f4f8ff; background: linear-gradient(135deg, rgb(235 246 255 / 19%), rgb(117 170 214 / 11%)); box-shadow: inset 0 1px 0 rgb(255 255 255 / 28%), 0 14px 38px rgb(8 27 48 / 34%); backdrop-filter: blur(18px) saturate(145%); -webkit-backdrop-filter: blur(18px) saturate(145%); font: var(--m3-title-large-emphasized); letter-spacing: var(--m3-tracking-title-large); cursor: pointer; transition: transform .18s ease, box-shadow .18s ease, border-color .18s ease; }
	@media (hover: hover) and (pointer: fine) { .primary-button:hover { transform: translateY(-2px); border-color: rgb(235 246 255 / 78%); box-shadow: inset 0 1px 0 rgb(255 255 255 / 42%), 0 18px 44px rgb(8 27 48 / 45%); } }
	.status-note { display: flex; align-items: center; gap: 10px; margin: 0; padding-left: 18px; border-left: 1px solid var(--m3-outline-variant); color: var(--m3-on-surface-variant); font-size: 11px; line-height: 1.65; }
	.status-mark { color: var(--space-amber); font-size: 17px; }
	.hero-art { min-height: 435px; position: relative; overflow: hidden; border-radius: 20px; border: 1px solid #6584a4; background: #0d1c32; isolation: isolate; }
	.hero-image { position: absolute; z-index: -2; inset: 0; width: 100%; height: 100%; object-fit: cover; object-position: center 58%; }
	.hero-art::before { content: ''; position: absolute; inset: 0; background: radial-gradient(circle at 15% 20%, #fff 0 1px, transparent 1.6px), radial-gradient(circle at 58% 18%, #fff 0 .8px, transparent 1.5px), radial-gradient(circle at 80% 34%, #fff 0 1px, transparent 1.8px), radial-gradient(circle at 28% 56%, #fff 0 .7px, transparent 1.6px), radial-gradient(circle at 92% 65%, #fff 0 1px, transparent 1.7px), radial-gradient(circle at 48% 36%, #fff 0 .8px, transparent 1.6px); opacity: .72; z-index: -1; }
	.art-topline { position: absolute; left: 23px; right: 23px; top: 19px; display: flex; justify-content: space-between; color: #a8bed6; font: 10px/1.4 Roboto, sans-serif; letter-spacing: .14em; }
	.orbit { position: absolute; left: 52%; top: 64%; width: 115%; height: 34%; border: 1px solid #9bc5e2aa; border-radius: 50%; transform: translate(-50%, -50%) rotate(-19deg); }
	.orbit-two { width: 139%; height: 49%; transform: translate(-50%, -50%) rotate(23deg); border-color: #f2b56d7d; }
	.earth { display: none; position: absolute; width: 130%; height: 44%; left: 53%; bottom: -19%; transform: translateX(-50%) rotate(-8deg); overflow: hidden; border-radius: 50% 50% 0 0; background: linear-gradient(170deg, #6caed0, #1b5786 30%, #0e335f 75%); box-shadow: 0 -13px 40px #4bbdf6a8; }
	.earth::before { content: ''; position: absolute; inset: 4px 0 0; border-radius: 50% 50% 0 0; border-top: 2px solid #d5f5ff; box-shadow: 0 -5px 14px #70d3ff; }
	.earth-glow { position: absolute; width: 70%; height: 50%; left: 15%; top: 25%; background: #63b2e8; filter: blur(40px); opacity: .3; }
	.earth-land { position: absolute; background: #6eaf98; opacity: .57; clip-path: polygon(12% 0, 43% 9%, 56% 31%, 48% 51%, 61% 68%, 47% 100%, 22% 87%, 9% 54%, 0 25%); }
	.land-one { width: 27%; height: 62%; left: 24%; top: 13%; transform: rotate(24deg); }
	.land-two { width: 18%; height: 58%; left: 67%; top: 9%; transform: rotate(-31deg); }
	.launch-trail { position: absolute; width: 39%; height: 1px; top: 58%; left: 34%; transform: rotate(-52deg); transform-origin: right; background: linear-gradient(90deg, transparent, #ffc476aa, #fff7d9); box-shadow: 0 0 12px #ffb255; }
	.rocket { display: none; position: absolute; left: 51%; top: 40%; width: 34px; height: 60px; transform: translate(-50%,-50%) rotate(34deg); filter: drop-shadow(0 0 12px #ffc87b); animation: drift 5s ease-in-out infinite; }
	.rocket svg { width: 100%; height: 100%; }
	@keyframes drift { 0%,100% { translate: 0 0; } 50% { translate: 0 -7px; } }
	.art-caption { position: absolute; bottom: 21px; left: 22px; right: 22px; display: flex; align-items: center; gap: 9px; color: #d5e6f5; font-size: 11px; }
	.caption-coord { margin-left: auto; color: #9bb6ce; font-variant-numeric: tabular-nums; }
	.art-index { position: absolute; right: 22px; top: 45%; color: #ffffffa0; text-align: right; font: 9px/1.7 Roboto, sans-serif; letter-spacing: .1em; }
	.lesson-section { padding: 27px 0 66px; border-top: 1px solid color-mix(in srgb, var(--m3-outline-variant), transparent 36%); }
	.section-heading { display: flex; align-items: end; justify-content: space-between; gap: 36px; margin-bottom: 25px; }
	.section-eyebrow { margin: 0 0 7px; letter-spacing: .02em; color: var(--m3-on-surface-variant); }
	.section-heading h2 { margin: 0; font: var(--m3-headline-medium-emphasized); letter-spacing: var(--m3-tracking-headline); }
	.closing h2 { margin: 0; font: var(--m3-headline-small-emphasized); letter-spacing: var(--m3-tracking-headline); }
	.section-heading > p { max-width: 430px; margin: 0 0 4px; color: var(--m3-on-surface-variant); font: var(--m3-body-medium); letter-spacing: var(--m3-tracking-body-medium); }
	.lesson-list { display: grid; grid-template-columns: repeat(3,minmax(0,1fr)); gap: 16px; }
	.lesson-card { min-width: 0; padding: 17px 17px 16px; border: 1px solid var(--m3-outline-variant); border-radius: 15px; background: var(--m3-surface-low); transition: border-color .2s ease, background .2s ease; }
	.lesson-card:hover { border-color: var(--m3-outline); background: var(--m3-surface-container); }
	.lesson-title-row { min-height: 34px; display: flex; align-items: center; gap: 11px; margin-bottom: 13px; }
	.grade-tag { flex: none; padding: 5px 12px; border-radius: 999px; background: var(--m3-secondary-container); color: var(--m3-on-secondary-container); font: var(--m3-label-medium-emphasized); letter-spacing: var(--m3-tracking-label-medium); }
	.lesson-title-row h3 { min-width: 0; margin: 0; overflow: hidden; color: var(--m3-on-surface); font: var(--m3-title-medium-emphasized); letter-spacing: var(--m3-tracking-title-medium); white-space: nowrap; text-overflow: ellipsis; }
	.lesson-index { margin-left: auto; color: var(--m3-outline); font: 10px/1 Roboto, sans-serif; font-variant-numeric: tabular-nums; }
	.scene-button { display: block; width: 100%; position: relative; padding: 0; border: 0; overflow: hidden; border-radius: 10px; background: var(--m3-surface-container); cursor: pointer; text-align: left; }
	.scene-svg { display: block; width: 100%; aspect-ratio: 2.53; }
	.scene-label { position: absolute; left: 11px; bottom: 10px; display: flex; align-items: center; gap: 9px; padding: 6px 10px; border: 1px solid #ffffff26; border-radius: 999px; color: #f2f5f9; background: #101820c7; font-size: 10px; line-height: 15px; backdrop-filter: blur(8px); }
	.scene-label span { color: var(--space-amber); font-size: 14px; }
	.scene-button:hover .scene-svg { transform: scale(1.025); }
	.scene-svg { transition: transform .35s cubic-bezier(.2,.8,.2,1); }
	.lesson-copy { margin: 13px 2px 0; color: var(--m3-on-surface-variant); text-align: center; font: var(--m3-body-medium); letter-spacing: var(--m3-tracking-body-medium); }
	.closing { display: flex; align-items: center; gap: 20px; padding: 28px 0; border-top: 1px solid var(--m3-outline-variant); border-bottom: 1px solid var(--m3-outline-variant); }
	.closing-star { color: var(--space-amber); font-size: 32px; line-height: 1; }
	.closing h2 { font-size: 24px; line-height: 32px; }
	.closing p { margin: 5px 0 0; color: var(--m3-on-surface-variant); font: var(--m3-body-medium); letter-spacing: var(--m3-tracking-body-medium); }
	.text-button { margin-left: auto; padding: 11px 0 11px 16px; border: 0; color: var(--m3-primary); background: transparent; font: 600 14px/20px Roboto, 'Noto Sans SC', sans-serif; cursor: pointer; }
	.text-button span { margin-left: 7px; font-size: 18px; }
	.footer { display: flex; align-items: center; justify-content: space-between; min-height: 60px; color: var(--m3-outline); font-size: 10px; letter-spacing: .04em; }
	.dialog-scrim { position: fixed; inset: 0; z-index: 10; display: grid; place-items: center; padding: 24px; background: #0009; backdrop-filter: blur(4px); }
	.simulation-dialog { width: min(790px, 100%); padding: 24px; border: 1px solid var(--m3-outline-variant); border-radius: 22px; background: var(--m3-surface-container); color: var(--m3-on-surface); box-shadow: 0 24px 80px #0008; }
	.dialog-heading { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 19px; }
	.dialog-heading .eyebrow { margin: 0 0 4px; }
	.dialog-heading h2 { margin: 0; font: var(--m3-headline-small-emphasized); letter-spacing: var(--m3-tracking-headline); }
	.close-button { width: 38px; height: 38px; border: 1px solid var(--m3-outline-variant); border-radius: 50%; background: transparent; color: var(--m3-on-surface); font-size: 24px; line-height: 1; cursor: pointer; }
	.close-button:hover { background: var(--m3-surface-high); }
	.sim-content { display: grid; grid-template-columns: 1.2fr .8fr; gap: 22px; }
	.sim-visual { min-height: 258px; position: relative; overflow: hidden; border: 1px solid #507499; border-radius: 13px; background: radial-gradient(ellipse at 50% 75%,#245b84,#102947 70%,#0e1a2d); }
	.sim-stars { position: absolute; inset: 0; opacity: .7; background-image: radial-gradient(#fff 1px,transparent 1.7px),radial-gradient(#b9ddf7 .8px,transparent 1.5px); background-size: 71px 71px,97px 97px; background-position: 8px 17px,38px 9px; }
	.sim-planet { position: absolute; width: 68%; aspect-ratio: 1; left: 16%; bottom: -70%; border-radius: 50%; border: 1px solid #b4eaff; background: radial-gradient(circle at 40% 20%,#4296c1,#245787 47%,#15365e 72%); box-shadow: 0 -9px 27px #78d5ff91; }
	.sim-planet::after { content: ''; position: absolute; inset: 18% 23%; border-radius: 45%; background: #5c9e8a; clip-path: polygon(12% 0,74% 7%,100% 37%,62% 50%,78% 88%,30% 100%,0 56%); opacity: .7; }
	.sim-orbit-path { position: absolute; width: 82%; height: 40%; left: 9%; top: 25%; border: 1px solid #f7d781; border-radius: 50%; transform: rotate(-20deg); transition: transform .5s ease; }
	.sim-visual.running .sim-orbit-path { animation: orbit-turn 4s linear infinite; }
	@keyframes orbit-turn { to { transform: rotate(340deg); } }
	.sim-satellite { position: absolute; left: 72%; top: 35%; width: 20px; height: 14px; display: grid; place-items: center; background: #e8e6d8; border: 1px solid #fff; transition: left .35s ease, top .35s ease; }
	.sim-satellite::before, .sim-satellite::after { content: ''; position: absolute; width: 14px; height: 21px; background: repeating-linear-gradient(90deg,#4c76a2 0 4px,#9cbad2 4px 5px); border: 1px solid #c8dbed; }
	.sim-satellite::before { right: 100%; }.sim-satellite::after { left: 100%; }
	.sim-visual.running .sim-satellite { animation: sat-orbit 4s linear infinite; }
	@keyframes sat-orbit { 0% { transform: rotate(0) translateX(12px); } 25% { transform: rotate(90deg) translateX(12px); } 50% { transform: rotate(180deg) translateX(12px); } 75% { transform: rotate(270deg) translateX(12px); } 100% { transform: rotate(360deg) translateX(12px); } }
	.sim-readout { position: absolute; left: 13px; bottom: 13px; display: grid; gap: 3px; color: #c2d4e5; font-size: 10px; }
	.sim-readout b { color: white; font: 600 13px/18px Roboto, sans-serif; }.sim-readout.right { left: auto; right: 13px; text-align: right; }
	.sim-controls { display: flex; flex-direction: column; justify-content: center; gap: 19px; }
	.sim-controls label > span { display: flex; justify-content: space-between; gap: 8px; margin-bottom: 7px; color: var(--m3-on-surface-variant); font-size: 12px; line-height: 18px; }
	.sim-controls output { color: var(--m3-on-surface); font-variant-numeric: tabular-nums; }
	.sim-controls input[type='range'] { display: block; width: 100%; height: 4px; border-radius: 4px; accent-color: var(--m3-primary); cursor: pointer; }
	.sim-actions { margin-top: 1px; }
	.sim-actions p { margin: 0 0 11px; color: var(--m3-on-surface-variant); font-size: 11px; line-height: 17px; }
	.run-button { width: 100%; min-height: 43px; display: flex; align-items: center; justify-content: center; gap: 9px; border: 0; border-radius: 999px; color: var(--m3-on-primary); background: var(--m3-primary); font: 600 13px/20px Roboto, 'Noto Sans SC', sans-serif; cursor: pointer; }
	.run-button:hover { filter: brightness(1.06); }
	.demo-note { margin: 15px 0 0; color: var(--m3-outline); font-size: 10px; line-height: 15px; }
	@media (max-width: 980px) {
		.topbar, main, .footer { width: min(100% - 48px, 760px); }
		.topnav { gap: 20px; margin-left: 0; }
		.hero { grid-template-columns: 1fr 0.9fr; gap: 25px; padding: 52px 0; }
		h1 { font: var(--m3-display-medium-emphasized); }
		.hero-art { min-height: 390px; }
		.lesson-list { gap: 11px; }.lesson-card { padding: 13px; }.lesson-title-row { gap: 7px; }.lesson-title-row h3 { font-size: 14px; }
	}
	@media (max-width: 720px) {
		.topbar, main, .footer { width: calc(100% - 36px); }
		.topbar { height: 64px; }.topnav { display: none; }.brand { font-size: 14px; }.brand-mark { width: 31px; height: 31px; }
		.top-cta { padding: 8px 13px; font-size: 12px; }
		.hero { grid-template-columns: 1fr; gap: 28px; padding: 42px 0 44px; }
		.hero-copy { order: 0; }.hero-art { order: 1; min-height: clamp(300px, 73vw, 420px); }
		.eyebrow { font-size: 10px; margin-bottom: 16px; }
		h1 { font: var(--m3-display-small-emphasized); }
		.hero-summary { margin: 17px 0 22px; font: var(--m3-body-medium); letter-spacing: var(--m3-tracking-body-medium); }
		.hero-actions { gap: 13px; align-items: stretch; }.primary-button { min-height: 58px; padding: 0 20px; font-size: 18px; }.status-note { padding-left: 12px; gap: 6px; font-size: 9px; }
		.lesson-section { padding: 25px 0 43px; }.section-heading { display: block; margin-bottom: 17px; }.section-heading h2 { font: var(--m3-headline-small-emphasized); }.section-heading > p { margin-top: 9px; font: var(--m3-body-small); }
		.lesson-list { grid-template-columns: 1fr; gap: 12px; }.lesson-card { padding: 14px; }.lesson-title-row { gap: 10px; margin-bottom: 10px; }.lesson-title-row h3 { font: var(--m3-title-small-emphasized); }.scene-svg { aspect-ratio: 2.2; }.lesson-copy { margin-top: 10px; text-align: left; font: var(--m3-body-small); }
		.closing { align-items: flex-start; gap: 12px; padding: 23px 0; }.closing-star { font-size: 26px; }.closing h2 { font: var(--m3-title-large-emphasized); }.closing p { max-width: 300px; font: var(--m3-body-small); }.text-button { align-self: center; padding-left: 0; white-space: nowrap; font-size: 12px; }
		.footer { gap: 9px; min-height: 57px; font-size: 8px; }.footer span:last-child { display: none; }
		.dialog-scrim { align-items: end; padding: 12px; }.simulation-dialog { max-height: calc(100dvh - 24px); overflow-y: auto; padding: 19px; border-radius: 20px; }.dialog-heading { margin-bottom: 13px; }.dialog-heading h2 { font: var(--m3-title-large-emphasized); letter-spacing: var(--m3-tracking-title-large); }.sim-content { grid-template-columns: 1fr; gap: 18px; }.sim-visual { min-height: 195px; }.sim-controls { gap: 14px; }.sim-actions { display: flex; align-items: center; gap: 12px; justify-content: space-between; }.sim-actions p { margin: 0; }.run-button { width: auto; min-width: 132px; padding: 0 14px; }.demo-note { margin-top: 12px; }
	}
	@media (max-width: 390px) {
		.topbar, main, .footer { width: calc(100% - 28px); }.top-cta { padding: 7px 10px; }.brand { gap: 8px; font-size: 12px; }
		.hero-actions { align-items: center; }.primary-button { min-height: 54px; padding: 0 16px; font-size: 16px; }.status-note { font-size: 8px; }
		.closing { gap: 8px; }.closing h2 { font-size: 17px; }.text-button { font-size: 11px; }.footer span:nth-child(2) { font-size: 7px; }
	}
	@media (prefers-reduced-motion: reduce) {
		.space-page :global(*), .space-page :global(*::before), .space-page :global(*::after) { scroll-behavior: auto !important; animation-duration: .01ms !important; animation-iteration-count: 1 !important; transition-duration: .01ms !important; }
		.space-page .twinkle-star { animation: star-twinkle-reduced 12s ease-in-out infinite !important; }
		.space-page .meteor { display: none !important; }
	}
</style>
