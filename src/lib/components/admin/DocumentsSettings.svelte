<script lang="ts">
	import Switch from '$lib/components/common/Switch.svelte';
	import ConfirmDialog from '$lib/components/common/ConfirmDialog.svelte';

	type RagConfig = {
		contentEngine: string;
		pdfExtractImages: boolean;
		pdfLoaderMode: 'page' | 'single';
		externalUrl: string;
		externalKey: string;
		tikaUrl: string;
		doclingUrl: string;
		doclingKey: string;
		doclingParams: string;
		datalabUrl: string;
		datalabKey: string;
		datalabUseLlm: boolean;
		datalabForceOcr: boolean;
		datalabOutputFormat: 'markdown' | 'json' | 'html';
		docIntelEndpoint: string;
		docIntelKey: string;
		docIntelModel: string;
		mistralUrl: string;
		mistralKey: string;
		mineruMode: 'local' | 'cloud';
		mineruUrl: string;
		mineruKey: string;
		mineruTimeout: number;
		mineruParams: string;
		bypassEmbedding: boolean;
		textSplitter: '' | 'token';
		markdownHeaderSplitter: boolean;
		chunkSize: number;
		chunkOverlap: number;
		chunkMinSize: number;
		embeddingEngine: '' | 'ollama' | 'openai' | 'azure_openai';
		embeddingModel: string;
		embeddingBatchSize: number;
		asyncEmbedding: boolean;
		embeddingConcurrency: number;
		openaiUrl: string;
		openaiKey: string;
		ollamaUrl: string;
		ollamaKey: string;
		azureUrl: string;
		azureKey: string;
		azureVersion: string;
		fullContext: boolean;
		hybridSearch: boolean;
		enrichHybridText: boolean;
		rerankEngine: '' | 'external';
		rerankModel: string;
		rerankUrl: string;
		rerankKey: string;
		topK: number;
		topKReranker: number;
		relevanceThreshold: number;
		bm25Weight: number | null;
		ragTemplate: string;
		allowedExtensions: string;
		maxFileSize: number;
		maxFileCount: number;
		imageWidth: number;
		imageHeight: number;
		googleDrive: boolean;
		onedrive: boolean;
	};

	const STORAGE_KEY = 'admin-mock-documents-settings';

	const defaults: RagConfig = {
		contentEngine: '',
		pdfExtractImages: false,
		pdfLoaderMode: 'page',
		externalUrl: '',
		externalKey: '',
		tikaUrl: '',
		doclingUrl: '',
		doclingKey: '',
		doclingParams: '',
		datalabUrl: '',
		datalabKey: '',
		datalabUseLlm: false,
		datalabForceOcr: false,
		datalabOutputFormat: 'markdown',
		docIntelEndpoint: '',
		docIntelKey: '',
		docIntelModel: 'prebuilt-layout',
		mistralUrl: '',
		mistralKey: '',
		mineruMode: 'local',
		mineruUrl: 'http://localhost:8000',
		mineruKey: '',
		mineruTimeout: 60,
		mineruParams: '',
		bypassEmbedding: false,
		textSplitter: '',
		markdownHeaderSplitter: false,
		chunkSize: 1000,
		chunkOverlap: 100,
		chunkMinSize: 0,
		embeddingEngine: '',
		embeddingModel: 'sentence-transformers/all-MiniLM-L6-v2',
		embeddingBatchSize: 1,
		asyncEmbedding: true,
		embeddingConcurrency: 0,
		openaiUrl: 'https://api.openai.com/v1',
		openaiKey: '',
		ollamaUrl: 'http://localhost:11434',
		ollamaKey: '',
		azureUrl: '',
		azureKey: '',
		azureVersion: '',
		fullContext: false,
		hybridSearch: false,
		enrichHybridText: false,
		rerankEngine: '',
		rerankModel: 'BAAI/bge-reranker-v2-m3',
		rerankUrl: '',
		rerankKey: '',
		topK: 4,
		topKReranker: 4,
		relevanceThreshold: 0,
		bm25Weight: null,
		ragTemplate: '',
		allowedExtensions: '',
		maxFileSize: 50,
		maxFileCount: 10,
		imageWidth: 0,
		imageHeight: 0,
		googleDrive: false,
		onedrive: false
	};

	function load(): RagConfig {
		if (typeof localStorage === 'undefined') return { ...defaults };
		try {
			const raw = localStorage.getItem(STORAGE_KEY);
			return raw ? { ...defaults, ...(JSON.parse(raw) as Partial<RagConfig>) } : { ...defaults };
		} catch {
			return { ...defaults };
		}
	}

	let config = $state<RagConfig>(load());
	let notice = $state('');
	let showResetUploads = $state(false);
	let showResetVector = $state(false);
	let showReindex = $state(false);

	function inform(message: string) {
		notice = message;
		setTimeout(() => notice = '', 2400);
	}

	function persist() {
		try {
			localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
		} catch {
			inform('无法保存到浏览器本地存储');
		}
	}

	function save() {
		if (config.contentEngine === 'external' && !config.externalUrl.trim()) {
			inform('使用外部文档解析服务时需要填写 URL');
			return;
		}
		if (config.contentEngine === 'tika' && !config.tikaUrl.trim()) {
			inform('使用 Tika 时需要填写服务器地址');
			return;
		}
		if (config.contentEngine === 'docling' && !config.doclingUrl.trim()) {
			inform('使用 Docling 时需要填写服务器地址');
			return;
		}
		if (config.contentEngine === 'document_intelligence' && !config.docIntelEndpoint.trim()) {
			inform('使用文档智能时需要填写端点地址');
			return;
		}
		if (config.contentEngine === 'mistral_ocr' && !config.mistralKey.trim()) {
			inform('使用 Mistral OCR 时需要填写 API Key');
			return;
		}
		if (config.contentEngine === 'mineru' && config.mineruMode === 'cloud' && !config.mineruKey.trim()) {
			inform('MinerU 云端模式需要填写 API Key');
			return;
		}
		for (const [label, value] of [['Docling 参数', config.doclingParams], ['MinerU 参数', config.mineruParams]] as const) {
			if (value.trim()) {
				try {
					JSON.parse(value);
				} catch {
					inform(`${label} 不是合法的 JSON`);
					return;
				}
			}
		}
		if (config.bm25Weight !== null && (config.bm25Weight < 0 || config.bm25Weight > 1)) {
			config.bm25Weight = 0.5;
		}
		persist();
		inform('文档设置已保存（本地 mock）');
	}

	function switchEngine(value: string) {
		config.contentEngine = value;
		if (value === 'mineru') config.mineruUrl = config.mineruMode === 'cloud' ? 'https://mineru.net/api/v4' : 'http://localhost:8000';
	}

	function switchEmbeddingEngine(value: string) {
		config.embeddingEngine = value as RagConfig['embeddingEngine'];
		if (value === 'ollama') config.embeddingModel = '';
		else if (value === 'openai' || value === 'azure_openai') config.embeddingModel = 'text-embedding-3-small';
		else config.embeddingModel = 'sentence-transformers/all-MiniLM-L6-v2';
	}

	function switchMineruMode(mode: 'local' | 'cloud') {
		const previous = config.mineruUrl;
		config.mineruMode = mode;
		if (!previous || previous === 'http://localhost:8000' || previous === 'https://mineru.net/api/v4') {
			config.mineruUrl = mode === 'cloud' ? 'https://mineru.net/api/v4' : 'http://localhost:8000';
		}
	}
