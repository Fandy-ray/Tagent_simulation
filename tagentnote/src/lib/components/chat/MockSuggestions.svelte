<script lang="ts">
	type Suggestion = {
		id: string;
		title: [string, string];
		content: string;
	};

	type AssistMode = 'qa' | 'paper';

	type Props = {
		inputValue?: string;
		mode?: AssistMode;
		onSelect?: (content: string) => void;
	};

	let { inputValue = '', mode = 'qa', onSelect = () => {} }: Props = $props();

	// 开场引导语，不是知识内容：措辞对任何笔记本都成立。
	const qaSuggestions: Suggestion[] = [
		{
			id: 'suggestion-1',
			title: ['帮我梳理', '当前笔记本的核心概念'],
			content: '帮我梳理当前笔记本的核心概念。'
		},
		{
			id: 'suggestion-2',
			title: ['看一个建模例子', '用排队系统理解仿真'],
			content: '用排队系统举例，说明如何建立一个离散事件仿真模型。'
		},
		{
			id: 'suggestion-3',
			title: ['出几道题', '检验我掌握得怎么样'],
			content: '根据笔记内容出几道题考考我。'
		}
	];

	const paperSuggestions: Suggestion[] = [
		{
			id: 'paper-outline',
			title: ['生成大纲', '课程论文章节结构'],
			content: '请基于离散事件仿真，给我一份课程论文大纲。'
		},
		{
			id: 'paper-abstract',
			title: ['起草摘要', '含方法与结果占位'],
			content: '请为「排队系统仿真优化」起草一段中文摘要。'
		},
		{
			id: 'paper-method',
			title: ['方法段落', '实体事件与假设表'],
			content: '帮我写建模方法部分：包含实体、事件、资源与假设。'
		},
		{
			id: 'paper-experiment',
			title: ['实验设计', '对照场景与指标'],
			content: '给我一个仿真实验设计模板，包含基准/改进场景和评价指标。'
		},
		{
			id: 'paper-checklist',
			title: ['完整性检查', '投稿前清单'],
			content: '按课程论文清单检查：我还缺哪些部分？'
		}
	];

	const suggestions = $derived(mode === 'paper' ? paperSuggestions : qaSuggestions);

	let filteredSuggestions = $derived(
		inputValue.trim()
			? suggestions.filter((suggestion) => {
					const searchText =
						`${suggestion.title[0]} ${suggestion.title[1]} ${suggestion.content}`.toLowerCase();

					return searchText.includes(inputValue.trim().toLowerCase());
				})
			: suggestions
	);
</script>

{#if filteredSuggestions.length > 0}
	<section class="qa-prompts" aria-labelledby="qa-prompts-title">
		<h2 id="qa-prompts-title">试试这样问</h2>
		<div class="qa-prompt-list">
			{#each filteredSuggestions as suggestion (suggestion.id)}
				<button type="button" class="qa-prompt" onclick={() => onSelect(suggestion.content)}>
					<span>
						<strong>{suggestion.title[0]}</strong>
						<small>{suggestion.title[1]}</small>
					</span>
					<svg
						viewBox="0 0 24 24"
						fill="none"
						stroke="currentColor"
						stroke-width="1.6"
						stroke-linecap="round"
						stroke-linejoin="round"
						aria-hidden="true"
					>
						<path d="M6 18 18 6M8 6h10v10" />
					</svg>
				</button>
			{/each}
		</div>
	</section>
{/if}
