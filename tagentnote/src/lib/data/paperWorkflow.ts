export type PaperSection =
	'选题与大纲' | '摘要' | '相关工作' | '研究方法' | '实验设计' | '结果与讨论' | '完整性检查';

export type PaperTextField =
	| 'researchObject'
	| 'researchQuestion'
	| 'outlineFocus'
	| 'researchBackground'
	| 'methodSummary'
	| 'resultSummary'
	| 'relatedWorkFocus'
	| 'relatedMaterials'
	| 'systemBoundary'
	| 'entitiesEventsResources'
	| 'modelAssumptions'
	| 'dataSource'
	| 'baselineScenario'
	| 'improvedScenario'
	| 'metrics'
	| 'dataStatus'
	| 'comparisonFindings'
	| 'limitations'
	| 'draftContent'
	| 'courseRequirements';

export type PaperNoteReference = {
	key: string;
	notebookId: string;
	notebookName: string;
	noteId: string;
	title: string;
};

export type PaperFileAttachment = {
	id: string;
	name: string;
	type: string;
	size: number;
	content?: string;
	status?: string;
};

export type PaperContext = Record<PaperTextField, string> & {
	attachedNotes?: Partial<Record<PaperTextField, PaperNoteReference[]>>;
	attachedFiles?: PaperFileAttachment[];
};

export type PaperContextField = {
	id: PaperTextField;
	label: string;
	placeholder: string;
};

export type PaperTask = {
	title: string;
	keywords: string;
	section: PaperSection;
	context?: PaperContext;
};

export type PaperIntent =
	'outline' | 'abstract' | 'related' | 'method' | 'experiment' | 'results' | 'checklist';

export const PAPER_SECTIONS: PaperSection[] = [
	'选题与大纲',
	'摘要',
	'相关工作',
	'研究方法',
	'实验设计',
	'结果与讨论',
	'完整性检查'
];

export const DEFAULT_PAPER_TASK: PaperTask = {
	title: '',
	keywords: '',
	// 默认落在**第一个**章节。原来写死 '实验设计'（第 5 个），
	// 和卡片上「先写题目，再分章节」的指引自相矛盾。
	section: '选题与大纲'
};

export const DEFAULT_PAPER_CONTEXT: PaperContext = {
	researchObject: '',
	researchQuestion: '',
	outlineFocus: '',
	researchBackground: '',
	methodSummary: '',
	resultSummary: '',
	relatedWorkFocus: '',
	relatedMaterials: '',
	systemBoundary: '',
	entitiesEventsResources: '',
	modelAssumptions: '',
	dataSource: '',
	baselineScenario: '',
	improvedScenario: '',
	metrics: '',
	dataStatus: '',
	comparisonFindings: '',
	limitations: '',
	draftContent: '',
	courseRequirements: '',
	attachedNotes: {},
	attachedFiles: []
};

export const PAPER_INTENTS: Array<{
	id: PaperIntent;
	title: string;
	description: string;
}> = [
	{ id: 'outline', title: '生成大纲', description: '搭建课程论文结构' },
	{ id: 'abstract', title: '起草摘要', description: '方法与结果留出位置' },
	{ id: 'related', title: '梳理相关工作', description: '整理概念与研究方向' },
	{ id: 'method', title: '写研究方法', description: '实体、事件、资源与假设' },
	{ id: 'experiment', title: '设计实验', description: '场景、指标与对照组' },
	{ id: 'results', title: '组织结果讨论', description: '比较结果并解释原因' },
	{ id: 'checklist', title: '完整性检查', description: '找出论文缺口与待补数据' }
];

export const PAPER_INTENT_LABELS: Record<PaperIntent, string> = {
	outline: '生成大纲',
	abstract: '起草摘要',
	related: '梳理相关工作',
	method: '写研究方法',
	experiment: '设计实验',
	results: '组织结果讨论',
	checklist: '完整性检查'
};

export const PAPER_INTENTS_BY_SECTION: Record<PaperSection, PaperIntent[]> = {
	选题与大纲: ['outline'],
	摘要: ['abstract'],
	相关工作: ['related'],
	研究方法: ['method'],
	实验设计: ['experiment'],
	结果与讨论: ['results'],
	完整性检查: ['checklist']
};

