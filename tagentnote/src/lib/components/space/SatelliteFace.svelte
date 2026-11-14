<script lang="ts">
	let {
		compact = false,
		thinking = false,
		greeting = false
	}: {
		compact?: boolean;
		thinking?: boolean;
		greeting?: boolean;
	} = $props();
</script>

<span class="mascot" class:compact class:thinking class:greeting aria-hidden="true">
	<span class="shadow"></span>
	<span class="pilot">
		<span class="pack"></span>
		<span class="arm left"><i></i></span>
		<span class="arm right"><i></i></span>
		<span class="boot left"></span>
		<span class="boot right"></span>
		<span class="suit"><span class="badge"></span></span>
		<span class="helmet">
			<span class="antenna"></span>
			<span class="visor">
				<i class="eye"></i><i class="eye"></i><b class="smile"></b>
			</span>
		</span>
	</span>
</span>

<style>
	.mascot {
		position: relative;
		display: inline-block;
		width: 78px;
		height: 86px;
		flex: none;
		vertical-align: middle;
	}
	.mascot.compact {
		width: 45px;
		height: 49px;
	}
	.pilot {
		position: absolute;
		inset: 0;
		display: block;
		transform-origin: 50% 65%;
		animation: drift 6s ease-in-out infinite;
	}
	.compact .pilot {
		animation: none;
	}
	.shadow {
		position: absolute;
		right: 24%;
		bottom: 2%;
		left: 24%;
		height: 5%;
		border-radius: 50%;
		background: #a489d73d;
		animation: shadow-breathe 6s ease-in-out infinite;
	}
	.compact .shadow {
		display: none;
	}
	.pack {
		position: absolute;
		inset: 48% 20% 21%;
		border: 1px solid #9a82c5;
		border-radius: 9px;
		background: #58447c;
	}
	.suit {
		position: absolute;
		inset: 49% 27% 20%;
		display: grid;
		place-items: center;
		border: 1px solid #eee5ff;
		border-radius: 34% 34% 43% 43%;
		background: linear-gradient(148deg, #eaddff, #a88bdc);
		box-shadow: inset 0 -3px #8065ad;
	}
	.badge {
		width: 21%;
		aspect-ratio: 1;
		border: 1px solid #ffe4ad;
		border-radius: 50%;
		background: #f6b45f;
	}
	.arm,
	.boot {
		position: absolute;
		border: 1px solid #dac6f8;
		border-radius: 999px;
		background: #ac90db;
	}
	.arm {
		top: 51%;
		width: 14%;
		height: 26%;
		transform-origin: 50% 20%;
	}
	.arm.left {
		left: 20%;
		transform: rotate(29deg);
	}
	.arm.right {
		right: 20%;
		transform: rotate(-29deg);
	}
	.arm i {
		position: absolute;
		inset: auto -16% -9%;
		height: 43%;
		border: 1px solid #f0e4ff;
		border-radius: 999px;
		background: #d9c5f7;
	}
	.boot {
		top: 71%;
		width: 20%;
		height: 18%;
		background: #6c5599;
	}
	.boot.left {
		left: 28%;
		transform: rotate(12deg);
	}
	.boot.right {
		right: 28%;
		transform: rotate(-12deg);
	}
	.helmet {
		position: absolute;
		inset: 13% 15% 43%;
		border: 1px solid #eee5ff;
		border-radius: 41% 41% 37% 37%;
		background: linear-gradient(145deg, #f7eeff, #b89de9 76%);
		box-shadow: inset 0 -3px #9577c8;
	}
	.antenna {
		position: absolute;
		bottom: 99%;
		left: 54%;
		width: 2px;
		height: 20%;
		background: #d0bcff;
		transform: rotate(16deg);
		transform-origin: bottom;
	}
	.antenna::after {
		position: absolute;
		top: -4px;
		left: -2px;
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: #f6b45f;
		content: '';
	}
	.visor {
		position: absolute;
		inset: 19% 10% 21%;
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 23%;
		border: 1px solid #846cae;
		border-radius: 44% 44% 38% 38%;
		background: #211c37;
	}
	.eye {
		width: 12%;
		height: 29%;
		margin-top: -7%;
		border-radius: 50%;
		background: #eee5ff;
		animation: blink 6.4s linear infinite;
	}
	.smile {
		position: absolute;
		top: 56%;
		width: 16%;
		height: 23%;
		border-bottom: 1px solid #f6b45f;
		border-radius: 50%;
	}
	.thinking .helmet {
		animation: wonder 1.8s ease-in-out infinite;
	}
	.thinking .antenna::after {
		animation: signal 1.8s ease-in-out infinite;
	}
	.greeting .arm.right {
		animation: wave 720ms ease-in-out;
	}
	@media (hover: hover) and (pointer: fine) {
		:global(.launcher:hover) .arm.right {
			animation: wave 720ms ease-in-out;
		}
	}
	@keyframes drift {
		0%,
		100% {
			transform: translate(0, 1px) rotate(-3deg);
		}
		35% {
			transform: translate(-3px, -5px) rotate(2deg);
		}
		68% {
			transform: translate(3px, -2px) rotate(3deg);
		}
	}
	@keyframes shadow-breathe {
		35% {
			transform: scale(0.84);
			opacity: 0.6;
		}
	}
	@keyframes blink {
		0%,
		43%,
		47%,
		100% {
			transform: scaleY(1);
		}
		45% {
			transform: scaleY(0.12);
		}
	}
	@keyframes wave {
		0%,
		100% {
			transform: rotate(-29deg);
		}
		30%,
		66% {
			transform: rotate(-133deg);
		}
		48% {
			transform: rotate(-98deg);
		}
	}
	@keyframes wonder {
		50% {
			transform: rotate(-12deg);
		}
	}
	@keyframes signal {
		50% {
			opacity: 0.42;
		}
	}
	@media (prefers-reduced-motion: reduce) {
		.mascot :is(.pilot, .shadow, .eye, .arm.right, .helmet),
		.antenna::after {
			animation: none !important;
		}
	}
</style>
