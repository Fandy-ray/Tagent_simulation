<script lang="ts">
	import PaperNotePicker from '$lib/components/chat/PaperNotePicker.svelte';
	import type { KnowledgeCollection } from '$lib/data/knowledge';
	import {
		contextFieldsForSection,
		PAPER_INTENTS,
		PAPER_INTENTS_BY_SECTION,
		PAPER_SECTIONS,
		DEFAULT_PAPER_CONTEXT,
		type PaperContext,
		type PaperFileAttachment,
		type PaperIntent,
		type PaperNoteReference,
		type PaperTextField,
		type PaperSection
	} from '$lib/data/paperWorkflow';

	type Props = {
		title?: string;
		keywords?: string;
		section?: PaperSection;
		context?: PaperContext;
		sourceName?: string;
		collections?: KnowledgeCollection[];
		compact?: boolean;
		onChange?: (task: {
			title: string;
			keywords: string;
			section: PaperSection;
			context: PaperContext;
		}) => void;
		onIntent?: (intent: PaperIntent) => void;
		/** 传了才显示「让助手出题」：按当前笔记本出一道小论文题，出在对话里 */
		onProposeTopic?: (() => void) | null;
	};

	let {
		title = $bindable(''),
		keywords = $bindable(''),
		section = $bindable<PaperSection>('实验设计'),
		context = $bindable<PaperContext>({ ...DEFAULT_PAPER_CONTEXT }),
		sourceName = '未绑定知识库',
		collections = [],
		compact = false,
		onChange = () => {},
		onIntent = () => {},
		onProposeTopic = null
	}: Props = $props();

	let detailsOpen = $state(true);
	let previousCompact = $state(false);

	$effect(() => {
		if (compact !== previousCompact) {
			detailsOpen = !compact;
			previousCompact = compact;
		}
	});

	const emitChange = () => onChange({ title, keywords, section, context });
	const contextFields = $derived(contextFieldsForSection(section));
	const visibleIntents = $derived(
		PAPER_INTENTS.filter((intent) => PAPER_INTENTS_BY_SECTION[section].includes(intent.id))
	);

	const updateContext = (id: keyof PaperContext, value: string) => {
		context = { ...context, [id]: value };
		onChange({ title, keywords, section, context });
	};

	const updateAttachedNotes = (id: PaperTextField, notes: PaperNoteReference[]) => {
		context = {
			...context,
			attachedNotes: {
				...(context.attachedNotes ?? {}),
				[id]: notes
			}
		};
		onChange({ title, keywords, section, context });
	};

	const addDataFiles = async (event: Event) => {
		const input = event.currentTarget as HTMLInputElement;
		const files = Array.from(input.files ?? []);
		if (files.length === 0) return;

		const parsed: PaperFileAttachment[] = [];
		for (const file of files) {
			const id = `${file.name}-${file.size}-${file.lastModified}`;
			if (context.attachedFiles?.some((item) => item.id === id)) continue;

			let content = '';
			let status: string;
			try {
				if (/\.(xlsx|xls)$/i.test(file.name)) {
					status = '暂不支持直接读取 Excel，请另存为 CSV 后再上传';
				} else {
					content = (await file.text()).slice(0, 16000);
					status = '已读取文本内容，已截取前 16000 个字符';
				}
			} catch {
				status = '文件已添加，但内容解析失败，请检查文件格式';
			}

			parsed.push({
				id,
				name: file.name,
				type: file.type || 'application/octet-stream',
				size: file.size,
				content,
				status
			});
		}

		if (parsed.length > 0) {
			context = { ...context, attachedFiles: [...(context.attachedFiles ?? []), ...parsed] };
			onChange({ title, keywords, section, context });
		}
		input.value = '';
	};

	const removeDataFile = (id: string) => {
		context = {
			...context,
			attachedFiles: (context.attachedFiles ?? []).filter((file) => file.id !== id)
		};
		onChange({ title, keywords, section, context });
	};
