<script lang="ts">
	import { resolve } from '$app/paths';
	import { page } from '$app/stores';
	import { untrack } from 'svelte';
	import AddConnectionModal from '$lib/components/chat/Settings/AddConnectionModal.svelte';
	import AdminModels from '$lib/components/admin/Models.svelte';
	import AdminAgentModels from '$lib/components/admin/AgentModels.svelte';
	import AdminEvaluationSettings from '$lib/components/admin/EvaluationSettings.svelte';
	import AdminIntegrations from '$lib/components/admin/Integrations.svelte';
	import AdminDocumentsSettings from '$lib/components/admin/DocumentsSettings.svelte';
	import AdminDatabase from '$lib/components/admin/Database.svelte';

	type SettingItem = {
		key: string;
		label: string;
		description: string;
		kind: 'toggle' | 'text' | 'number' | 'select' | 'textarea';
		options?: string[];
		value: boolean | string | number;
		section?: string;
	};
	type SettingTab = { id: string; title: string; keywords: string[]; items: SettingItem[] };
	const rawDefinitions: SettingTab[] = [
		{
			id: 'general',
			title: '通用',
			keywords: ['版本 更新 语言 主题 数据 用户 角色 ldap webhook 社区 频道'],
			items: [
				{
					key: 'defaultRole',
					label: '默认用户角色',
					description: '',
					kind: 'select',
					options: ['待激活', '用户', '管理员'],
					value: '待激活',
					section: 'authentication'
				},
				{
					key: 'defaultGroup',
					label: '默认用户组',
					description: '',
					kind: 'select',
					options: ['None', '教学团队', '研究团队'],
					value: 'None',
					section: 'authentication'
				},
				{
					key: 'registration',
					label: '允许新用户注册',
					description: '',
					kind: 'toggle',
					value: false,
					section: 'authentication'
				},
				{
					key: 'showAdminDetails',
					label: '在待激活用户的界面中显示管理员邮箱等详细信息',
					description: '',
					kind: 'toggle',
					value: true,
					section: 'authentication'
				},
				{
					key: 'adminEmail',
					label: '管理员联系邮箱',
					description: '',
					kind: 'text',
					value: '',
					section: 'authentication'
				},
				{
					key: 'pendingTitle',
					label: '待激活用户界面标题',
					description: '',
					kind: 'textarea',
					value: '',
					section: 'authentication'
				},
				{
					key: 'pendingContent',
					label: '待激活用户界面内容',
					description: '',
					kind: 'textarea',
					value: '',
					section: 'authentication'
				},
				{
					key: 'enableApiKeys',
					label: '启用 API 密钥',
					description: '',
					kind: 'toggle',
					value: false,
					section: 'authentication'
				},
				{
					key: 'apiRestrictions',
					label: '限制 API 密钥可访问的端点',
					description: '仅允许访问下方配置的 API 端点。',
					kind: 'toggle',
					value: false,
					section: 'authentication'
				},
				{
					key: 'allowedEndpoints',
					label: '允许的 API 端点',
					description: '使用逗号分隔多个路径。',
					kind: 'text',
					value: '/api/v1/messages, /api/v1/channels',
					section: 'authentication'
				},
				{
					key: 'jwtExpiration',
					label: 'JWT 过期时间',
					description: '',
					kind: 'text',
					value: '4w',
					section: 'authentication'
				},
				{
					key: 'enableLdap',
					label: '启用 LDAP',
					description: '允许通过 LDAP 服务器进行身份验证。',
					kind: 'toggle',
					value: false,
					section: 'authentication'
				},
				{
					key: 'ldapHost',
					label: 'LDAP 服务器地址',
					description: 'LDAP 主机地址及端口，例如 ldap.example.com:389。',
					kind: 'text',
					value: '',
					section: 'authentication'
				},
				{
					key: 'communitySharing',
					label: '启用分享至社区',
					description: '',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'messageRating',
					label: '启用模型回答结果评价',
					description: '',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'folders',
					label: '启用文件夹',
					description: '允许用户使用文件夹整理对话。',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'folderMaxFiles',
					label: '分组最大文件数量',
					description: '每个分组允许的最大文件数量。',
					kind: 'number',
					value: '',
					section: 'features'
				},
				{
					key: 'notes',
					label: '启用笔记（Beta）',
					description: '允许用户创建和管理笔记。',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'channels',
					label: '频道 (Beta)',
					description: '',
					kind: 'toggle',
					value: false,
					section: 'features'
				},
				{
					key: 'memories',
					label: '记忆 (Beta)',
					description: '',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'userWebhooks',
					label: '启用用户 Webhook',
					description: '允许用户配置个人 Webhook。',
					kind: 'toggle',
					value: false,
					section: 'features'
				},
				{
					key: 'userStatus',
					label: '启用用户状态',
					description: '显示用户在线状态。',
					kind: 'toggle',
					value: true,
					section: 'features'
				},
				{
					key: 'responseWatermark',
					label: '复制时添加水印',
					description: '',
					kind: 'textarea',
					value: '',
					section: 'features'
				},
				{
					key: 'webuiUrl',
					label: 'WebUI URL',
					description: '输入 WebUI 的公共链接。此链接将用于在通知中生成链接。',
					kind: 'text',
					value: '',
					section: 'features'
				},
				{
					key: 'webhook',
					label: 'Webhook URL',
					description: '接收系统事件的通知地址。',
					kind: 'text',
					value: '',
					section: 'features'
				}
			]
		},
		{
			id: 'connections',
			title: '外部连接',
			keywords: ['ollama openai api base url direct connections proxy key'],
			items: [
				{ key: 'enableOpenAI', label: 'OpenAI 接口', description: '', kind: 'toggle', value: true },
				{ key: 'enableOllama', label: 'Ollama 接口', description: '', kind: 'toggle', value: true },
				{
					key: 'directConnections',
					label: '直接连接',
					description: '允许用户直接连接到自己的 OpenAI 兼容 API 端点。',
					kind: 'toggle',
					value: false
				},
				{
					key: 'cacheBaseModels',
					label: '缓存基础模型列表',
					description:
						'仅在启动或保存设置时获取基础模型列表以提升访问速度，但显示的模型列表可能不是最新的。',
					kind: 'toggle',
					value: false
				}
			]
		},
		{
			id: 'models',
			title: '模型',
			keywords: ['模型 拉取 删除 创建 编辑 modelfile gguf 导入 导出'],
			items: [
				{
					key: 'modelGallery',
					label: '模型库',
					description: '允许用户浏览并添加可用模型。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'defaultModel',
					label: '默认模型',
					description: '新对话默认选择的模型。',
					kind: 'select',
					options: ['TAgent Chat', 'Qwen 2.5', 'DeepSeek V3'],
					value: 'TAgent Chat'
				},
				{
					key: 'modelName',
					label: '自定义模型名称',
					description: '管理界面中显示的模型名称。',
					kind: 'text',
					value: ''
				}
			]
		},
		{
			id: 'agent-models',
			title: '智能体模型',
			keywords: ['agent openai provider model routing api key base url'],
			items: [
				{
					key: 'agentProvider',
					label: '默认服务提供商',
					description: '智能体任务使用的默认模型渠道。',
					kind: 'select',
					options: ['TAgent', 'OpenAI 兼容接口', '本地模型'],
					value: 'TAgent'
				},
				{
					key: 'agentModel',
					label: '智能体模型',
					description: '用于工具规划和任务处理的模型。',
					kind: 'text',
					value: 'TAgent Chat'
				},
				{
					key: 'agentKey',
					label: '服务密钥',
					description: '智能体模型服务的 API 密钥（mock）。',
					kind: 'text',
					value: ''
				}
			]
		},
		{
			id: 'evaluations',
			title: '评估',
			keywords: ['evaluations feedback rating arena leaderboard preference'],
			items: [
				{
					key: 'feedback',
					label: '启用用户反馈',
					description: '允许用户对模型回复进行评价。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'arena',
					label: '启用模型对战',
					description: '允许用户匿名比较两个模型的回复。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'leaderboard',
					label: '公开排行榜',
					description: '在评估页面展示模型排名。',
					kind: 'toggle',
					value: false
				}
			]
		},
		{
			id: 'integrations',
			title: '集成',
			keywords: ['tools integrations plugins extensions functions openapi server terminal'],
			items: [
				{
					key: 'tools',
					label: '启用工具调用',
					description: '允许模型请求已配置的工具。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'openapi',
					label: 'OpenAPI 工具服务器',
					description: '可发现的 OpenAPI 服务地址。',
					kind: 'text',
					value: ''
				},
				{
					key: 'plugins',
					label: '允许函数扩展',
					description: '启用自定义函数和过滤器。',
					kind: 'toggle',
					value: true
				}
			]
		},
		{
			id: 'documents',
			title: '文档',
			keywords: [
				'documents files rag knowledge upload embedding vector db chunk overlap splitter pdf ocr'
			],
			items: [
				{
					key: 'fileUpload',
					label: '允许文件上传',
					description: '允许在对话中添加文档。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'maxFileSize',
					label: '最大文件大小（MB）',
					description: '单个文件允许上传的最大体积。',
					kind: 'number',
					value: 50
				},
				{
					key: 'chunkSize',
					label: '文本分块大小',
					description: '检索文档拆分时每段的字符数。',
					kind: 'number',
					value: 1000
				},
				{
					key: 'chunkOverlap',
					label: '文本分块重叠',
					description: '相邻文档块之间保留的字符数。',
					kind: 'number',
					value: 100
				}
			]
		},
		{
			id: 'web',
			title: '网页搜索',
			keywords: ['web search google bing duckduckgo serp searxng tavily exa firecrawl'],
			items: [
				{
					key: 'webSearch',
					label: '启用网页搜索',
					description: '允许模型检索外部网页信息。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'searchProvider',
					label: '搜索服务',
					description: '用于检索网页的服务提供商。',
					kind: 'select',
					options: ['DuckDuckGo', 'Google', 'Bing', 'SearXNG', 'Tavily'],
					value: 'DuckDuckGo'
				},
				{
					key: 'searchKey',
					label: '搜索服务 API Key',
					description: '选定搜索服务的访问密钥（mock）。',
					kind: 'text',
					value: ''
				},
				{
					key: 'searchTopK',
					label: '结果数量',
					description: '每次搜索返回的网页条数。',
					kind: 'number',
					value: 5
				}
			]
		},
		{
			id: 'code-execution',
			title: '代码执行',
			keywords: ['code execution python sandbox compiler jupyter interpreter'],
			items: [
				{
					key: 'codeExecution',
					label: '启用代码执行',
					description: '允许模型在隔离环境中运行代码。',
					kind: 'toggle',
					value: false
				},
				{
					key: 'codeRuntime',
					label: '执行环境',
					description: '代码运行器服务地址。',
					kind: 'text',
					value: 'http://localhost:8080'
				},
				{
					key: 'executionTimeout',
					label: '执行超时（秒）',
					description: '单次代码执行最长时间。',
					kind: 'number',
					value: 30
				}
			]
		},
		{
			id: 'interface',
			title: '界面',
			keywords: ['interface ui appearance banners tasks prompt suggestions title generation tags'],
			items: [
				{
					key: 'titleGeneration',
					label: '自动生成标题',
					description: '根据首轮对话内容生成会话标题。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'promptSuggestions',
					label: '显示提示建议',
					description: '在新对话页面展示示例问题。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'welcomeTitle',
					label: '欢迎标题',
					description: '新对话首页展示的标题文字。',
					kind: 'text',
					value: '今天有什么可以帮你？'
				},
				{
					key: 'welcomeMessage',
					label: '欢迎语',
					description: '新对话首页展示的说明内容。',
					kind: 'textarea',
					value: ''
				}
			]
		},
		{
			id: 'audio',
			title: '音频',
			keywords: ['audio voice speech tts stt whisper deepgram azure elevenlabs'],
			items: [
				{
					key: 'speechToText',
					label: '语音转文字',
					description: '允许用户通过语音输入消息。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'textToSpeech',
					label: '文字转语音',
					description: '支持将回复转换为语音播放。',
					kind: 'toggle',
					value: false
				},
				{
					key: 'audioProvider',
					label: '音频服务提供商',
					description: '语音识别和合成服务。',
					kind: 'select',
					options: ['内置服务', 'OpenAI', 'Azure', 'ElevenLabs'],
					value: '内置服务'
				},
				{
					key: 'audioKey',
					label: '音频服务 API Key',
					description: '音频服务访问密钥（mock）。',
					kind: 'text',
					value: ''
				}
			]
		},
		{
			id: 'images',
			title: '图像',
			keywords: ['images generation dalle stable diffusion comfyui gemini'],
			items: [
				{
					key: 'imageGeneration',
					label: '启用图像生成',
					description: '允许用户通过提示词生成图片。',
					kind: 'toggle',
					value: true
				},
				{
					key: 'imageProvider',
					label: '图像生成服务',
					description: '提供图像生成的模型服务。',
					kind: 'select',
					options: ['DALL·E', 'Stable Diffusion', 'ComfyUI', 'Gemini'],
					value: 'DALL·E'
				},
				{
					key: 'imageUrl',
					label: '服务地址',
					description: '图像生成 API 端点。',
					kind: 'text',
					value: ''
				},
				{
					key: 'imageKey',
					label: '服务 API Key',
					description: '图像服务访问密钥（mock）。',
					kind: 'text',
					value: ''
				}
			]
		},
		{
			id: 'pipelines',
			title: '管道',
			keywords: ['pipelines workflows filters valves middleware'],
			items: [
				{
					key: 'pipelineUrl',
					label: '管道服务地址',
					description: '连接自定义管道服务的 URL。',
					kind: 'text',
					value: ''
				},
				{
					key: 'pipelineKey',
					label: '管道 API Key',
					description: '管道服务的访问密钥（mock）。',
					kind: 'text',
					value: ''
				},
				{
					key: 'pipelineEnabled',
					label: '启用管道集成',
					description: '允许加载管道提供的模型和过滤器。',
					kind: 'toggle',
					value: false
				}
			]
		},
		{
			id: 'db',
			title: '数据库',
			keywords: ['database export import backup chats users'],
			items: [
				{
					key: 'databaseInfo',
					label: '数据库信息',
					description: '当前 mock 环境使用浏览器本地存储。',
					kind: 'text',
					value: 'Local Storage'
				},
				{
					key: 'backupFrequency',
					label: '备份频率',
					description: '自动备份配置的间隔。',
					kind: 'select',
					options: ['手动', '每天', '每周'],
					value: '手动'
				}
			]
		}
	];

	const definitions: SettingTab[] = rawDefinitions.map((tab) => ({
		...tab,
		keywords: tab.keywords[0].split(' ')
	}));

	const getStoredValue = (id: string, item: SettingItem) => {
		if (typeof localStorage === 'undefined') return item.value;
		try {
			const stored = localStorage.getItem('admin-mock-settings');
			if (stored) {
				const values = JSON.parse(stored) as Record<string, Record<string, SettingItem['value']>>;
				return values[id]?.[item.key] ?? item.value;
			}
		} catch {
			/* Ignore malformed local mock settings. */
		}
		return item.value;
	};

	const settings = $state<SettingTab[]>(
		definitions.map((tab) => ({
			...tab,
			items: tab.items.map((item) => ({ ...item, value: getStoredValue(tab.id, item) }))
		}))
	);
	type MockBanner = {
		id: string;
		type: 'info' | 'warning' | 'error';
		title: string;
		content: string;
		dismissible: boolean;
	};
	type MockConnection = {
		id: string;
		url: string;
		key: string;
		enabled: boolean;
		editing?: boolean;
		config?: Record<string, unknown>;
	};
	const defaultMockConnections = (provider: 'openai' | 'ollama'): MockConnection[] =>
		provider === 'openai'
			? [{ id: 'openai-default', url: 'https://api.openai.com/v1', key: '', enabled: true }]
			: [{ id: 'ollama-default', url: 'http://localhost:11434', key: '', enabled: true }];
	const loadMockConnections = (provider: 'openai' | 'ollama'): MockConnection[] => {
		const defaults = defaultMockConnections(provider);
		if (typeof localStorage === 'undefined') return defaults;
		try {
			const stored = localStorage.getItem(`admin-mock-${provider}-connections`);
			return stored ? (JSON.parse(stored) as MockConnection[]) : defaults;
		} catch {
			return defaults;
		}
	};
	const loadBanners = (): MockBanner[] => {
		if (typeof localStorage === 'undefined') return [];
		try {
			const stored = localStorage.getItem('admin-mock-banners');
			return stored ? (JSON.parse(stored) as MockBanner[]) : [];
		} catch {
			return [];
		}
	};
	let banners = $state<MockBanner[]>(loadBanners());
	let openAiConnections = $state<MockConnection[]>(loadMockConnections('openai'));
	let ollamaConnections = $state<MockConnection[]>(loadMockConnections('ollama'));
	let showAddOpenAiModal = $state(false);
	let showAddOllamaModal = $state(false);
	let showEditOpenAiModal = $state(false);
	let showEditOllamaModal = $state(false);
	let editingOpenAiConnection = $state<MockConnection | null>(null);
	let editingOllamaConnection = $state<MockConnection | null>(null);
	let search = $state('');
	let notice = $state('');
	const getSnapshot = () => ({
		values: settings.map((tab) => tab.items.map((item) => item.value)),
		banners,
		openAiConnections: openAiConnections.map(({ id, url, key, enabled, config }) => ({
			id,
			url,
			key,
			enabled,
			config
		})),
		ollamaConnections: ollamaConnections.map(({ id, url, key, enabled, config }) => ({
			id,
			url,
			key,
			enabled,
			config
		}))
	});
	let savedSnapshot = untrack(() => JSON.stringify(getSnapshot()));
	let selectedTab = $derived(
		settings.some((tab) => tab.id === $page.params.tab) ? $page.params.tab : 'general'
	);
	let visibleTabs = $derived(
		settings.filter(
			(tab) =>
				!search.trim() ||
				tab.title.toLowerCase().includes(search.trim().toLowerCase()) ||
				tab.keywords.some((word) => word.includes(search.trim().toLowerCase())) ||
				tab.items.some((item) =>
					`${item.label} ${item.description}`.toLowerCase().includes(search.trim().toLowerCase())
				)
		)
	);
	let currentTab = $derived(settings.find((tab) => tab.id === selectedTab) ?? settings[0]);
	const generalSections = $derived(
		[
			{ id: 'authentication', title: '身份验证' },
			{ id: 'features', title: '功能' },
			{ id: 'interface', title: '界面' }
		].map((section) => ({
			...section,
			items:
				settings
					.find((tab) => tab.id === 'general')
					?.items.filter((item) => item.section === section.id) ?? []
		}))
	);
	const isGeneralEnabled = (key: string) =>
		Boolean(
			settings.find((tab) => tab.id === 'general')?.items.find((item) => item.key === key)?.value
		);
	let dirty = $derived(JSON.stringify(getSnapshot()) !== savedSnapshot);

	function persistMockConnections() {
		localStorage.setItem('admin-mock-openai-connections', JSON.stringify(openAiConnections));
		localStorage.setItem('admin-mock-ollama-connections', JSON.stringify(ollamaConnections));
	}

	function saveSettings() {
		const data = Object.fromEntries(
			settings.map((tab) => [
				tab.id,
				Object.fromEntries(tab.items.map((item) => [item.key, item.value]))
			])
		);
		localStorage.setItem('admin-mock-settings', JSON.stringify(data));
		localStorage.setItem('admin-mock-banners', JSON.stringify(banners));
		localStorage.setItem(
			'admin-mock-openai-connections',
			JSON.stringify(getSnapshot().openAiConnections)
		);
		localStorage.setItem(
			'admin-mock-ollama-connections',
			JSON.stringify(getSnapshot().ollamaConnections)
		);
		savedSnapshot = JSON.stringify(getSnapshot());
		notice = '设置已保存（本地 mock）';
		setTimeout(() => (notice = ''), 2400);
	}

	function resetSettings() {
		for (const tab of settings) {
			const defaults = definitions.find((item) => item.id === tab.id);
			if (defaults) tab.items = defaults.items.map((item) => ({ ...item }));
		}
		banners = [];
		openAiConnections = defaultMockConnections('openai');
		ollamaConnections = defaultMockConnections('ollama');
	}
