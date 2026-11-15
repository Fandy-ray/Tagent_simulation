<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/state';
	import { learningContextParams, spaceStages, spaceTopics } from '$lib/data/spaceLearning';
	import type { PageProps } from './$types';

	let { data }: PageProps = $props();

	type Resource = { type: string; title: string; source: string; guide: string; url?: string; panels?: typeof orbitComic };
	const orbitComic = [
		{ art: '⚾ ↘', title: '扔出一颗球', text: '球向前飞，地球的引力同时把它往下拉。' },
		{ art: '⚾ ⟶', title: '如果再快一点', text: '想象周围没有空气，也没有山挡路。球飞得越快，落地前就能走得越远。' },
		{ art: '🛰️ ↷ 🌍', title: '地面也在弯', text: '速度正合适时，球往下落的同时，弯曲的地表也在远离它。' },
		{ art: '🛰️ ⤾ 🌍', title: '绕成一圈', text: '卫星不断被地球拉向内侧，同时继续向前飞，就这样沿着轨道绕行。' }
	];

	const stationComic = [
		{ art: '☀️ 🧑‍🚀', title: '起床', text: '航天员从固定好的睡袋里钻出来，开始一天的工作。' },
		{ art: '🍱 🥄', title: '吃饭', text: '食品装在专用包装里。打开包装时，要小心碎屑飘走。' },
		{ art: '🚲 🧑‍🚀', title: '锻炼', text: '航天员用太空自行车和跑台锻炼肌肉。' },
		{ art: '🌙 🛌', title: '休息', text: '睡觉前把睡袋固定好，这样就不会飘到别处。' }
	];


	const library: Partial<Record<string, Resource[]>> = {
		satellites: [
			{ type: '动画视频', title: '跟着卫星绕地球', source: 'NASA 科学可视化工作室', guide: '看陆地卫星绕地球飞。试着用手指在屏幕上画出它走过的路线。', url: 'https://svs.gsfc.nasa.gov/3939/' },
			{ type: '四格漫画', title: '小卫星怎么绕起了圈？', source: '航空航天探索实验室', guide: '从扔球开始想一想，地球怎样把小卫星的路线拉弯。', panels: orbitComic }
		],
		motion: [
			{ type: '原理视频', title: '航天员在空间站讲轨道', source: 'NASA+ · 英语', guide: '观察演示。试着画两支箭头，一支沿运动方向，另一支指向地心。', url: 'https://plus.nasa.gov/video/stemonstrations-orbits/' },
			{ type: '科普阅读', title: '什么是卫星？', source: 'NASA STEM · 英文', guide: '推荐阅读卫星如何绕地球运行一节，比较极地轨道和地球静止轨道。', url: 'https://www.nasa.gov/learning-resources/for-kids-and-students/what-is-a-satellite-grades-5-8/' }
		],
		model: [
			{ type: '技术视频', title: 'MMS 四星编队的轨道设计', source: 'NASA 科学可视化工作室 · 英语', guide: '观察四颗卫星的编队如何随任务阶段变化，思考为何要同时在多个位置测量。', url: 'https://svs.gsfc.nasa.gov/11485/' },
			{ type: '技术文档', title: '轨道参数与典型轨道', source: 'NASA《航天飞行基础》· 英文', guide: '阅读轨道参数和地球静止轨道两节。用圆轨道模型估算静止轨道的半径。', url: 'https://science.nasa.gov/learn/basics-of-space-flight/chapter5-1/' }
		],
		station: [
			{ type: '科普阅读', title: '太空中怎么吃饭睡觉？', source: '中国载人航天官方网站', guide: '找到关于吃饭和睡觉的问题，看看航天员怎样处理会飘起来的食物和睡袋。', url: 'https://www.cmse.gov.cn/col/col1285/index.html' },
			{ type: '四格漫画', title: '太空生活的一天', source: '航空航天探索实验室', guide: '跟着航天员看看起床、吃饭、运动和休息有什么不同。', panels: stationComic }
		],
		moonlight: [
			{ type: '原理视频', title: '月亮为什么会变形？', source: 'NASA eClips · 英语', guide: '边看边画下太阳、地球和月球的位置，想一想为什么每天看到的亮面不同。', url: 'https://science.nasa.gov/eclips/videos/moon-phases/' },
			{ type: '科普阅读', title: '月相与月食', source: 'NASA Science · 英文', guide: '比较月相和月食各自的成因，找出什么时候月球会进入地球的影子。', url: 'https://science.nasa.gov/moon/moon-phases/' }
		],
		observations: [
			{ type: '技术文档', title: 'Landsat 的波段与空间分辨率', source: '美国地质调查局 · 英文', guide: '对比 Landsat 8/9 的全色、多光谱和热红外波段。分别记录像元大小与观测波段。', url: 'https://www.usgs.gov/faqs/what-are-band-designations-landsat-satellites' },
			{ type: '技术文献', title: '用遥感监测矿区与生态恢复', source: '美国地质调查局 · 英文 PDF', guide: '阅读空间分辨率和光谱分辨率相关段落，比较细节辨识与地物分类各需要什么数据。', url: 'https://pubs.usgs.gov/circ/1525/cir1525.pdf' }
		]
	};


	let filter = $state('全部');
	const topics = $derived(spaceTopics[data.stage]);
	const topic = $derived(topics.find(({ id }) => id === page.url.searchParams.get('topic')));
	const groups = $derived((topic ? [topic] : topics).map((entry) => ({
		...entry,
		resources: library[entry.id] ?? []
	})));
	const types = $derived([...new Set(groups.flatMap(({ resources }) => resources.map(({ type }) => type)))]);
	const currentFilter = $derived(types.includes(filter) ? filter : '全部');
	const back = $derived(resolve('/space-exploration/learn/[stage]', { stage: data.stage }) + page.url.search);

	function originalHref(url: string, title: string, topicId: string) {
		const lesson = topic?.id === topicId
			? topic.lessons.find(({ id }) => id === page.url.searchParams.get('lesson'))
			: undefined;
		const params = learningContextParams(data.stage, topicId, lesson?.id);
		params.set('resource', title);
		if (url === 'https://pubs.usgs.gov/circ/1525/cir1525.pdf') {
			return `${resolve('/space-assistant')}?${params}&document=usgs-1525`;
		}
		params.set('platform', page.url.origin);
		return `${url}#xiaogui=${params}`;
	}