</script>

<ConfirmDialog
	bind:show={showResetUploads}
	title="重置上传目录"
	message="这会删除本地上传目录中的全部文件（mock 操作）。"
	confirmLabel="重置"
	onConfirm={() => inform('上传目录已重置（本地 mock）')}
/>
<ConfirmDialog
	bind:show={showResetVector}
	title="重置向量存储与知识库"
	message="这会清空向量数据库中的全部内容（mock 操作）。"
	confirmLabel="重置"
	onConfirm={() => inform('向量存储已重置（本地 mock）')}
/>
<ConfirmDialog
	bind:show={showReindex}
	title="重建知识库向量"
	message="将重新计算所有知识库文件的向量（mock 操作）。"
	confirmLabel="重建"
	onConfirm={() => inform('已开始重建知识库向量（本地 mock）')}
/>

<form class="flex min-h-full flex-col justify-between gap-3 text-sm" onsubmit={(event) => { event.preventDefault(); save(); }}>
	<div class="min-h-0 flex-1 space-y-2.5 overflow-y-auto pr-1.5">
		<section class="mb-3">
			<div class="mb-2.5 mt-0.5 text-base font-medium">常规</div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />

			<div class="mb-2.5 flex w-full flex-col justify-between">
				<div class="mb-1 flex w-full justify-between">
					<div class="self-center text-xs font-medium">内容提取引擎</div>
					<select class="w-fit rounded-sm bg-transparent px-2 pr-8 text-right text-xs outline-none" value={config.contentEngine} onchange={(event) => switchEngine((event.currentTarget as HTMLSelectElement).value)}>
						<option value="">默认</option>
						<option value="external">外部</option>
						<option value="tika">Tika</option>
						<option value="docling">Docling</option>
						<option value="datalab_marker">Datalab Marker API</option>
						<option value="document_intelligence">文档智能</option>
						<option value="mistral_ocr">Mistral OCR</option>
						<option value="mineru">MinerU</option>
					</select>
				</div>

				{#if config.contentEngine === ''}
					<div class="mt-1 flex w-full">
						<div class="flex flex-1 items-center justify-between">
							<div class="self-center text-xs font-medium">PDF 提取图像（OCR）</div>
							<Switch bind:state={config.pdfExtractImages} ariaLabelledbyId="pdf-extract-images" />
						</div>
					</div>
					<div class="mt-2 flex w-full">
						<div class="flex flex-1 items-center justify-between">
							<div class="self-center text-xs font-medium">PDF 加载模式</div>
							<select class="w-fit rounded-sm bg-transparent px-2 pr-8 text-right text-xs outline-none" bind:value={config.pdfLoaderMode}>
								<option value="page">按页</option>
								<option value="single">合并</option>
							</select>
						</div>
					</div>
				{:else if config.contentEngine === 'external'}
					<div class="my-0.5 mt-1 flex gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="输入外部文档解析服务 URL" bind:value={config.externalUrl} />
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.externalKey} autocomplete="new-password" />
					</div>
				{:else if config.contentEngine === 'tika'}
					<input class="mt-1 w-full bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="输入 Tika 服务地址" bind:value={config.tikaUrl} />
				{:else if config.contentEngine === 'docling'}
					<div class="my-0.5 mt-1 flex gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="输入 Docling 服务地址" bind:value={config.doclingUrl} />
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.doclingKey} autocomplete="new-password" />
					</div>
					<div class="mt-2">
						<div class="mb-1 text-xs font-medium">参数</div>
						<textarea class="min-h-24 w-full resize-y rounded-lg bg-gray-50 px-3 py-2 text-xs outline-none dark:bg-gray-850" placeholder="以 JSON 格式输入附加参数" bind:value={config.doclingParams}></textarea>
					</div>
				{:else if config.contentEngine === 'datalab_marker'}
					<div class="my-0.5 mt-1 flex gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="Datalab Marker API 地址（默认 https://www.datalab.to/api/v1/marker）" bind:value={config.datalabUrl} />
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.datalabKey} autocomplete="new-password" />
					</div>
					<div class="mt-2 flex w-full justify-between">
						<div class="self-center text-xs font-medium">使用 LLM</div>
						<Switch bind:state={config.datalabUseLlm} ariaLabelledbyId="datalab-use-llm" />
					</div>
					<div class="mt-2 flex w-full justify-between">
						<div class="self-center text-xs font-medium">强制 OCR</div>
						<Switch bind:state={config.datalabForceOcr} ariaLabelledbyId="datalab-force-ocr" />
					</div>
					<div class="mt-2 flex w-full justify-between">
						<div class="self-center text-xs font-medium">输出格式</div>
						<select class="w-fit rounded-sm bg-transparent px-2 pr-8 text-right text-xs outline-none" bind:value={config.datalabOutputFormat}>
							<option value="markdown">Markdown</option>
							<option value="json">JSON</option>
							<option value="html">HTML</option>
						</select>
					</div>
				{:else if config.contentEngine === 'document_intelligence'}
					<div class="my-0.5 mt-1 flex gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="输入文档智能端点" bind:value={config.docIntelEndpoint} />
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.docIntelKey} autocomplete="new-password" />
					</div>
					<div class="mt-2">
						<div class="mb-1 text-xs font-medium">文档智能模型</div>
						<input class="w-full bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="prebuilt-layout" bind:value={config.docIntelModel} />
					</div>
				{:else if config.contentEngine === 'mistral_ocr'}
					<div class="my-0.5 mt-1 flex gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="Mistral API 地址" bind:value={config.mistralUrl} />
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.mistralKey} autocomplete="new-password" />
					</div>
				{:else if config.contentEngine === 'mineru'}
					<div class="mt-2 flex w-full justify-between">
						<div class="self-center text-xs font-medium">API 模式</div>
						<select class="w-fit rounded-sm bg-transparent px-2 pr-8 text-xs outline-none" value={config.mineruMode} onchange={(event) => switchMineruMode((event.currentTarget as HTMLSelectElement).value as 'local' | 'cloud')}>
							<option value="local">本地</option>
							<option value="cloud">云端</option>
						</select>
					</div>
					<input class="mt-2 w-full bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder={config.mineruMode === 'cloud' ? 'https://mineru.net/api/v4' : 'http://localhost:8000'} bind:value={config.mineruUrl} />
					<input class="mt-2 w-full bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="MinerU API Key" bind:value={config.mineruKey} autocomplete="new-password" />
					<div class="mt-2 flex w-full justify-between">
						<div class="self-center text-xs font-medium">API 超时（秒）</div>
						<input class="w-16 bg-transparent text-right text-sm outline-none" type="number" min="1" placeholder="60" bind:value={config.mineruTimeout} />
					</div>
					<div class="mt-2">
						<div class="text-xs font-medium">参数</div>
						<textarea class="mt-1.5 min-h-24 w-full resize-y rounded-lg bg-gray-50 px-3 py-2 text-xs outline-none dark:bg-gray-850" placeholder={'{\n  "enable_ocr": false,\n  "language": "en"\n}'} bind:value={config.mineruParams}></textarea>
					</div>
				{/if}
			</div>

			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">绕过嵌入与检索</div>
				<Switch bind:state={config.bypassEmbedding} ariaLabelledbyId="bypass-embedding" />
			</div>

			{#if !config.bypassEmbedding}
				<div class="mb-2.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">文本分割器</div>
					<select class="w-fit rounded-sm bg-transparent px-2 pr-8 text-right text-xs outline-none" bind:value={config.textSplitter}>
						<option value="">默认（字符）</option>
						<option value="token">Token（Tiktoken）</option>
					</select>
				</div>

				<div class="mb-2.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">Markdown 标题文本分割</div>
					<Switch bind:state={config.markdownHeaderSplitter} ariaLabelledbyId="markdown-splitter" />
				</div>

				<div class="mb-2.5 flex w-full gap-1.5">
					<div class="w-full justify-between">
						<div class="mb-1 min-w-fit self-center text-xs font-medium">分块大小</div>
						<input class="w-full rounded-lg bg-gray-50 px-4 py-1.5 text-sm outline-none dark:bg-gray-850 dark:text-gray-300" type="number" min="0" bind:value={config.chunkSize} />
					</div>
					<div class="w-full">
						<div class="mb-1 min-w-fit self-center text-xs font-medium">分块重叠</div>
						<input class="w-full rounded-lg bg-gray-50 px-4 py-1.5 text-sm outline-none dark:bg-gray-850 dark:text-gray-300" type="number" min="0" bind:value={config.chunkOverlap} />
					</div>
				</div>

				{#if config.markdownHeaderSplitter}
					<div class="mb-2.5 flex w-full justify-between">
						<div class="w-full">
							<div class="mb-1 min-w-fit self-center text-xs font-medium">分块最小目标大小</div>
							<input class="w-full rounded-lg bg-gray-50 px-4 py-1.5 text-sm outline-none dark:bg-gray-850 dark:text-gray-300" type="number" min="0" bind:value={config.chunkMinSize} />
						</div>
					</div>
				{/if}
			{/if}
		</section>

		{#if !config.bypassEmbedding}
			<section class="mb-3">
				<div class="mb-2.5 mt-0.5 text-base font-medium">嵌入</div>
				<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />

				<div class="mb-2.5 flex w-full flex-col justify-between">
					<div class="flex w-full justify-between">
						<div class="self-center text-xs font-medium">嵌入模型引擎</div>
						<select class="w-fit rounded-sm bg-transparent p-1 px-2 pr-8 text-right text-xs outline-none" value={config.embeddingEngine} onchange={(event) => switchEmbeddingEngine((event.currentTarget as HTMLSelectElement).value)}>
							<option value="">默认（SentenceTransformers）</option>
							<option value="ollama">Ollama</option>
							<option value="openai">OpenAI</option>
							<option value="azure_openai">Azure OpenAI</option>
						</select>
					</div>

					{#if config.embeddingEngine === 'openai'}
						<div class="my-0.5 mt-1 flex gap-2">
							<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="API Base URL" bind:value={config.openaiUrl} />
							<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.openaiKey} autocomplete="new-password" />
						</div>
					{:else if config.embeddingEngine === 'ollama'}
						<div class="my-0.5 mt-1 flex gap-2">
							<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="API Base URL" bind:value={config.ollamaUrl} />
							<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.ollamaKey} autocomplete="new-password" />
						</div>
					{:else if config.embeddingEngine === 'azure_openai'}
						<div class="my-0.5 mt-1 flex flex-col gap-2">
							<div class="flex gap-2">
								<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="API Base URL" bind:value={config.azureUrl} />
								<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.azureKey} autocomplete="new-password" />
							</div>
							<input class="w-full bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="版本" bind:value={config.azureVersion} />
						</div>
					{/if}
				</div>

				<div class="mb-2.5 flex w-full flex-col">
					<div class="mb-1 text-xs font-medium">嵌入模型</div>
					<div class="flex w-full gap-2">
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="设置嵌入模型" bind:value={config.embeddingModel} />
						{#if config.embeddingEngine === ''}
							<button type="button" class="rounded-lg px-2.5 text-gray-800 transition hover:bg-gray-100 dark:text-gray-100 dark:hover:bg-gray-850" aria-label="下载嵌入模型" title="下载嵌入模型" onclick={() => inform('嵌入模型已就绪（本地 mock）')}>
								<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="size-4" aria-hidden="true"><path d="M8.75 2.75a.75.75 0 0 0-1.5 0v5.69L5.03 6.22a.75.75 0 0 0-1.06 1.06l3.5 3.5a.75.75 0 0 0 1.06 0l3.5-3.5a.75.75 0 0 0-1.06-1.06L8.75 8.44V2.75Z" /><path d="M3.5 9.75a.75.75 0 0 0-1.5 0v1.5A2.75 2.75 0 0 0 4.75 14h6.5A2.75 2.75 0 0 0 14 11.25v-1.5a.75.75 0 0 0-1.5 0v1.5c0 .69-.56 1.25-1.25 1.25h-6.5c-.69 0-1.25-.56-1.25-1.25v-1.5Z" /></svg>
							</button>
						{/if}
					</div>
					<div class="mb-1 mt-1 text-xs text-gray-400 dark:text-gray-500">更换嵌入模型后需要重建知识库向量，可通过下方「重建」按钮完成。</div>
				</div>

				<div class="mb-2.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">嵌入批处理大小</div>
					<input class="w-14 bg-transparent text-center text-sm outline-none" type="number" min="-2" max="16000" step="1" bind:value={config.embeddingBatchSize} />
				</div>

				{#if config.embeddingEngine !== ''}
					<div class="mb-2.5 flex w-full justify-between">
						<div class="self-center text-xs font-medium">异步嵌入处理</div>
						<Switch bind:state={config.asyncEmbedding} ariaLabelledbyId="async-embedding" />
					</div>
					<div class="mb-2.5 flex w-full justify-between">
						<div class="self-center text-xs font-medium">嵌入并发请求数</div>
						<input class="w-14 bg-transparent text-center text-sm outline-none" type="number" min="0" step="1" bind:value={config.embeddingConcurrency} />
					</div>
				{/if}
			</section>

			<section class="mb-3">
				<div class="mb-2.5 mt-0.5 text-base font-medium">检索</div>
				<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />

				<div class="mb-2.5 flex w-full justify-between">
					<div class="self-center text-xs font-medium">完整上下文模式</div>
					<Switch bind:state={config.fullContext} ariaLabelledbyId="full-context" />
				</div>

				{#if !config.fullContext}
					<div class="mb-2.5 flex w-full justify-between">
						<div class="self-center text-xs font-medium">混合搜索</div>
						<Switch bind:state={config.hybridSearch} ariaLabelledbyId="hybrid-search" />
					</div>

					{#if config.hybridSearch}
						<div class="mb-2.5 flex w-full justify-between">
							<div class="self-center text-xs font-medium">增强混合搜索文本</div>
							<Switch bind:state={config.enrichHybridText} ariaLabelledbyId="enrich-hybrid" />
						</div>

						<div class="mb-2.5 flex w-full flex-col justify-between">
							<div class="flex w-full justify-between">
								<div class="self-center text-xs font-medium">重排序引擎</div>
								<select class="w-fit rounded-sm bg-transparent p-1 px-2 pr-8 text-right text-xs outline-none" bind:value={config.rerankEngine}>
									<option value="">默认（SentenceTransformers）</option>
									<option value="external">外部</option>
								</select>
							</div>
							{#if config.rerankEngine === 'external'}
								<div class="my-0.5 mt-1 flex gap-2">
									<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="API Base URL" bind:value={config.rerankUrl} />
									<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="password" placeholder="API Key" bind:value={config.rerankKey} autocomplete="new-password" />
								</div>
							{/if}
						</div>

						<div class="mb-2.5 flex w-full flex-col">
							<div class="mb-1 text-xs font-medium">重排序模型</div>
							<input class="w-full bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="设置重排序模型（如 BAAI/bge-reranker-v2-m3）" bind:value={config.rerankModel} />
						</div>
					{/if}

					<div class="mb-2.5 flex w-full items-center justify-between gap-2">
						<div class="self-center whitespace-nowrap text-xs font-medium">Top K</div>
						<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="输入 Top K" bind:value={config.topK} />
					</div>

					{#if config.hybridSearch}
						<div class="mb-2.5 flex w-full items-center justify-between gap-2">
							<div class="self-center whitespace-nowrap text-xs font-medium">Top K 重排序</div>
							<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="输入 Top K 重排序" bind:value={config.topKReranker} />
						</div>

						<div class="mb-2.5 flex w-full flex-col justify-between">
							<div class="flex w-full items-center justify-between gap-2">
								<div class="self-center whitespace-nowrap text-xs font-medium">相关性阈值</div>
								<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" max="1" step="0.01" placeholder="输入分数" bind:value={config.relevanceThreshold} />
							</div>
							<div class="mt-1 text-xs text-gray-400 dark:text-gray-500">设置最小分数后，仅返回分数不低于该值的文档。</div>
						</div>

						<div class="mb-2.5 w-full justify-between py-0.5">
							<div class="flex w-full items-center justify-between">
								<div class="self-center text-xs font-medium">BM25 权重</div>
								<button class="flex shrink-0 rounded-sm px-3 py-1 text-xs outline-none transition" type="button" onclick={() => { config.bm25Weight = (config.bm25Weight ?? null) === null ? 0.5 : null; }}>{config.bm25Weight === null ? '默认' : '自定义'}</button>
							</div>
							{#if config.bm25Weight !== null}
								<div class="mt-0.5 flex space-x-2">
									<div class="flex-1">
										<input type="range" min="0" max="1" step="0.05" bind:value={config.bm25Weight} class="h-2 w-full cursor-pointer appearance-none rounded-lg dark:bg-gray-700" />
										<div class="py-0.5">
											<div class="flex w-full justify-between">
												<div class="text-left text-xs">语义</div>
												<div class="text-right text-xs">关键词</div>
											</div>
										</div>
									</div>
									<input class="w-14 bg-transparent text-center text-sm" type="number" min="0" max="1" step="any" bind:value={config.bm25Weight} />
								</div>
							{/if}
						</div>
					{/if}
				{/if}

				<div class="mb-2.5 flex w-full flex-col justify-between">
					<div class="mb-1 text-xs font-medium">RAG 模板</div>
					<textarea class="min-h-20 w-full resize-y rounded-lg bg-gray-50 px-3 py-2 text-xs outline-none dark:bg-gray-850" placeholder="留空使用默认提示词，或输入自定义提示词" bind:value={config.ragTemplate}></textarea>
				</div>
			</section>
		{/if}

		<section class="mb-3">
			<div class="mb-2.5 mt-0.5 text-base font-medium">文件</div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />

			<div class="mb-2.5 flex w-full items-center justify-between gap-2">
				<div class="self-center whitespace-nowrap text-xs font-medium">允许的文件扩展名</div>
				<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" placeholder="例如 pdf, docx, txt" bind:value={config.allowedExtensions} />
			</div>
			<div class="mb-2.5 flex w-full items-center justify-between gap-2">
				<div class="self-center whitespace-nowrap text-xs font-medium">最大上传大小（MB）</div>
				<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="留空表示不限" bind:value={config.maxFileSize} />
			</div>
			<div class="mb-2.5 flex w-full items-center justify-between gap-2">
				<div class="self-center whitespace-nowrap text-xs font-medium">最大上传数量</div>
				<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="留空表示不限" bind:value={config.maxFileCount} />
			</div>
			<div class="mb-2.5 flex w-full items-center justify-between gap-2">
				<div class="self-center whitespace-nowrap text-xs font-medium">图像压缩宽度</div>
				<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="留空表示不压缩" bind:value={config.imageWidth} />
			</div>
			<div class="mb-2.5 flex w-full items-center justify-between gap-2">
				<div class="self-center whitespace-nowrap text-xs font-medium">图像压缩高度</div>
				<input class="w-full flex-1 bg-transparent text-sm outline-none placeholder:text-gray-400" type="number" min="0" placeholder="留空表示不压缩" bind:value={config.imageHeight} />
			</div>
		</section>

		<section class="mb-3">
			<div class="mb-2.5 mt-0.5 text-base font-medium">集成</div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />
			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">Google Drive</div>
				<Switch bind:state={config.googleDrive} ariaLabelledbyId="google-drive" />
			</div>
			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">OneDrive</div>
				<Switch bind:state={config.onedrive} ariaLabelledbyId="onedrive" />
			</div>
		</section>

		<section class="mb-3">
			<div class="mb-2.5 mt-0.5 text-base font-medium">危险区域</div>
			<hr class="my-2 border-gray-100/30 dark:border-gray-850/30" />
			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">重置上传目录</div>
				<button class="text-xs" type="button" onclick={() => showResetUploads = true}>重置</button>
			</div>
			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">重置向量存储 / 知识库</div>
				<button class="text-xs" type="button" onclick={() => showResetVector = true}>重置</button>
			</div>
			<div class="mb-2.5 flex w-full justify-between">
				<div class="self-center text-xs font-medium">重建知识库向量</div>
				<button class="text-xs" type="button" onclick={() => showReindex = true}>重建</button>
			</div>
		</section>
	</div>

	<div class="flex justify-end pt-3 text-sm font-medium">
		<button class="rounded-full bg-black px-3.5 py-1.5 text-sm font-medium text-white transition hover:bg-gray-900 dark:bg-white dark:text-black dark:hover:bg-gray-100" type="submit">保存</button>
	</div>
</form>

{#if notice}<div class="fixed bottom-5 right-5 z-[100] max-w-sm rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900" role="status">{notice}</div>{/if}