</script>

<section
	class={`mx-auto w-full max-w-4xl rounded-2xl border border-amber-300/15 bg-amber-200/[0.04] text-left shadow-xl shadow-black/10 ${compact ? 'px-3 py-2' : 'px-4 py-4'}`}
	aria-label="论文任务卡"
>
	<div class="flex flex-wrap items-center justify-between gap-2">
		<div class="flex min-w-0 items-center gap-2">
			<span
				class="flex size-7 shrink-0 items-center justify-center rounded-lg bg-amber-300/15 text-amber-200"
				aria-hidden="true">✦</span
			>
			<div class="min-w-0">
				<div class="text-xs font-medium tracking-[0.16em] text-amber-200/80 uppercase">
					论文任务
				</div>
				<div class="truncate text-sm text-gray-200">
					{title.trim() || '先填写题目，再开始分章节写作'}
				</div>
				<div class="mt-0.5 truncate text-[11px] text-gray-500">引用资料：{sourceName}</div>
			</div>
		</div>

		<div class="flex items-center gap-2">
			<button
				type="button"
				class="rounded-lg px-2 py-1 text-xs text-gray-400 transition hover:bg-white/10 hover:text-white"
				onclick={() => (detailsOpen = !detailsOpen)}
				aria-expanded={detailsOpen}
			>
				{detailsOpen ? '收起' : '编辑任务'}
			</button>
		</div>
	</div>

	{#if detailsOpen}
		<div class="mt-3 grid gap-3 md:grid-cols-[1.2fr_1fr]">
			<div class="text-xs font-medium text-gray-400 md:col-span-2">第一步 · 论文基础</div>
			<div class="block">
				<div class="mb-1 flex items-center justify-between gap-2">
					<label for="paper-task-title" class="block text-xs text-gray-500">论文题目</label>
					{#if onProposeTopic}
						<button
							type="button"
							class="text-xs text-amber-300/90 transition hover:text-amber-200"
							onclick={onProposeTopic}
							title="按课程材料出一道小论文题（选了笔记本就只用选中的）"
						>
							让助手出题
						</button>
					{/if}
				</div>
				<input
					id="paper-task-title"
					class="h-9 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-amber-300/50"
					placeholder="例如：基于排队系统的服务窗口仿真优化"
					bind:value={title}
					oninput={emitChange}
				/>
				{#if onProposeTopic}
					<p class="mt-1 text-[11px] text-gray-600">交稿批改时按这个题目判「切题与内容」。</p>
				{/if}
			</div>
			<label class="block">
				<span class="mb-1 block text-xs text-gray-500">关键词</span>
				<input
					class="h-9 w-full rounded-lg border border-white/10 bg-black/20 px-3 text-sm text-gray-100 outline-none placeholder:text-gray-600 focus:border-amber-300/50"
					placeholder="排队系统、吞吐量、等待时间"
					bind:value={keywords}
					oninput={emitChange}
				/>
			</label>
		</div>
	{/if}

	{#if detailsOpen}
		<div class="mt-3">
			<div class="mb-2 text-xs font-medium text-gray-400">第二步 · 当前章节</div>
			<p class="mb-2 text-[11px] text-gray-500">
				章节按钮是帮你写这一节，结果以对话回答给出；要打分和逐句批注，把整篇正文粘进下方输入框点「交稿批改」。
			</p>
			<div class="flex flex-wrap gap-2">
				{#each PAPER_SECTIONS as item (item)}
					<button
						type="button"
						class={`rounded-xl border px-3 py-2 text-left transition focus:ring-2 focus:ring-amber-300/40 focus:outline-none ${
							section === item
								? 'border-amber-300/50 bg-amber-300/15 text-amber-100 shadow-sm shadow-amber-950/30'
								: 'border-white/10 bg-white/[0.03] text-gray-400 hover:border-amber-200/30 hover:bg-white/[0.06] hover:text-gray-200'
						}`}
						onclick={() => {
							section = item;
							emitChange();
						}}
						aria-pressed={section === item}
					>
						<span class="block text-xs font-medium">{item}</span>
						<span class="mt-0.5 block text-[11px] text-gray-500">
							{section === item ? '当前工作章节' : '切换章节'}
						</span>
					</button>
				{/each}
			</div>
		</div>

		<div class="mt-4 border-t border-white/10 pt-3">
			<div class="mb-2 text-xs font-medium text-gray-400">第三步 · 撰写内容</div>
			<p class="mb-3 text-[11px] text-gray-500">
				根据“{section}”显示需要补充的信息，填写后再选择具体写作动作。
			</p>
			<div class="grid gap-2 md:grid-cols-2">
				{#each contextFields as field (field.id)}
					<label class="block">
						<span class="mb-1 block text-[11px] text-gray-500">{field.label}</span>
						<textarea
							class="min-h-14 w-full resize-y rounded-lg border border-white/10 bg-black/20 px-3 py-2 text-xs text-gray-100 outline-none placeholder:text-gray-600 focus:border-amber-300/50"
							placeholder={field.placeholder}
							value={context[field.id]}
							oninput={(event) =>
								updateContext(field.id, (event.currentTarget as HTMLTextAreaElement).value)}
						></textarea>
						<PaperNotePicker
							{collections}
							selected={context.attachedNotes?.[field.id] ?? []}
							onChange={(notes) => updateAttachedNotes(field.id, notes)}
						/>
						{#if field.id === 'dataSource' || field.id === 'dataStatus' || field.id === 'resultSummary'}
							<div class="mt-2">
								<div class="flex flex-wrap items-center gap-2">
									<label
										class="inline-flex cursor-pointer items-center gap-1 rounded-md border border-white/10 px-2 py-1 text-[11px] text-gray-400 transition hover:border-amber-200/30 hover:bg-white/[0.06] hover:text-amber-100"
									>
										<span aria-hidden="true">↑</span>
										上传 CSV / TSV
										<input
											type="file"
											class="hidden"
											accept=".csv,.tsv,.txt,.md,.json,text/csv, text/tab-separated-values, application/json, text/markdown"
											multiple
											onchange={addDataFiles}
										/>
									</label>
									<span class="text-[11px] text-gray-600"
										>Excel 请先另存为 CSV；内容会截取后发送给智能体</span
									>
								</div>
								{#if context.attachedFiles && context.attachedFiles.length > 0}
									<div class="mt-1 space-y-1">
										{#each context.attachedFiles as file (file.id)}
											<div class="flex items-center gap-1 text-[11px] text-gray-500">
												<span class="min-w-0 flex-1 truncate">{file.name}</span>
												<span class="max-w-48 truncate text-gray-600">{file.status}</span>
												<button
													type="button"
													class="shrink-0 px-1 text-gray-600 hover:text-gray-200"
													onclick={() => removeDataFile(file.id)}
													aria-label={`移除文件 ${file.name}`}
												>
													×
												</button>
											</div>
										{/each}
									</div>
								{/if}
							</div>
						{/if}
					</label>
				{/each}
			</div>

			<div class="mt-3 flex flex-wrap gap-2">
				{#each visibleIntents as intent (intent.id)}
					<button
						type="button"
						class="rounded-xl border border-amber-200/15 bg-white/[0.04] px-3 py-2 text-left transition hover:-translate-y-0.5 hover:border-amber-200/40 hover:bg-amber-200/10 focus:ring-2 focus:ring-amber-300/40 focus:outline-none"
						onclick={() => {
							// 提交后收起工作区，避免任务卡遮挡正在生成的正文。
							detailsOpen = false;
							onIntent(intent.id);
						}}
					>
						<span class="block text-xs font-medium text-amber-100">{intent.title}</span>
						<span class="mt-0.5 block text-[11px] text-gray-500">{intent.description}</span>
					</button>
				{/each}
			</div>
		</div>
	{/if}
</section>
