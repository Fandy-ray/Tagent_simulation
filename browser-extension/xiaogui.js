(() => {
  // Static copy of the default SatelliteFace for the extension's isolated launcher.
  const mascotMarkup = `<span class="mascot" aria-hidden="true">
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
</span>`;
  const mascotCss = `.mascot {
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
	}`;
  const marker = '#xiaogui=';
  if (!location.hash.startsWith(marker)) return;

  const context = new URLSearchParams(location.hash.slice(marker.length));
  const stage = context.get('space_stage');
  const topic = context.get('space_topic');
  if (!['primary', 'middle', 'high'].includes(stage) || !topic || !/^[a-z0-9-]+$/.test(topic)) return;

  const platform = context.get('platform') ?? 'http://127.0.0.1:5173';
  let assistant;
  try {
    const platformUrl = new URL(platform);
    if (!['http:', 'https:'].includes(platformUrl.protocol) || platformUrl.href !== `${platformUrl.origin}/`) return;
    assistant = new URL('/space-assistant', platformUrl.origin);
  } catch {
    return;
  }
  const hostname = assistant.hostname.toLowerCase();
  const privateIpv4 =
    /^(?:10|127)\./.test(hostname) ||
    /^192\.168\./.test(hostname) ||
    /^169\.254\./.test(hostname) ||
    /^172\.(?:1[6-9]|2\d|3[01])\./.test(hostname);
  const privateIpv6 = /^\[(?:fc|fd|fe80:)/.test(hostname);
  const localPlatform =
    hostname === 'localhost' || hostname === '[::1]' || hostname.endsWith('.local') || privateIpv4 || privateIpv6;
  const trustedPlatforms = new Set();
  assistant.searchParams.set('space_stage', stage);
  assistant.searchParams.set('space_topic', topic);
  assistant.searchParams.set('parent_origin', location.origin);
  const resource = context.get('resource');
  if (resource) assistant.searchParams.set('resource', resource.slice(0, 100));
  const lesson = context.get('space_lesson');
  if (lesson && /^[a-z0-9-]+$/.test(lesson)) assistant.searchParams.set('space_lesson', lesson);

  const host = document.createElement('span');
  host.style.cssText = 'all:initial;position:fixed;right:20px;bottom:20px;z-index:2147483647';
  const shadow = host.attachShadow({ mode: 'closed' });
  const link = document.createElement('a');
  link.href = assistant.href;
  link.target = '_blank';
  link.rel = 'noopener noreferrer';
  const style = document.createElement('style');
  style.textContent = `
    .launcher {
      display: inline-grid;
      justify-items: center;
      gap: 4px;
      padding: 3px 7px;
      border-radius: 12px;
      color: #d0bcff;
      font: 600 14px system-ui, sans-serif;
      text-decoration: none;
      text-shadow: 0 1px 4px #141218, 0 1px 8px #141218;
      background: #141218dd;
    }
    .launcher:hover, .launcher:focus-visible {
      color: #f5edff;
      outline: 2px solid #d0bcff;
    }
    .panel {
      display: grid;
      grid-template: minmax(0, 1fr) / minmax(0, 1fr);
      position: relative;
      box-sizing: border-box;
      width: min(440px, calc(100vw - 40px));
      height: min(590px, calc(100dvh - 40px));
      overflow: hidden;
      border: 1px solid #49454f;
      border-radius: 16px;
      background: #141218;
      color: #e6e0e9;
      box-shadow: 0 8px 32px #0007;
      font: 14px system-ui, sans-serif;
    }
    [hidden] { display: none !important; }
    iframe { width: 100%; height: 100%; min-width: 0; min-height: 0; border: 0; }
    .status { margin: 18px; }
    .status a { color: #d0bcff; }
    .dismiss {
      position: absolute;
      right: 8px;
      top: 8px;
      border: 0;
      background: #2b2930;
      color: #e6e0e9;
      border-radius: 6px;
      cursor: pointer;
      font: 20px system-ui, sans-serif;
    }
` + mascotCss;
  link.className = 'launcher';
  link.setAttribute('aria-label', '打开小轨问答窗口');
  link.innerHTML = mascotMarkup;
  const label = document.createElement('span');
  label.textContent = '问小轨';
  link.append(label);
  const panel = document.createElement('section');
  panel.className = 'panel';
  panel.hidden = true;
  panel.setAttribute('aria-label', '小轨问答');
  link.setAttribute('aria-expanded', 'false');

  const status = document.createElement('p');
  status.className = 'status';
  status.setAttribute('role', 'status');
  const dismiss = document.createElement('button');
  dismiss.type = 'button';
  dismiss.className = 'dismiss';
  dismiss.setAttribute('aria-label', '关闭小轨问答');
  dismiss.textContent = '×';
  const frame = document.createElement('iframe');
  frame.title = '小轨问答';
  frame.referrerPolicy = 'no-referrer';
  frame.hidden = true;
  panel.append(frame, status, dismiss);

  let timeout;
  let ready = false;
  function closePanel() {
    panel.hidden = true;
    link.hidden = false;
    link.setAttribute('aria-expanded', 'false');
    link.focus();
  }

  function showLoadFailure() {
    status.textContent = '页内问答未能加载。';
    const fallback = document.createElement('a');
    fallback.href = assistant.href;
    fallback.target = '_blank';
    fallback.rel = 'noopener noreferrer';
    fallback.textContent = '在新标签页打开小轨';
    status.append(' ', fallback);
  }

  dismiss.addEventListener('click', closePanel);
  window.addEventListener('message', (event) => {
    if (event.source !== frame.contentWindow || event.origin !== assistant.origin) return;
    if (event.data?.type === 'xiaogui-ready') {
      clearTimeout(timeout);
      ready = true;
      frame.hidden = false;
      status.hidden = true;
      dismiss.hidden = true;
    } else if (event.data?.type === 'xiaogui-close') {
      clearTimeout(timeout);
      ready = false;
      frame.removeAttribute('src');
      closePanel();
    }
  });
  link.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey || event.altKey) return;
    if (!localPlatform) {
      // Public deployments open in a new tab by default. HTTPS origins may be
      // embedded only after an explicit user gesture; plain public HTTP would
      // be blocked as mixed content by the HTTPS resource page anyway.
      if (assistant.protocol !== 'https:') return;
      if (!trustedPlatforms.has(assistant.origin)) {
        const allow = window.confirm(
          `是否允许 ${assistant.origin} 在此页面嵌入小轨？\n选择“取消”将在新标签页打开。`
        );
        if (!allow) return;
        trustedPlatforms.add(assistant.origin);
      }
    }
    event.preventDefault();
    panel.hidden = false;
    link.hidden = true;
    link.setAttribute('aria-expanded', 'true');
    if (ready) return;
    frame.hidden = true;
    status.hidden = false;
    dismiss.hidden = false;
    status.textContent = '正在打开小轨…';
    frame.src = assistant.href;
    clearTimeout(timeout);
    timeout = setTimeout(showLoadFailure, 8000);
  });
  shadow.append(style, link, panel);
  document.body.append(host);
})();