</script>

<svelte:head><title>空天资料库 · {spaceStages[data.stage].label}</title></svelte:head>

<main class="learn-frame learn-selection">
	<a class="learn-button secondary" href={back}>← 返回学习</a>
	<h1>空天资料库</h1>
	<p class="subtitle">{spaceStages[data.stage].label} · {topic?.title ?? '全部章节'}</p>
	<div class="filters" role="group" aria-label="按资料类型筛选">
		{#each ['全部', ...types] as type (type)}
			<button type="button" class="learn-button secondary" aria-pressed={currentFilter === type} onclick={() => (filter = type)}>{type}</button>
		{/each}
	</div>
	{#each groups as group (group.id)}
		{@const visible = group.resources.filter(({ type }) => currentFilter === '全部' || type === currentFilter)}
		{#if visible.length}
			<section class="topic-resources" aria-label={group.title}>
				{#if !topic}<h2>{group.title}</h2>{/if}
	<div class="resources" class:primary={data.stage === 'primary'}>
		{#each visible as item (item.title)}
			<article class="resource">
				<p class="metadata">{item.type} · {item.source}</p>
				<h2>{item.title}</h2>
				<p>{item.guide}</p>
				{#if item.url}
					<a class="learn-button" href={originalHref(item.url, item.title, group.id)} target="_blank" rel="noopener noreferrer">{item.url.endsWith('.pdf') ? '阅读 PDF' : '打开原站'} ↗</a>
				{:else if item.panels}
					<details>
						<summary>阅读四格漫画</summary>
						<ol class="comic">
							{#each item.panels as panel (panel.title)}
								<li>
									<div class="art" aria-hidden="true">{panel.art}</div>
									<h3>{panel.title}</h3>
									<p>{panel.text}</p>
								</li>
							{/each}
						</ol>
					</details>
				{/if}
			</article>
		{/each}
	</div>
			</section>
		{/if}
	{/each}
</main>

<style>
	h1 { margin: 1.5rem 0 0.25rem; font-size: clamp(2rem, 5vw, 3.25rem); font-weight: 700; }
	.subtitle, .metadata { color: var(--m3-on-surface-variant); }
	.filters { display: flex; flex-wrap: wrap; gap: 8px; margin: 1.4rem 0; }
	.topic-resources + .topic-resources { margin-top: 2rem; }
	.topic-resources > h2 { margin-bottom: 0.7rem; font-size: 1.2rem; font-weight: 650; }
	.resources { display: grid; gap: 14px; }
	.resource { padding: clamp(16px, 3vw, 28px); border: 1px solid var(--m3-outline-variant); border-radius: 16px; background: var(--m3-surface-low); }
	.resource h2 { margin-block: 0.4rem; font-size: 1.35rem; font-weight: 650; }
	.resource > p:not(.metadata) { margin-bottom: 1rem; line-height: 1.65; }
	.metadata { font-size: 0.875rem; }
	.primary .resource { border-top: 3px solid var(--m3-primary); }
	summary { width: fit-content; cursor: pointer; color: var(--m3-primary); }
	.comic { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 190px), 1fr)); gap: 12px; margin-top: 14px; padding: 0; list-style: none; }
	.comic li { border: 1px solid var(--m3-outline-variant); border-radius: 12px; padding: 12px; background: var(--m3-surface-high); }
	.comic h3 { font-weight: 650; }
	.comic p { margin-top: 5px; }
	.art { display: grid; min-height: 74px; place-items: center; margin-bottom: 10px; border-radius: 8px; background: var(--m3-background); font-size: 1.9rem; letter-spacing: 0.1em; }
</style>