const CONTEXT_FIELDS_BY_SECTION: Record<PaperSection, PaperContextField[]> = {
	选题与大纲: [
		{ id: 'researchObject', label: '研究对象', placeholder: '例如：校园食堂高峰期服务窗口' },
		{
			id: 'researchQuestion',
			label: '研究问题',
			placeholder: '例如：增加服务窗口是否能降低平均等待时间？'
		},
		{
			id: 'outlineFocus',
			label: '论文侧重点',
			placeholder: '例如：模型构建、策略对比或课程知识应用'
		}
	],
	摘要: [
		{ id: 'researchBackground', label: '研究背景', placeholder: '这个系统为什么值得研究？' },
		{ id: 'methodSummary', label: '方法概述', placeholder: '使用什么模型、仿真方法或改进策略？' },
		{
			id: 'resultSummary',
			label: '结果情况',
			placeholder: '已有结果就填写；没有数据可填写“暂未完成实验”'
		}
	],
	相关工作: [
		{
			id: 'relatedWorkFocus',
			label: '相关工作主题',
			placeholder: '希望对比哪些概念、方法或研究方向？'
		},
		{ id: 'relatedMaterials', label: '已有资料', placeholder: '课程教材、笔记或已找到的文献线索' }
	],
	研究方法: [
		{ id: 'systemBoundary', label: '系统边界', placeholder: '研究哪些部分？哪些部分不纳入模型？' },
		{
			id: 'entitiesEventsResources',
			label: '实体、事件与资源',
			placeholder: '例如：顾客、到达事件、服务台'
		},
		{
			id: 'modelAssumptions',
			label: '建模假设',
			placeholder: '例如：到达服从某分布、服务时间如何处理'
		},
		{ id: 'dataSource', label: '数据来源', placeholder: '实验数据、教材案例、观测数据或待采集' }
	],
	实验设计: [
		{ id: 'baselineScenario', label: '基准场景', placeholder: '当前系统或未经优化的方案' },
		{ id: 'improvedScenario', label: '改进场景', placeholder: '准备比较的策略或优化方案' },
		{ id: 'metrics', label: '评价指标', placeholder: '例如：等待时间、吞吐量、资源利用率' },
		{ id: 'dataStatus', label: '数据情况', placeholder: '已有数据、需要仿真生成，或尚未确定' }
	],
	结果与讨论: [
		{ id: 'resultSummary', label: '实验结果', placeholder: '填写表格、数值或观察到的现象' },
		{ id: 'comparisonFindings', label: '对比发现', placeholder: '基准场景和改进场景有什么差异？' },
		{ id: 'limitations', label: '局限性', placeholder: '哪些结论还需要更多实验或数据支持？' }
	],
	完整性检查: [
		{
			id: 'draftContent',
			label: '已有草稿',
			placeholder: '粘贴大纲或章节内容，帮助智能体进行针对性检查'
		},
		{ id: 'courseRequirements', label: '课程要求', placeholder: '老师的格式、章节或评分要求' }
	]
};

export function contextFieldsForSection(section: PaperSection) {
	return CONTEXT_FIELDS_BY_SECTION[section];
}

const taskContext = (task: PaperTask) =>
	[
		`论文题目：${task.title.trim() || '（尚未填写，请先根据课程内容提出合适的题目）'}`,
		`关键词：${task.keywords.trim() || '（尚未填写）'}`,
		`当前章节：${task.section}`,
		...Object.entries(task.context ?? {})
			.filter(([, value]) => typeof value === 'string' && value.trim())
			.map(([key, value]) => `${key}：${value}`),
		...Object.entries(task.context?.attachedNotes ?? {})
			.filter(([, notes]) => Array.isArray(notes) && notes.length > 0)
			.map(
				([key, notes]) =>
					`${key}：已从笔记本关联笔记：${(notes as PaperNoteReference[])
						.map((note) => `${note.notebookName} · ${note.title}`)
						.join('、')}`
			),
		...(task.context?.attachedFiles ?? []).map(
			(file) =>
				`数据文件：${file.name}（${Math.ceil(file.size / 1024)} KB）${file.status ? `，${file.status}` : ''}${file.content ? `\n文件内容摘录：\n${file.content}` : ''}`
		)
	].join('\n');

