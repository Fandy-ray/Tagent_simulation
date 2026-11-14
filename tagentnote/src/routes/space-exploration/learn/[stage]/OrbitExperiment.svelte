<script lang="ts">
	import { orbitSource, spaceStages, type SpaceStage } from '$lib/data/spaceLearning';
	let { stage, onSave }: { stage: SpaceStage; onSave: (text: string) => void } = $props();
	let height = $state(400);
	let running = $state(false);
	const radius = $derived(6371 + height);
	const speed = $derived(Math.sqrt(398600 / radius));
	const period = $derived((2 * Math.PI * radius) / speed / 60);
	const orbitSize = $derived(128 + ((height - 400) / 1600) * 92);
</script>

<p>{spaceStages[stage].task}</p>
<div class="learn-experiment">
	<figure class="orbit-player">
		<div class="orbit-visual" role="img" aria-label="圆轨道示意图，轨道高度越高，轨道圆越大">
			<div
				class="orbit-ring"
				style:--orbit-size={`${orbitSize}px`}
				style:--orbit-time={`${period / 18}s`}
				class:running
			>
				<span class="orbit-satellite"></span>
				{#if stage !== 'primary'}
					<svg
						class="orbit-vectors"
						width="62"
						height="55"
						viewBox="0 0 62 55"
						fill="none"
						aria-hidden="true"
					>
						<path d="M7 9h43m-6-5 6 5-6 5" stroke="var(--m3-primary)" stroke-width="2" />
						<path d="M7 9v34m-5-6 5 6 5-6" stroke="var(--space-amber)" stroke-width="2" />
					</svg>
				{/if}
			</div>
			<span class="orbit-earth">地球</span>
		</div>
		<figcaption>
			<button class="learn-button orbit-play" type="button" onclick={() => (running = !running)}>
				<svg viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
					{#if running}<path d="M7 5h3v14H7zm7 0h3v14h-3z" />{:else}<path
							d="m8 5 11 7-11 7z"
						/>{/if}
				</svg>
				{running ? '暂停演示' : '播放演示'}
			</button>
			<span>轨道示意 · 非等比例</span>
		</figcaption>
	</figure>
	<div class="orbit-controls">
		{#if stage === 'primary'}
			<div class="learn-actions" role="group" aria-label="轨道距离">
				<button
					class="learn-button secondary"
					type="button"
					aria-pressed={height === 400}
					onclick={() => (height = 400)}>离地球近一点</button
				>
				<button
					class="learn-button secondary"
					type="button"
					aria-pressed={height === 2000}
					onclick={() => (height = 2000)}>离地球远一点</button
				>
			</div>
			<p>{height === 400 ? '靠近地球时，卫星绕一圈更快。' : '远离地球时，卫星绕一圈需要更久。'}</p>
		{:else}
			<label for="orbit-height">轨道高度 <output>{height} km</output></label>
			<input id="orbit-height" type="range" min="400" max="2000" step="100" bind:value={height} />
			<p>绕行周期约 {Math.round(period)} 分钟</p>
			{#if stage === 'high'}<p>轨道速度约 {speed.toFixed(2)} km/s</p>{/if}
		{/if}
	</div>
</div>
<p class="learn-muted">
	圆轨道教学示意，距离与播放时间经过缩放。{stage !== 'primary'
		? '浅紫是速度方向，琥珀色是引力方向。'
		: ''}
</p>
<div class="learn-actions">
	<button
		class="learn-button secondary"
		type="button"
		onclick={() =>
			onSave(
				`圆轨道高度 ${height} km，周期约 ${Math.round(period)} 分钟，速度约 ${speed.toFixed(2)} km/s。`
			)}>记录当前观测</button
	>
	<a class="learn-button secondary" href={orbitSource.href} target="_blank" rel="noreferrer"
		>查看轨道参考资料</a
	>
</div>
