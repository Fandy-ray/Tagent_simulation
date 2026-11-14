<script lang="ts">
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
</script>

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

<style>
	.cosmic-layer {
		position: fixed;
		z-index: -1;
		inset: 0;
		overflow: hidden;
		pointer-events: none;
	}
	.twinkle-star {
		position: absolute;
		left: var(--star-x);
		top: var(--star-y);
		width: 2px;
		height: 2px;
		border-radius: 50%;
		background: #eaf4ff;
		opacity: 0.24;
		box-shadow: 0 0 5px 1px rgb(159 207 255 / 45%);
		animation: star-twinkle var(--star-duration) ease-in-out var(--star-delay) infinite;
	}
	.twinkle-star.bright {
		width: 3px;
		height: 3px;
		background: #fff2c9;
		box-shadow: 0 0 8px 2px rgb(255 205 125 / 55%);
	}
	.meteor {
		position: absolute;
		left: var(--meteor-x);
		top: var(--meteor-y);
		width: var(--meteor-width);
		height: 1.5px;
		border-radius: 50%;
		opacity: 0;
		background: linear-gradient(
			90deg,
			transparent 0%,
			rgb(203 231 255 / 30%) 28%,
			#fff4d6 82%,
			transparent 100%
		);
		box-shadow: 0 0 8px 1px rgb(137 197 255 / 35%);
		transform: translate3d(0, 0, 0) rotate(var(--meteor-angle));
		animation: meteor-sweep 10s linear var(--meteor-delay) infinite;
	}
	@keyframes star-twinkle {
		0%,
		100% {
			opacity: 0.2;
			transform: scale(0.78);
		}
		50% {
			opacity: 0.88;
			transform: scale(1.3);
		}
	}
	@keyframes meteor-sweep {
		0%,
		4% {
			opacity: 0;
			transform: translate3d(0, 0, 0) rotate(var(--meteor-angle));
		}
		6% {
			opacity: 0.92;
		}
		15% {
			opacity: 0;
			transform: translate3d(var(--meteor-dx), var(--meteor-dy), 0) rotate(var(--meteor-angle));
		}
		100% {
			opacity: 0;
			transform: translate3d(var(--meteor-dx), var(--meteor-dy), 0) rotate(var(--meteor-angle));
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.twinkle-star {
			animation: none;
		}
		.meteor {
			display: none;
		}
	}
</style>