</script>

<AddConnectionModal
	bind:show={showAddOpenAiModal}
	onSubmit={(connection) => {
		openAiConnections = [
			...openAiConnections,
			{
				id: crypto.randomUUID(),
				url: connection.url,
				key: connection.key,
				enabled: connection.config?.enable ?? true,
				config: connection.config
			}
		];
		persistMockConnections();
		notice = 'OpenAI 连接已添加（本地 mock）';
		setTimeout(() => (notice = ''), 2400);
	}}
/>
<AddConnectionModal
	ollama
	bind:show={showAddOllamaModal}
	onSubmit={(connection) => {
		ollamaConnections = [
			...ollamaConnections,
			{
				id: crypto.randomUUID(),
				url: connection.url,
				key: connection.key,
				enabled: connection.config?.enable ?? true,
				config: connection.config
			}
		];
		persistMockConnections();
		notice = 'Ollama 连接已添加（本地 mock）';
		setTimeout(() => (notice = ''), 2400);
	}}
/>
<AddConnectionModal
	edit
	bind:show={showEditOpenAiModal}
	connection={editingOpenAiConnection
		? {
				url: editingOpenAiConnection.url,
				key: editingOpenAiConnection.key,
				config: editingOpenAiConnection.config ?? {}
			}
		: null}
	onSubmit={(connection) => {
		if (!editingOpenAiConnection) return;
		openAiConnections = openAiConnections.map((entry) =>
			entry.id === editingOpenAiConnection?.id
				? {
						...entry,
						url: connection.url,
						key: connection.key,
						enabled: connection.config?.enable ?? true,
						config: connection.config
					}
				: entry
		);
		persistMockConnections();
	}}
	onDelete={() => {
		if (!editingOpenAiConnection) return;
		openAiConnections = openAiConnections.filter(
			(entry) => entry.id !== editingOpenAiConnection?.id
		);
		persistMockConnections();
	}}