export function buildPaperPrompt(intent: PaperIntent, task: PaperTask) {
	const context = taskContext(task);

	const prompts: Record<PaperIntent, string> = {
		outline: `请作为《系统建模与仿真》课程论文助手，基于下面的论文任务生成一份可执行的分章大纲。不要直接编造实验结果；对缺少的信息明确标记“待补充”。当前已绑定课程知识库，请优先从检索到的教材和笔记中提取可引用资料。\n\n【论文任务】\n${context}\n\n【输出格式】\n# 论文题目\n\n## 摘要\n- 研究问题\n- 方法\n- 预期结果（待补充）\n\n## 1. 绪论\n## 2. 相关工作\n## 3. 系统建模与研究方法\n## 4. 仿真实验设计\n## 5. 结果与讨论\n## 6. 结论与展望\n\n每一章都补充：\n- 写作目标\n- 需要的课程知识\n- 可引用资料：只列本次知识库检索到的教材/笔记；没有检索到时写“待补充资料”\n- 需要学生准备的证据`,
		abstract: `请为下面的课程论文起草一版中文摘要。摘要必须包含研究背景、研究问题、建模或仿真方法、评价指标和主要结果；没有真实实验数据的地方请写“待补充实验数据”，不要虚构结论。\n\n【论文任务】\n${context}\n\n请使用“背景—方法—结果—结论”的结构，输出一段 250—400 字的 Markdown 文本，并在末尾列出还需要补充的信息。`,
		related: `请围绕下面的课程论文梳理相关工作章节。只基于课程知识库和学生提供的资料组织概念、方法与研究方向，不要编造具体文献作者、年份或结论。\n\n【论文任务】\n${context}\n\n请输出：研究主题分类、各方向与本文的关系、本文准备采用的切入点，以及还需要补充的参考文献。`,
		method: `请围绕下面的论文任务撰写“研究方法”章节草稿，重点体现系统建模与仿真课程特色。\n\n【论文任务】\n${context}\n\n【必须覆盖】\n1. 研究对象与系统边界\n2. 实体、事件、资源和状态变量\n3. 建模假设及其合理性\n4. 输入数据与参数来源\n5. 仿真流程和模型验证方式\n\n使用 Markdown 标题和表格。无法从当前知识库确认的内容标记为“待补充依据”，不要凭空编造数据。`,
		experiment: `请为下面的课程论文设计一套可落地的仿真实验方案。\n\n【论文任务】\n${context}\n\n【输出格式】\n## 实验目的\n## 实验假设\n## 基准场景\n## 改进场景\n## 实验变量与控制变量\n## 评价指标\n至少考虑等待时间、吞吐量、资源利用率等适合仿真课程的指标。\n## 重复次数与结果呈现\n## 待补充数据\n\n请区分“设计建议”和“已有资料支持的事实”。`,
		results: `请围绕下面的课程论文组织“结果与讨论”章节。只解释学生提供的实验结果，不要虚构数值；如果结果不完整，请明确列出待补充的表格或实验。\n\n【论文任务】\n${context}\n\n请按“结果概述—基准与改进方案对比—原因解释—局限性—小结”的结构输出 Markdown 草稿。`,
		checklist: `请对下面的课程论文任务做一次完整性检查，不要替用户直接生成整篇论文。\n\n【论文任务】\n${context}\n\n请输出一个可执行的 checklist，按“状态 / 缺失内容 / 建议下一步 / 可引用资料”四列组织，并明确标记“已具备 / 部分具备 / 缺失”。至少逐项检查：\n- 论文题目与研究问题\n- 摘要\n- 相关工作与参考文献\n- 系统边界\n- 实体、事件、资源表\n- 建模假设表\n- 模型验证方式\n- 基准与改进实验场景\n- 评价指标\n- 实验结果数据\n- 结论与局限性\n对没有证据支持的部分标记为“待补充”，可引用资料只使用当前知识库检索到的教材和笔记。`
	};

	return prompts[intent];
}

export function paperChatTitle(task: PaperTask, fallback = '论文辅助') {
	const title = task.title.trim();
	return title ? `论文·${title.slice(0, 32)}` : fallback;
}

/** 兼容第一版论文卡片：把已存进历史的内部提示词识别回卡片动作。 */
export function paperIntentFromPrompt(prompt: string): PaperIntent | null {
	if (prompt.includes('生成一份可执行的分章大纲')) return 'outline';
	if (prompt.includes('起草一版中文摘要')) return 'abstract';
	if (prompt.includes('梳理相关工作章节')) return 'related';
	if (prompt.includes('撰写“研究方法”章节草稿')) return 'method';
	if (prompt.includes('设计一套可落地的仿真实验方案')) return 'experiment';
	if (prompt.includes('组织“结果与讨论”章节')) return 'results';
	if (prompt.includes('做一次完整性检查')) return 'checklist';
	return null;
}

export function paperIntentDisplay(intent: PaperIntent, section: PaperSection) {
	return `已选择论文任务卡：${PAPER_INTENT_LABELS[intent]}（当前章节：${section}）`;
}
