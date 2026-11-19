<script lang="ts">
	import type { SceneKey } from '$lib/data/spaceScenes';
	let { sceneKey, label }: { sceneKey: SceneKey; label: string } = $props();
	const land = 'M0 83 Q35 45 80 71 T150 72 V132 H0Z';
	const river = 'M-5 98 Q32 83 37 50 T98 49 T155 22';
	const stars = [
		[25, 27],
		[58, 58],
		[103, 20],
		[154, 44],
		[225, 25],
		[273, 58],
		[337, 23],
		[361, 107],
		[32, 177],
		[319, 173]
	];
</script>

<svg class="scene-art" viewBox="0 0 380 200" role="img" aria-label={label}>
	<rect width="380" height="200" fill="#121a2c" />
	{#each stars as [x, y] (x)}
		<circle cx={x} cy={y} r="1.2" fill="#b7c6e2" opacity=".48" />
	{/each}

	{#snippet earth(x: number, y: number, r: number)}
		<g transform={`translate(${x} ${y}) scale(${r / 30})`}>
			<circle r="30" fill="#235681" stroke="#7cc3e9" stroke-width="1.2" />
			<path
				d="M-25-11-15-20-6-17 5-23 14-13 5-7 8 0-4 4-10 16-19 8-16-2ZM9 14l12-10 5 9-9 10-7-5Z"
				fill="#70b5a1"
			/>
			<path
				d="M-26 8a27 27 0 0 0 39 17"
				stroke="#14334e"
				stroke-width="4"
				opacity=".55"
				fill="none"
			/>
		</g>
	{/snippet}
	{#snippet satellite(x: number, y: number, angle = 0)}
		<g transform={`translate(${x} ${y}) rotate(${angle})`}>
			<path d="M-31-7h21V7h-21Zm41 0h21V7H10Z" fill="#574d96" stroke="#d0bcff" />
			<path d="M-24-7V7m7-14V7m34-14V7m7-14V7" stroke="#9990cf" />
			<rect x="-10" y="-9" width="20" height="18" rx="4" fill="#e6e0e9" />
			<circle r="3" fill="#f6b45f" />
		</g>
	{/snippet}
	{#snippet arrow(x: number, y: number, angle: number, length: number, color: string)}
		<path
			transform={`translate(${x} ${y}) rotate(${angle})`}
			d={`M0 0H${length}m-6-5 6 5-6 5`}
			stroke={color}
			stroke-width="2"
			fill="none"
			stroke-linecap="round"
			stroke-linejoin="round"
		/>
	{/snippet}
	{#snippet map(
		x: number,
		label: string,
		mode: 'clear' | 'cloud' | 'shadow' | 'coarse' | 'fine' | 'visible' | 'infrared'
	)}
		<svg {x} y="27" width="150" height="132" viewBox="0 0 150 132" class="map">
			<rect width="150" height="132" fill={mode === 'infrared' ? '#5b527e' : '#305151'} />
			<path d={land} fill={mode === 'infrared' ? '#c599d6' : '#537c62'} />
			<path d={river} fill="none" stroke="#80c4e4" stroke-width="10" />
			{#if mode === 'coarse' || mode === 'fine'}
				{@const size = mode === 'coarse' ? 25 : 10}
				<path d="M15 105h45v14H15z" fill="#e5af83" />
				{#each Array.from({ length: Math.ceil(150 / size) }, (_, i) => i * size) as p (p)}
					<path d={`M${p} 0v132M0 ${p}h150`} stroke="#151f31" opacity=".6" />
				{/each}
			{/if}
			{#if mode === 'cloud' || mode === 'shadow'}
				{#if mode === 'shadow'}<path
						d="M55 77q28-25 68-3l-4 34-57 1Z"
						fill="#20233a"
						opacity=".75"
					/>{/if}
				<path
					d="M69 39q-7-15 11-19 5-19 27-7 20-11 29 7 16 0 16 21-6 15-25 9-13 8-26-2-28 6-32-9Z"
					fill="#e3eaf5"
					opacity=".88"
				/>
			{/if}
		</svg>
		<text x={x + 75} y="181" text-anchor="middle">{label}</text>
	{/snippet}

	{#if sceneKey === 'satellites/orbit'}
		<path d="M16 154h139" stroke="#61938f" stroke-width="3" />
		<path d="M26 134q60-91 120 20" class="trace" />
		<circle cx="79" cy="93" r="8" fill="#f6b45f" />
		<path d="M173 42v115" stroke="#4c5875" />
		<circle cx="269" cy="105" r="64" class="trace" />
		{@render earth(269, 105, 37)}
		{@render satellite(309, 54, -18)}
		<text x="83" y="180" text-anchor="middle">操场</text>
		<text x="269" y="188" text-anchor="middle">太空</text>
	{:else if sceneKey === 'satellites/pictures' || sceneKey.startsWith('observations/')}
		{#if sceneKey === 'observations/resolution'}
			{@render map(28, '较粗的像元', 'coarse')}{@render map(202, '较细的像元', 'fine')}
		{:else if sceneKey === 'observations/bands'}
			{@render map(28, '可见光', 'visible')}{@render map(202, '另一波段', 'infrared')}
		{:else if sceneKey === 'observations/change'}
			{@render map(28, '第一次观测', 'clear')}{@render map(202, '第二次观测', 'shadow')}
		{:else}
			{@render map(28, '第一张', 'clear')}{@render map(202, '第二张', 'cloud')}
		{/if}
	{:else if sceneKey === 'satellites/moon'}
		<ellipse cx="184" cy="99" rx="142" ry="58" class="trace" />
		{@render earth(170, 99, 44)}
		<circle cx="303" cy="78" r="21" fill="#d7cde3" />
		<circle cx="298" cy="73" r="5" fill="#a69ab7" />
		<circle cx="309" cy="83" r="3" fill="#a69ab7" />
		{@render satellite(58, 125, -18)}
		<text x="306" y="118" text-anchor="middle">月亮</text>
		<text x="67" y="167" text-anchor="middle">人造卫星</text>
	{:else if sceneKey.startsWith('station/')}
		<rect x="32" y="22" width="316" height="156" rx="30" fill="#25334c" stroke="#4d638a" />
		<circle cx="105" cy="95" r="47" fill="#112037" stroke="#8aabd3" stroke-width="4" />
		{@render earth(112, 100, 30)}
		<path d="M174 40v111M326 40v111" stroke="#526582" stroke-width="2" />
		{#if sceneKey === 'station/floating'}
			<g transform="translate(247 98) rotate(-24)">
				<rect x="-39" y="-6" width="68" height="12" rx="3" fill="#f6b45f" />
				<path d="M29-6 43 0 29 6Z" fill="#e6e0e9" />
				<path d="M39-2 45 0 39 2Z" fill="#1a1c32" />
			</g>
			<path d="M220 67q-24 4-29 18m86 47q18-4 21-17" class="trace" />
			<text x="248" y="154" text-anchor="middle">漂浮的铅笔</text>
		{:else if sceneKey === 'station/sleep'}
			<rect x="223" y="35" width="60" height="120" rx="20" fill="#62528e" stroke="#d0bcff" />
			<circle cx="253" cy="63" r="14" fill="#ead9c0" />
			<path d="M235 86h36m-36 24h36m-36 24h36" stroke="#b89adf" stroke-width="3" />
			<path d="M223 80h-24m84 0h24m-84 49h-24m84 0h24" stroke="#f6b45f" stroke-width="4" />
		{:else}
			<path d="M264 143v-36l-20-9" stroke="#e6e0e9" stroke-width="7" fill="none" />
			<rect x="238" y="126" width="54" height="34" rx="9" fill="#556a98" stroke="#9db5df" />
			<circle cx="226" cy="85" r="19" fill="#68b8e5" stroke="#b6e5ff" />
			<ellipse cx="220" cy="79" rx="6" ry="3" fill="#d6f1ff" />
			<circle cx="199" cy="70" r="5" fill="#8ac9ec" />
		{/if}
	{:else if sceneKey.startsWith('moonlight/')}
		{#if sceneKey === 'moonlight/phases'}
			{#each [{ x: 75, path: 'M75 66a29 29 0 0 1 0 58q29-29 0-58' }, { x: 190, path: 'M190 66a29 29 0 0 1 0 58Z' }, { x: 305, path: 'M305 66a29 29 0 1 1 0 58a29 29 0 1 1 0-58Z' }] as moon, i (moon.x)}
				<circle cx={moon.x} cy="95" r="29" fill="#2c344a" stroke="#7484aa" />
				<path d={moon.path} fill="#f0cf95" />
				<text x={moon.x} y="155" text-anchor="middle">第 {i + 1} 次观察</text>
			{/each}
		{:else if sceneKey === 'moonlight/eclipse'}
			<path d="M184 65 346 85v30L184 135Z" fill="#3b2b4c" stroke="#8b729c" stroke-dasharray="4 4" />
			<circle cx="64" cy="100" r="29" fill="#f6b45f" />
			{@render arrow(101, 72, 0, 48, '#f6b45f')}
			{@render arrow(101, 128, 0, 48, '#f6b45f')}
			{@render earth(184, 100, 35)}
			<circle cx="298" cy="100" r="14" fill="#ab838f" stroke="#dfac9e" />
			<text x="64" y="165" text-anchor="middle">光源</text><text
				x="307"
				y="165"
				text-anchor="middle">影区</text
			>
		{:else}
			<ellipse cx="190" cy="100" rx="100" ry="64" class="trace" />
			{@render earth(190, 100, 28)}
			{#each [[190, 36, 190, 44], [290, 100, 282, 100], [190, 164, 190, 156], [90, 100, 98, 100]] as [x, y, mx, my] (x + y)}
				<circle cx={x} cy={y} r="14" fill="#c2b9d5" />
				<circle cx={mx} cy={my} r="4" fill="#efa75a" />
			{/each}
		{/if}
	{:else}
		<ellipse cx="178" cy="99" rx="108" ry="65" class="trace" />
		{@render earth(178, 99, 34)}
		{#if sceneKey === 'motion/orbit'}
			<path d="M100 51q78-42 143-3" fill="none" stroke="#d0bcff" stroke-width="2" />
			<circle cx="110" cy="49" r="3" fill="#d0bcff" /><circle
				cx="145"
				cy="37"
				r="3"
				fill="#d0bcff"
			/>
			{@render satellite(200, 35)}
			{@render arrow(218, 36, 8, 49, '#f6b45f')}
			<text x="289" y="45">切线</text>
		{:else if sceneKey === 'motion/gravity'}
			{#each [[178, 34], [285, 99], [178, 164]] as [x, y], i (i)}
				<circle cx={x} cy={y} r="8" fill="#f6b45f" />
				<text x={x + 15} y={y + 5}>{'ABC'[i]}</text>
			{/each}
		{:else if sceneKey === 'model/orbit'}
			<path d="M178 99 264 59" stroke="#f6b45f" stroke-width="2" />
			<circle cx="178" cy="99" r="3" fill="#f6b45f" />
			{@render satellite(264, 59, 18)}
			<text x="224" y="98">r</text>
		{:else}
			<ellipse
				cx="178"
				cy="99"
				rx="143"
				ry="83"
				fill="none"
				stroke="#79afd3"
				stroke-dasharray="4 5"
			/>
			{@render satellite(117, 43, -22)}
			{@render satellite(270, 160, -20)}
			<text x="85" y="75"
				>{sceneKey === 'model/speed'
					? 'v₁'
					: sceneKey === 'model/period'
						? 'r₁ · T₁'
						: '内圈'}</text
			>
			<text x="300" y="152"
				>{sceneKey === 'model/speed'
					? 'v₂'
					: sceneKey === 'model/period'
						? 'r₂ · T₂'
						: '外圈'}</text
			>
		{/if}
	{/if}
</svg>

<style>
	.scene-art {
		display: block;
		width: 100%;
		height: auto;
	}
	.map {
		overflow: hidden;
	}
	.trace {
		stroke: #a697cf;
		stroke-width: 1.4;
		stroke-dasharray: 4 5;
		fill: none;
	}
	text {
		fill: #e6e0e9;
		font-size: 13px;
		font-family: var(--space-font);
	}
</style>