/>
<AddConnectionModal
	ollama
	edit
	bind:show={showEditOllamaModal}
	connection={editingOllamaConnection
		? {
				url: editingOllamaConnection.url,
				key: editingOllamaConnection.key,
				config: editingOllamaConnection.config ?? {}
			}
		: null}
	onSubmit={(connection) => {
		if (!editingOllamaConnection) return;
		ollamaConnections = ollamaConnections.map((entry) =>
			entry.id === editingOllamaConnection?.id
				? {
						...entry,
						url: connection.url,
						key: connection.key,
						enabled: connection.config?.enable ?? true,
						config: connection.config
					}
				: entry
		);
		persistMockConnections();
	}}
	onDelete={() => {
		if (!editingOllamaConnection) return;
		ollamaConnections = ollamaConnections.filter(
			(entry) => entry.id !== editingOllamaConnection?.id
		);
		persistMockConnections();
	}}
/>

<svelte:head><title>设置 | 管理员面板</title></svelte:head>

<div class="flex h-full min-h-0 w-full flex-col pb-2 lg:flex-row lg:gap-3">
	<nav
		class="mx-2 flex max-w-full scrollbar-none flex-row gap-2 overflow-x-auto text-sm font-medium lg:mx-0 lg:w-52 lg:flex-none lg:flex-col lg:gap-1 lg:overflow-y-auto lg:px-3"
		aria-label="管理员设置分类"
	>
		<label
			class="dark:bg-gray-850/80 hidden w-full items-center gap-2 rounded-full bg-gray-100/80 px-3 py-1.5 text-sm text-gray-500 backdrop-blur md:flex"
		>
			<svg viewBox="0 0 20 20" fill="currentColor" class="size-4 shrink-0"
				><path
					fill-rule="evenodd"
					d="M9 3.5a5.5 5.5 0 1 0 3.445 9.788l3.328 3.328a.75.75 0 1 0 1.06-1.06l-3.328-3.329A5.5 5.5 0 0 0 9 3.5ZM5 9a4 4 0 1 1 8 0 4 4 0 0 1-8 0Z"
					clip-rule="evenodd"
				/></svg
			>
			<input
				class="w-full min-w-0 bg-transparent py-1 text-sm outline-none dark:text-gray-300"
				bind:value={search}
				placeholder="搜索设置"
				aria-label="搜索设置分类"
			/>
			{#if search}<button
					class="rounded-full px-1 hover:bg-gray-200 dark:hover:bg-gray-700"
					onclick={() => (search = '')}
					aria-label="清除搜索">×</button
				>{/if}
		</label>
		{#each visibleTabs as tab (tab.id)}
			<a
				href={resolve(`/admin/settings/${tab.id}`)}
				aria-current={selectedTab === tab.id ? 'page' : undefined}
				class="flex min-w-fit flex-1 items-center gap-2 rounded-lg px-2 py-2 transition select-none lg:flex-none {selectedTab ===
				tab.id
					? 'text-gray-900 dark:text-white'
					: 'text-gray-500 hover:text-gray-800 dark:text-gray-500 dark:hover:text-white'}"
			>
				<span
					class="flex size-5 shrink-0 items-center justify-center text-current"
					aria-hidden="true"
				>
					<svg viewBox="0 0 24 24" class="size-5" fill="currentColor">
						{#if tab.id === 'general'}
							<path
								d="M19.14 12.94a7.5 7.5 0 0 0 .05-1.88l2.03-1.58-2-3.46-2.42.98a7.6 7.6 0 0 0-1.63-.94L14.8 3h-4l-.37 3.06a7.6 7.6 0 0 0-1.63.94l-2.42-.98-2 3.46 2.03 1.58a7.5 7.5 0 0 0 0 1.88l-2.03 1.58 2 3.46 2.42-.98c.5.4 1.05.72 1.63.94L10.8 21h4l.37-3.06c.58-.22 1.13-.54 1.63-.94l2.42.98 2-3.46-2.08-1.58ZM12.8 15a3 3 0 1 1 0-6 3 3 0 0 1 0 6Z"
							/>
						{:else if tab.id === 'connections'}
							<path
								d="M19.35 10.04A7.49 7.49 0 0 0 5.2 8.25 5.5 5.5 0 0 0 5.5 19h13a4.5 4.5 0 0 0 .85-8.96Z"
							/>
						{:else if tab.id === 'models' || tab.id === 'db'}
							<path
								d="M12 2C6.48 2 2 4.02 2 6.5S6.48 11 12 11s10-2.02 10-4.5S17.52 2 12 2Zm-10 8v4.5C2 16.98 6.48 19 12 19c2.88 0 5.47-.55 7.3-1.43A4.49 4.49 0 0 1 17 13.5c0-.24.02-.48.06-.71-1.5.46-3.24.71-5.06.71-4.42 0-8.18-1.35-10-3.5Zm0 7.5V18c0 2.48 4.48 4.5 10 4.5 1.04 0 2.03-.07 2.96-.2A4.5 4.5 0 0 1 14 19.5v-.2c-.65.12-1.32.2-2 .2-4.42 0-8.18-1.35-10-3.5Z"
							/>
						{:else if tab.id === 'agent-models'}
							<path
								d="m12 2 10 5.5v9L12 22 2 16.5v-9L12 2Zm0 2.3L5.4 8 12 11.7 18.6 8 12 4.3Zm-8 5.4v5.6l7 3.85v-5.7l-7-3.75Zm9 9.45 7-3.85V9.7l-7 3.75v5.7Z"
							/>
						{:else if tab.id === 'evaluations'}
							<path
								d="M6 2h8l6 6v13a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5ZM7 17h2v3H7v-3Zm4-4h2v7h-2v-7Zm4-3h2v10h-2V10Z"
							/>
						{:else if tab.id === 'integrations'}
							<path
								d="M22 19.59 13.42 11a6 6 0 0 0-7.77-7.77l3.53 3.53-2.83 2.83-3.53-3.53A6 6 0 0 0 10.59 13l8.59 8.59A2 2 0 0 0 22 19.59ZM5.2 18.8a2 2 0 1 1-2.83-2.83l6.36-6.36 2.83 2.83L5.2 18.8Z"
							/>
						{:else if tab.id === 'documents'}
							<path
								d="M6 2h8l6 6v13a1 1 0 0 1-1 1H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Zm7 1.5V9h5.5L13 3.5ZM8 12h8v1.5H8V12Zm0 3h8v1.5H8V15Zm0 3h5v1.5H8V18Z"
							/>
						{:else if tab.id === 'web'}
							<path
								d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20Zm6.9 6h-3.02a15.7 15.7 0 0 0-1.5-3.87A8.04 8.04 0 0 1 18.9 8ZM12 4c.84 1.12 1.5 2.48 1.92 4h-3.84c.42-1.52 1.08-2.88 1.92-4ZM4.26 14a8.06 8.06 0 0 1 0-4h3.37a16.2 16.2 0 0 0 0 4H4.26Zm.84 2h3.02c.35 1.42.86 2.73 1.5 3.87A8.04 8.04 0 0 1 5.1 16Zm3.02-8H5.1a8.04 8.04 0 0 1 4.52-3.87A15.7 15.7 0 0 0 8.12 8ZM12 20c-.84-1.12-1.5-2.48-1.92-4h3.84c-.42 1.52-1.08 2.88-1.92 4Zm2.34-6H9.66a13.8 13.8 0 0 1 0-4h4.68a13.8 13.8 0 0 1 0 4Zm.04 5.87c.64-1.14 1.15-2.45 1.5-3.87h3.02a8.04 8.04 0 0 1-4.52 3.87ZM16.37 14a16.2 16.2 0 0 0 0-4h3.37a8.06 8.06 0 0 1 0 4h-3.37Z"
							/>
						{:else if tab.id === 'code-execution'}
							<path
								d="M4 3h16a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm3.2 5.3a1 1 0 0 0-1.4 1.4L8.1 12l-2.3 2.3a1 1 0 1 0 1.4 1.4l3-3a1 1 0 0 0 0-1.4l-3-3ZM12 15a1 1 0 0 0 0 2h4a1 1 0 0 0 0-2h-4Z"
							/>
						{:else if tab.id === 'interface'}
							<path
								d="M4 3h16a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2h-6v2h3v2H7v-2h3v-2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm0 2v11h16V5H4Z"
							/>
						{:else if tab.id === 'audio'}
							<path
								d="M3 9v6h4l5 4V5L7 9H3Zm12.5 3a3.5 3.5 0 0 0-2-3.16v6.32a3.5 3.5 0 0 0 2-3.16Zm-2-8.9v2.06a7 7 0 0 1 0 13.68v2.06a9 9 0 0 0 0-17.8Z"
							/>
						{:else if tab.id === 'images'}
							<path
								d="M21 5v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2ZM5 19h14l-4.5-6-3.5 4.5-2.5-3L5 19Zm3-9a2 2 0 1 0 0-4 2 2 0 0 0 0 4Z"
							/>
						{:else if tab.id === 'pipelines'}
							<path
								d="m12 2 10 5.5-10 5.5L2 7.5 12 2Zm-10 9 10 5.5 10-5.5v3L12 19.5 2 14v-3Zm0 5.5 10 5.5L22 16.5v3L12 25 2 19.5v-3Z"
								transform="translate(0 -1)"
							/>
						{:else}
							<path
								d="M12 2C6.48 2 2 4.02 2 6.5S6.48 11 12 11s10-2.02 10-4.5S17.52 2 12 2Zm-10 8v4.5C2 16.98 6.48 19 12 19s10-2.02 10-4.5V10c-1.82 2.15-5.58 3.5-10 3.5S3.82 12.15 2 10Zm0 7.5V18c0 2.48 4.48 4.5 10 4.5s10-2.02 10-4.5v-.5c-1.82 2.15-5.58 3.5-10 3.5S3.82 19.65 2 17.5Z"
							/>
						{/if}
					</svg>
				</span>
				<span>{tab.title}</span>
			</a>
		{:else}
			<p class="px-2 py-3 text-xs text-gray-500">没有匹配的设置分类</p>
		{/each}
	</nav>

	<main class="mt-2 min-w-0 flex-1 overflow-y-auto px-3 lg:mt-0 lg:px-4">
		{#if currentTab}
			<!-- 有自己组件的分类不套外层表单：它们里面有自己的表单，提交事件会冒泡上来，
			     连带触发外层的「保存设置」（那只是存本地的界面示例） -->
			{#if selectedTab === 'models'}
				<AdminModels />
			{:else if selectedTab === 'agent-models'}
				<AdminAgentModels />
			{:else if selectedTab === 'evaluations'}
				<AdminEvaluationSettings />
			{:else if selectedTab === 'integrations'}
				<AdminIntegrations />
			{:else if selectedTab === 'documents'}
				<AdminDocumentsSettings />
			{:else if selectedTab === 'db'}
				<AdminDatabase />
			{:else}
				<form
					class="flex min-h-full flex-col"
					onsubmit={(event) => {
						event.preventDefault();
						saveSettings();
					}}
				>
					<header
						class="sticky top-0 z-10 flex items-center justify-between bg-white/95 py-2 backdrop-blur dark:bg-gray-900/95"
					>
						<div>
							<h1 class="text-lg font-medium">{currentTab.title}</h1>
							{#if selectedTab !== 'general'}<p class="mt-0.5 text-xs text-gray-500">
									管理平台的{currentTab.title}相关配置
								</p>{/if}
						</div>
						{#if dirty}<span
								class="rounded-full bg-amber-100 px-2.5 py-1 text-[10px] font-medium text-amber-800 dark:bg-amber-950/50 dark:text-amber-200"
								>未保存</span
							>{/if}
					</header>
					<div class="flex-1 space-y-1 pb-5">
						{#if selectedTab === 'general'}
							<section class="mb-5">
								<div class="mb-3.5">
									<div class="mb-2 text-base font-medium">版本</div>
									<hr class="dark:border-gray-850/30 my-2 border-gray-100/30" />
									<div class="mb-2.5">
										<div class="mb-1 text-xs font-medium">版本</div>
										<div class="flex w-full items-center justify-between gap-3">
											<div class="flex flex-col text-xs text-gray-700 dark:text-gray-200">
												<div>v0.8.12 <span class="text-gray-500">(v0.12.3 版本可用！)</span></div>
												<button
													type="button"
													class="w-fit text-left text-xs text-gray-500 underline"
													onclick={() => {
														notice = '已查看最新更新内容（mock）';
														setTimeout(() => (notice = ''), 2400);
													}}>查看最新更新内容</button
												>
											</div>
											<button
												type="button"
												class="dark:bg-gray-850 shrink-0 rounded-lg bg-gray-50 px-3 py-1.5 text-xs font-medium transition hover:bg-gray-100 dark:hover:bg-gray-800"
												onclick={() => {
													notice = '已检查更新：当前为 mock 最新版本';
													setTimeout(() => (notice = ''), 2400);
												}}>检查更新</button
											>
										</div>
									</div>
									<div class="mb-2.5">
										<div class="flex w-full items-center justify-between gap-3">
											<div class="pr-2 text-xs">
												<div>帮助</div>
												<div class="text-xs text-gray-500">
													了解如何使用 Open WebUI 并寻求社区支持
												</div>
											</div>
											<a
												class="shrink-0 text-xs font-medium underline"
												href="https://docs.openwebui.com/"
												target="_blank"
												rel="noreferrer">帮助文档</a
											>
										</div>
										<div class="mt-1 flex flex-wrap items-center gap-1 text-[10px]">
											<a
												class="rounded bg-[#5865f2] px-1.5 py-0.5 font-medium text-white"
												href="https://discord.gg/5rJgQTnV4s"
												target="_blank"
												rel="noreferrer">Discord</a
											>
											<a
												class="rounded bg-sky-700 px-1.5 py-0.5 font-medium text-white"
												href="https://docs.openwebui.com/"
												target="_blank"
												rel="noreferrer">Open WebUI</a
											>
											<a
												class="rounded border border-gray-300 px-1.5 py-0.5 text-gray-700 dark:border-gray-700 dark:text-gray-200"
												href="https://twitter.com/OpenWebUI"
												target="_blank"
												rel="noreferrer">𝕏 Follow @OpenWebUI</a
											>
											<a
												class="rounded border border-gray-300 px-1.5 py-0.5 text-gray-700 dark:border-gray-700 dark:text-gray-200"
												href="https://github.com/open-webui/open-webui"
												target="_blank"
												rel="noreferrer">★ Star us on Github</a
											>
											<span
												class="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
												>156k</span
											>
										</div>
									</div>
									<div class="mb-2.5">
										<div class="flex w-full items-center justify-between gap-3">
											<div class="pr-2 text-xs">
												<div>授权</div>
												<div class="text-xs text-gray-500">
													升级到授权套餐以获得增强功能，包括自定义主题、品牌推广以及专属支持
												</div>
											</div>
											<a
												class="shrink-0 text-xs font-medium underline"
												href="https://docs.openwebui.com/enterprise"
												target="_blank"
												rel="noreferrer">了解更多</a
											>
										</div>
									</div>
								</div>
							</section>

							{#each generalSections as section (section.id)}
								<section class="mb-5">
									<h2 class="mt-1 mb-2.5 text-base font-medium">{section.title}</h2>
									<hr class="my-2 border-gray-100 dark:border-gray-800" />
									{#each section.items as item (item.key)}
										{#if (item.key !== 'adminEmail' || isGeneralEnabled('showAdminDetails')) && (item.key !== 'apiRestrictions' || isGeneralEnabled('enableApiKeys')) && (item.key !== 'allowedEndpoints' || (isGeneralEnabled('enableApiKeys') && isGeneralEnabled('apiRestrictions'))) && (item.key !== 'ldapHost' || isGeneralEnabled('enableLdap')) && (item.key !== 'folderMaxFiles' || isGeneralEnabled('folders'))}
											<div
												class="dark:border-gray-850/20 mb-0 flex w-full flex-col gap-1 border-b border-gray-100/50 py-1 last:border-0 {item.kind ===
													'toggle' || item.kind === 'select'
													? 'sm:flex-row sm:items-center sm:justify-between'
													: ''}"
											>
												<div
													class="min-w-0 text-xs {item.kind === 'toggle' || item.kind === 'select'
														? 'sm:max-w-[55%]'
														: 'w-full'}"
												>
													<label
														class="font-medium {item.key === 'responseWatermark'
															? 'whitespace-nowrap'
															: ''}"
														for={`setting-${item.key}`}>{item.label}</label
													>
													{#if item.description}<p class="mt-0.5 text-gray-500">
															{item.description}
														</p>{/if}
												</div>
												<div
													class="w-full {item.kind === 'toggle' || item.kind === 'select'
														? 'sm:flex sm:max-w-[45%] sm:justify-end'
														: 'sm:max-w-full'}"
												>
													{#if item.kind === 'toggle'}
														<button
															type="button"
															role="switch"
															aria-checked={Boolean(item.value)}
															aria-label={item.label}
															class="relative h-[1.125rem] w-8 shrink-0 rounded-full px-1 outline outline-1 outline-gray-700 transition {item.value
																? 'bg-emerald-700'
																: 'bg-transparent'}"
															onclick={() => (item.value = !item.value)}
															><span
																class="block size-3 rounded-full bg-white transition-transform {item.value
																	? 'translate-x-3'
																	: ''}"
															></span></button
														>
													{:else if item.kind === 'select'}
														<select
															id={`setting-${item.key}`}
															class="w-fit min-w-16 rounded-sm bg-transparent px-1 py-0.5 text-right text-[10px] outline-none"
															bind:value={item.value as string}
															>{#each item.options ?? [] as option (option)}<option value={option}
																	>{option}</option
																>{/each}</select
														>
													{:else if item.kind === 'textarea'}
														<textarea
															id={`setting-${item.key}`}
															class="dark:bg-gray-850 min-h-16 w-full resize-y rounded-lg bg-gray-800/80 px-3 py-2 text-center text-xs outline-none placeholder:text-[11px] focus:ring-1 focus:ring-blue-500"
															bind:value={item.value as string}
															placeholder=""></textarea>
													{:else}
														<input
															id={`setting-${item.key}`}
															type={item.kind === 'number'
																? 'number'
																: item.key === 'adminEmail'
																	? 'email'
																	: 'text'}
															class="dark:bg-gray-850 w-full rounded-lg bg-gray-800/80 px-3 py-2 text-center text-xs outline-none placeholder:text-[11px] placeholder:text-gray-500 focus:ring-1 focus:ring-blue-500"
															bind:value={item.value}
															placeholder=""
														/>
														{#if item.key === 'jwtExpiration'}<p class="mt-1 text-xs text-gray-500">
																有效时间单位：'s'（秒）、'm'（分）、'h'（时）、'd'（天）、'w'（周）或
																'-1' 表示无过期时间。
															</p>{/if}
													{/if}
												</div>
											</div>
											{#if item.key === 'jwtExpiration' && item.value === '-1'}
												<div
													class="mb-3 rounded-lg bg-yellow-500/15 px-3 py-2 text-xs text-yellow-800 dark:text-yellow-200"
												>
													注意：JWT 永不过期可能带来安全风险。
												</div>
											{/if}
										{/if}
									{/each}
									{#if section.id === 'interface'}
										<div class="mt-1">
											<div class="mb-1 flex items-center justify-between text-xs">
												<span>公告横幅</span>
												<button
													aria-label="添加公告横幅"
													class="dark:hover:bg-gray-850 rounded p-1 transition hover:bg-gray-100"
													type="button"
													onclick={() =>
														(banners = [
															...banners,
															{
																id: crypto.randomUUID(),
																type: 'info',
																title: '',
																content: '',
																dismissible: true
															}
														])}
												>
													<svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
														><path
															d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z"
														/></svg
													>
												</button>
											</div>
											{#each banners as banner (banner.id)}
												<div class="dark:bg-gray-850 mb-2 space-y-2 rounded-lg bg-gray-50 p-3">
													<div class="flex items-center gap-2">
														<select
															class="min-w-0 flex-1 rounded-lg bg-white px-3 py-2 text-xs outline-none dark:bg-gray-900"
															bind:value={banner.type}
															aria-label="公告类型"
															><option value="info">信息</option><option value="warning"
																>警告</option
															><option value="error">错误</option></select
														>
														<label class="flex shrink-0 items-center gap-1 text-xs"
															><input
																type="checkbox"
																bind:checked={banner.dismissible}
															/>允许关闭</label
														>
														<button
															type="button"
															class="rounded p-1 text-gray-500 hover:bg-gray-200 dark:hover:bg-gray-700"
															aria-label="删除公告"
															onclick={() =>
																(banners = banners.filter((item) => item.id !== banner.id))}
															>×</button
														>
													</div>
													<input
														class="w-full rounded-lg bg-white px-3 py-2 text-xs outline-none dark:bg-gray-900"
														bind:value={banner.title}
														placeholder="标题（可选）"
														aria-label="公告标题"
													/>
													<textarea
														class="min-h-16 w-full resize-y rounded-lg bg-white px-3 py-2 text-xs outline-none dark:bg-gray-900"
														bind:value={banner.content}
														placeholder="公告内容"
														aria-label="公告内容"></textarea>
													{#if banner.content}<div
															class="rounded-lg border border-gray-200 px-3 py-2 text-xs dark:border-gray-700"
														>
															<div class="font-medium">{banner.title || '公告预览'}</div>
															<div class="mt-1 text-gray-500">{banner.content}</div>
														</div>{/if}
												</div>
											{/each}
										</div>
									{/if}
								</section>
							{/each}
						{:else if selectedTab === 'connections'}
							<p
								class="mb-3 rounded-lg bg-gray-50 px-3 py-2 text-xs text-gray-600 dark:bg-gray-800/60 dark:text-gray-300"
							>
								这一页是界面示例，设置只存在这个浏览器里。学生实际能用的模型在
								<a class="underline" href={resolve('/admin/settings/agent-models')}>智能体模型</a> 里登记。
							</p>
							<section class="mb-4">
								<h2 class="mt-1 mb-2.5 text-base font-medium">通用</h2>
								<hr class="dark:border-gray-850/30 my-2 border-gray-100/30" />
								{#each currentTab.items.slice(0, 1) as item (item.key)}
									<div class="flex items-center justify-between py-2 text-sm">
										<span class="font-medium">{item.label}</span><button
											type="button"
											role="switch"
											aria-checked={Boolean(item.value)}
											aria-label={item.label}
											class="relative h-[1.125rem] w-8 rounded-full px-1 outline outline-1 outline-gray-700 transition {item.value
												? 'bg-emerald-700'
												: 'bg-transparent'}"
											onclick={() => (item.value = !item.value)}
											><span
												class="block size-3 rounded-full bg-white transition-transform {item.value
													? 'translate-x-3'
													: ''}"
											></span></button
										>
									</div>
								{/each}
								{#if Boolean(currentTab.items.find((item) => item.key === 'enableOpenAI')?.value)}
									<div class="mb-4">
										<div class="flex items-center justify-between py-1">
											<span class="text-xs font-medium">管理 OpenAI API 连接</span><button
												type="button"
												aria-label="添加 OpenAI API 连接"
												class="dark:hover:bg-gray-850 rounded p-1 hover:bg-gray-100"
												onclick={() => (showAddOpenAiModal = true)}
												><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
													><path
														d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z"
													/></svg
												></button
											>
										</div>
										<div class="space-y-2">
											{#each openAiConnections as connection (connection.id)}
												<div class="py-1">
													<div class="flex items-center gap-2">
														<input
															class="min-w-0 flex-1 bg-transparent text-sm outline-none"
															placeholder="API Base URL"
															bind:value={connection.url}
														/>
														<button
															type="button"
															aria-label="配置连接"
															class="dark:hover:bg-gray-850 rounded p-1 hover:bg-gray-100"
															onclick={() => {
																editingOpenAiConnection = connection;
																showEditOpenAiModal = true;
															}}
															><svg
																viewBox="0 0 24 24"
																fill="none"
																stroke="currentColor"
																stroke-width="1.8"
																class="size-4"
																><path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="M10.3 3.5h3.4l.5 2.2c.5.2.9.4 1.3.8l2.2-.6 1.7 3-1.7 1.6v1.5l1.7 1.6-1.7 3-2.2-.6c-.4.3-.8.6-1.3.8l-.5 2.2h-3.4l-.5-2.2c-.5-.2-.9-.5-1.3-.8l-2.2.6-1.7-3 1.7-1.6v-1.5L4.6 8.9l1.7-3 2.2.6c.4-.4.8-.6 1.3-.8l.5-2.2Z"
																/><circle cx="12" cy="11.3" r="2.2" /></svg
															></button
														>
														<button
															type="button"
															role="switch"
															aria-checked={connection.enabled}
															aria-label="启用 OpenAI 连接"
															class="relative h-[1.125rem] w-8 rounded-full px-1 outline outline-1 outline-gray-700 {connection.enabled
																? 'bg-emerald-700'
																: 'bg-transparent'}"
															onclick={() => (connection.enabled = !connection.enabled)}
															><span
																class="block size-3 rounded-full bg-white transition-transform {connection.enabled
																	? 'translate-x-3'
																	: ''}"
															></span></button
														>
													</div>
												</div>
											{/each}
										</div>
									</div>
								{/if}
								{#each currentTab.items.slice(1, 2) as item (item.key)}
									<div class="flex items-center justify-between py-2 text-sm">
										<span class="font-medium">{item.label}</span><button
											type="button"
											role="switch"
											aria-checked={Boolean(item.value)}
											aria-label={item.label}
											class="relative h-[1.125rem] w-8 rounded-full px-1 outline outline-1 outline-gray-700 transition {item.value
												? 'bg-emerald-700'
												: 'bg-transparent'}"
											onclick={() => (item.value = !item.value)}
											><span
												class="block size-3 rounded-full bg-white transition-transform {item.value
													? 'translate-x-3'
													: ''}"
											></span></button
										>
									</div>
								{/each}
								{#if Boolean(currentTab.items.find((item) => item.key === 'enableOllama')?.value)}
									<div class="mb-4">
										<div class="flex items-center justify-between py-1">
											<span class="text-xs font-medium">管理 Ollama API 连接</span><button
												type="button"
												aria-label="添加 Ollama API 连接"
												class="dark:hover:bg-gray-850 rounded p-1 hover:bg-gray-100"
												onclick={() => (showAddOllamaModal = true)}
												><svg viewBox="0 0 20 20" fill="currentColor" class="size-4"
													><path
														d="M10.75 4.75a.75.75 0 0 0-1.5 0v4.5h-4.5a.75.75 0 0 0 0 1.5h4.5v4.5a.75.75 0 0 0 1.5 0v-4.5h4.5a.75.75 0 0 0 0-1.5h-4.5v-4.5Z"
													/></svg
												></button
											>
										</div>
										<div class="space-y-2">
											{#each ollamaConnections as connection (connection.id)}
												<div
													class="rounded-lg border border-gray-200 px-3 py-2 dark:border-gray-800"
												>
													<div class="flex items-center gap-2">
														<input
															class="min-w-0 flex-1 bg-transparent text-sm outline-none"
															placeholder="http://localhost:11434"
															bind:value={connection.url}
														/>
														<button
															type="button"
															aria-label="管理 Ollama 模型"
															class="dark:hover:bg-gray-850 rounded p-1 text-gray-500 hover:bg-gray-100"
															onclick={() => {
																notice = '模型管理（mock）';
																setTimeout(() => (notice = ''), 2400);
															}}
															><svg
																viewBox="0 0 24 24"
																fill="none"
																stroke="currentColor"
																stroke-width="1.8"
																class="size-4"
																><path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="M12 3v12m0 0 4-4m-4 4-4-4M5 17v3h14v-3"
																/></svg
															></button
														>
														<button
															type="button"
															aria-label="配置连接"
															class="dark:hover:bg-gray-850 rounded p-1 hover:bg-gray-100"
															onclick={() => {
																editingOllamaConnection = connection;
																showEditOllamaModal = true;
															}}
															><svg
																viewBox="0 0 24 24"
																fill="none"
																stroke="currentColor"
																stroke-width="1.8"
																class="size-4"
																><path
																	stroke-linecap="round"
																	stroke-linejoin="round"
																	d="M10.3 3.5h3.4l.5 2.2c.5.2.9.4 1.3.8l2.2-.6 1.7 3-1.7 1.6v1.5l1.7 1.6-1.7 3-2.2-.6c-.4.3-.8.6-1.3.8l-.5 2.2h-3.4l-.5-2.2c-.5-.2-.9-.5-1.3-.8l-2.2.6-1.7-3 1.7-1.6v-1.5L4.6 8.9l1.7-3 2.2.6c.4-.4.8-.6 1.3-.8l.5-2.2Z"
																/><circle cx="12" cy="11.3" r="2.2" /></svg
															></button
														>
														<button
															type="button"
															role="switch"
															aria-checked={connection.enabled}
															aria-label="启用 Ollama 连接"
															class="relative h-[1.125rem] w-8 rounded-full px-1 outline outline-1 outline-gray-700 {connection.enabled
																? 'bg-emerald-700'
																: 'bg-transparent'}"
															onclick={() => (connection.enabled = !connection.enabled)}
															><span
																class="block size-3 rounded-full bg-white transition-transform {connection.enabled
																	? 'translate-x-3'
																	: ''}"
															></span></button
														>
													</div>
												</div>
											{/each}
										</div>
										<p class="mt-2 text-xs text-gray-500">
											无法连接到 Ollama？<a
												class="underline"
												href="https://github.com/open-webui/open-webui#troubleshooting"
												target="_blank"
												rel="noreferrer">查看帮助</a
											>
										</p>
									</div>
								{/if}
								<hr class="dark:border-gray-850/30 my-3 border-gray-100/30" />
								{#each currentTab.items.slice(2) as item (item.key)}
									<div class="py-2">
										<div class="flex items-center justify-between text-sm">
											<span
												class={item.key === 'cacheBaseModels'
													? 'text-xs font-medium'
													: 'font-medium'}>{item.label}</span
											><button
												type="button"
												role="switch"
												aria-checked={Boolean(item.value)}
												aria-label={item.label}
												class="relative h-[1.125rem] w-8 rounded-full px-1 outline outline-1 outline-gray-700 transition {item.value
													? 'bg-emerald-700'
													: 'bg-transparent'}"
												onclick={() => (item.value = !item.value)}
												><span
													class="block size-3 rounded-full bg-white transition-transform {item.value
														? 'translate-x-3'
														: ''}"
												></span></button
											>
										</div>
										{#if item.description}<p class="mt-1 text-xs text-gray-500">
												{item.description}
											</p>{/if}
									</div>
								{/each}
							</section>
						{:else}
							{#each currentTab.items as item (item.key)}
								<div
									class="dark:border-gray-850/40 flex flex-col gap-3 border-b border-gray-100 py-3.5 sm:flex-row sm:items-center sm:justify-between"
								>
									<div class="min-w-0 flex-1">
										<label class="text-xs font-medium" for={`setting-${item.key}`}
											>{item.label}</label
										>
										<p class="mt-0.5 text-xs text-gray-500">{item.description}</p>
									</div>
									<div class="w-full sm:max-w-sm sm:flex-1 sm:pl-5">
										{#if item.kind === 'toggle'}
											<button
												type="button"
												role="switch"
												aria-checked={Boolean(item.value)}
												aria-label={item.label}
												class="relative h-5 w-9 rounded-full transition {item.value
													? 'bg-emerald-600'
													: 'bg-gray-300 dark:bg-gray-700'}"
												onclick={() => (item.value = !item.value)}
												><span
													class="absolute top-0.5 size-4 rounded-full bg-white shadow transition-all {item.value
														? 'left-[18px]'
														: 'left-0.5'}"
												></span></button
											>
										{:else if item.kind === 'select'}
											<select
												id={`setting-${item.key}`}
												class="w-full rounded-lg border border-gray-200 bg-white px-3 py-2 text-xs outline-none focus:border-blue-500 dark:border-gray-700 dark:bg-gray-900"
												bind:value={item.value as string}
												>{#each item.options ?? [] as option (option)}<option value={option}
														>{option}</option
													>{/each}</select
											>
										{:else if item.kind === 'textarea'}
											<textarea
												id={`setting-${item.key}`}
												class="min-h-20 w-full resize-y rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-xs outline-none focus:border-blue-500 dark:border-gray-700"
												bind:value={item.value as string}></textarea>
										{:else}
											<input
												id={`setting-${item.key}`}
												type={item.kind === 'number' ? 'number' : 'text'}
												class="w-full rounded-lg border border-gray-200 bg-transparent px-3 py-2 text-xs outline-none focus:border-blue-500 dark:border-gray-700"
												bind:value={item.value}
											/>
										{/if}
									</div>
								</div>
							{/each}
						{/if}
					</div>
					<footer
						class="sticky bottom-0 flex items-center justify-between border-t border-gray-100 bg-white/95 py-3 backdrop-blur dark:border-gray-800 dark:bg-gray-900/95"
					>
						<button
							type="button"
							class="dark:hover:bg-gray-850 rounded-lg px-3 py-2 text-xs text-gray-500 hover:bg-gray-100"
							onclick={resetSettings}>恢复默认值</button
						>
						<button
							type="submit"
							disabled={!dirty}
							class="rounded-lg bg-gray-900 px-4 py-2 text-xs font-medium text-white transition hover:bg-gray-700 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-white dark:text-gray-900 dark:hover:bg-gray-200"
							>保存设置</button
						>
					</footer>
				</form>
			{/if}
		{/if}
	</main>
</div>

{#if notice}<div
		class="fixed right-5 bottom-5 z-[70] rounded-xl bg-gray-900 px-4 py-2.5 text-sm text-white shadow-lg dark:bg-white dark:text-gray-900"
		role="status"
	>
		{notice}
	</div>{/if}
