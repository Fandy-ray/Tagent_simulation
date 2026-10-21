import { browser } from '$app/environment';

import { loadQaChats, saveQaChats, type QaChat, type QaMessage } from '$lib/data/qaConversations';
import { loadQaFolders, saveQaFolders, type QaFolder } from '$lib/data/qaFolders';

const SEEDED_KEY = 'tagentnote.qa.seeded.v1';
const MINUTE = 60 * 1000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

const folder = (
	id: string,
	name: string,
	parentId: string | null = null,
	expanded = true
): QaFolder => {
	const now = Date.now();
	return {
		id,
		name,
		parentId,
		expanded,
		systemPrompt: '',
		backgroundImageUrl: null,
		icon: '',
		knowledgeItems: [],
		createdAt: now - 7 * DAY,
		updatedAt: now - 2 * DAY
	};
};

const message = (id: string, role: QaMessage['role'], content: string): QaMessage => ({
	id,
	role,
	content
});

const seedFolders = (): QaFolder[] => [
	folder('folder-modeling', '系统建模'),
	folder('folder-simulation', '仿真实验', 'folder-modeling'),
	folder('folder-course', '课程答疑'),
	folder('folder-paper', '毕业论文')
];

const seedChats = (): QaChat[] => {
	const now = Date.now();
	const chat = (
		id: string,
		title: string,
		ago: number,
		folderId: string | null,
		messages: QaMessage[]
	): QaChat => ({
		id,
		title,
		updatedAt: now - ago,
		folderId,
		mode: 'qa',
		messages
	});

	return [
		chat('chat-modeling', '如何建立一级倒立摆的动力学模型？', 6 * MINUTE, null, [
			message('m1', 'user', '如何建立一级倒立摆的动力学模型？请从受力分析开始说明。'),
			message(
				'm2',
				'assistant',
				'可以先定义小车位置 x、摆杆与竖直方向的夹角 θ，再用拉格朗日方程建立广义坐标下的动力学模型：\n1. 写出小车与摆杆的动能 T 和势能 V；\n2. 令 L = T − V，代入欧拉-拉格朗日方程；\n3. 在平衡点附近线性化，得到状态空间形式 ẋ = Ax + Bu。'
			),
			message('m3', 'user', '平衡点线性化时需要注意什么？'),
			message(
				'm4',
				'assistant',
				'注意只在 θ ≈ 0 附近做小角度近似（sinθ≈θ，cosθ≈1），并把高阶项忽略；线性化后得到的 A、B 矩阵才是增量模型，后续控制器设计要基于该模型验证。'
			)
		]),
		chat('chat-pid', 'PID 控制器参数整定思路', 50 * MINUTE, 'folder-course', [
			message('p1', 'user', 'PID 控制器的参数应该怎么整定？'),
			message(
				'p2',
				'assistant',
				'建议从比例环节开始：先取较小 Kp，逐步增加直到系统出现稳定振荡；再加入微分环节抑制超调，最后用积分消除稳态误差。也可以使用 Ziegler-Nichols 经验公式做初值。'
			)
		]),
		chat('chat-simulation', '离散事件仿真：事件调度机制', 26 * HOUR, 'folder-simulation', [
			message('s1', 'user', '离散事件仿真中事件调度和活动扫描有什么区别？'),
			message(
				's2',
				'assistant',
				'事件调度以事件表为核心，按时间戳顺序取出最早事件处理，适合事件时间明确、事件数较少的系统；活动扫描按固定时间步检查所有活动条件，更适合条件触发密集的系统，但计算量更大。'
			)
		]),
		chat('chat-error', '仿真误差分析怎么写', 3 * DAY, 'folder-modeling', [
			message('e1', 'user', '仿真结果误差分析部分应该包含哪些内容？'),
			message(
				'e2',
				'assistant',
				'可以从三方面展开：误差来源（模型简化、参数估计、数值积分误差）、量化指标（相对误差、RMSE、最大偏差）以及改进措施（减小步长、参数辨识、与实验数据对比验证）。'
			)
		]),
		chat('chat-paper', '论文引言结构建议', 5 * DAY, 'folder-paper', [
			message('w1', 'user', '毕业论文引言部分的结构怎么安排？'),
			message(
				'w2',
				'assistant',
				'推荐采用“研究背景 → 国内外研究现状 → 现有方法不足 → 本文工作与贡献”的结构。背景部分交代问题的重要性，现状部分按方法分类综述，最后一段明确本文要解决的问题和创新点。'
			)
		]),
		chat('chat-old', '状态空间表达式答疑', 12 * DAY, null, [
			message('o1', 'user', '状态空间表达式和传递函数之间可以互相转换吗？'),
			message(
				'o2',
				'assistant',
				'可以。传递函数是状态空间模型在零初始条件下的拉普拉斯变换形式，G(s)=C(sI−A)⁻¹B+D；反过来，传递函数可以通过能控标准型或能观标准型实现为状态空间模型。'
			)
		])
	];
};

export function ensureQaSeed(): { chats: QaChat[]; folders: QaFolder[]; activeId: string | null } {
	if (!browser) return { chats: [], folders: [], activeId: null };

	const bundle = loadQaChats();
	let folders = loadQaFolders();

	if (localStorage.getItem(SEEDED_KEY)) {
		return { chats: bundle.chats, folders, activeId: bundle.activeId };
	}

	localStorage.setItem(SEEDED_KEY, '1');

	if (folders.length === 0) {
		folders = seedFolders();
		saveQaFolders(folders);
	}

	if (bundle.chats.length === 0) {
		const chats = seedChats();
		saveQaChats(chats, chats[0]?.id ?? null);
		return { chats, folders, activeId: chats[0]?.id ?? null };
	}

	return { chats: bundle.chats, folders, activeId: bundle.activeId };
}
