/**
 * 输入框里的附件怎么发给模型。
 *
 * 以前只把文件名拼进问题（「[附件:a.pdf]」），模型根本看不到内容。现在：
 * - 读得成文字的（纯文本、Markdown、代码、表格、JSON……）把内容带上；
 * - 读不了的（PDF、Word、图片……）明说没发，不假装发了；
 * - 带了附件时，检索知识库只用学生打的那句话：几千字的附件拿去检索等于没检索。
 *
 * 纯函数、不碰 DOM，可以离线单测（scripts/attachments.test.mjs）。
 */

/** 附件内容一共最多带这么多字：后端单条消息上限 2 万字，留出问题本身和技能要求的位置 */
export const MAX_ATTACHMENT_CHARS = 12_000;
/** 超过这么大的文件不读：再大也只能截前面一小段，读整个文件白白卡页面 */
export const MAX_ATTACHMENT_BYTES = 2_000_000;
/** 检索提示的上限，和后端 MAX_RETRIEVAL_QUERY_CHARS 一致 */
export const MAX_RETRIEVAL_QUERY_CHARS = 200;

const TEXT_EXTENSIONS = new Set([
	'txt',
	'md',
	'markdown',
	'csv',
	'tsv',
	'json',
	'jsonl',
	'yaml',
	'yml',
	'xml',
	'html',
	'htm',
	'tex',
	'bib',
	'log',
	'ini',
	'toml',
	'sql',
	'py',
	'ipynb',
	'js',
	'ts',
	'java',
	'c',
	'h',
	'cpp',
	'hpp',
	'cs',
	'go',
	'rs',
	'm',
	'r',
	'sh',
	'bat',
	'ps1'
]);

const TEXT_MIME_TYPES = new Set([
	'application/json',
	'application/xml',
	'application/x-yaml',
	'application/x-tex',
	'application/javascript',
	'application/x-sh'
]);

export const extensionOf = (name: string) => {
	const dot = name.lastIndexOf('.');
	return dot >= 0 ? name.slice(dot + 1).toLowerCase() : '';
};

export function isTextFile(file: { name: string; type: string }): boolean {
	return (
		file.type.startsWith('text/') ||
		TEXT_MIME_TYPES.has(file.type) ||
		TEXT_EXTENSIONS.has(extensionOf(file.name))
	);
}

/** 读不了的附件，给学生的一句说明 */
export function unsupportedReason(file: { name: string; type: string; size?: number }): string {
	if (file.size !== undefined && file.size > MAX_ATTACHMENT_BYTES) {
		return '文件太大（超过 2 MB），没有发送内容';
	}
	if (file.type.startsWith('image/')) return '图片目前还不能识别，没有发送';
	const ext = extensionOf(file.name);
	if (ext === 'pdf' || ext === 'doc' || ext === 'docx' || ext === 'ppt' || ext === 'pptx') {
		return `${ext.toUpperCase()} 目前还不能读，可以复制正文粘贴进来`;
	}
	return '这种文件目前还不能读，没有发送内容';
}

export type AttachmentPart = {
	name: string;
	/** 读出来的文字；没有就是读不了 */
	content?: string;
	/** 读不了的原因 */
	unsupported?: string;
};

export type ComposedMessage = {
	/** 真正发给模型的 */
	request: string;
	/** 聊天里显示的：只列附件名，不把几千字的内容贴在气泡里 */
	display: string;
	/** 检索知识库用的那句话；undefined = 就用 request（没带附件、技能时） */
	retrievalQuery?: string;
	/** 读不了、没发出去的附件 */
	skipped: AttachmentPart[];
};

export type SkillPart = { name: string; content: string };

const clip = (text: string, limit: number) => text.replace(/\s+/g, ' ').trim().slice(0, limit);

/**
 * 把「学生打的字 + 附件 + 选中的技能」拼成一条消息。
 * 附件超出总长度时从后面截，截掉多少写清楚，免得模型以为看到的就是全文。
 */
export function composeMessage(
	typed: string,
	attachments: AttachmentPart[],
	skills: SkillPart[] = []
): ComposedMessage {
	const question = typed.trim();
	const readable = attachments.filter((item) => item.content !== undefined && item.content.trim());
	const skipped = attachments.filter((item) => item.content === undefined || !item.content.trim());
	const usableSkills = skills.filter((skill) => skill.content.trim());

	const blocks: string[] = [];
	let budget = MAX_ATTACHMENT_CHARS;
	for (const item of readable) {
		const text = item.content!.trim();
		if (budget <= 0) {
			blocks.push(`【附件：${item.name}】（太长了，没有放进来）`);
			continue;
		}
		const kept = text.slice(0, budget);
		budget -= kept.length;
		const cut = text.length - kept.length;
		blocks.push(
			`【附件：${item.name}】\n\`\`\`\n${kept}\n\`\`\`${cut > 0 ? `\n（后面还有 ${cut} 字，太长没有放进来）` : ''}`
		);
	}
	if (usableSkills.length) {
		blocks.push(
			[
				'【回答要求】',
				...usableSkills.map((skill) => `- ${skill.name}：${skill.content.trim()}`)
			].join('\n')
		);
	}

	const lead = question || (readable.length ? '请结合附件回答。' : '');
	const request = [lead, ...blocks].filter(Boolean).join('\n\n');

	const notes = [
		attachments.length ? `📎 ${attachments.map((item) => item.name).join('、')}` : '',
		usableSkills.length ? `🧩 ${usableSkills.map((skill) => skill.name).join('、')}` : ''
	].filter(Boolean);
	const display = [question || lead, ...notes].filter(Boolean).join('\n\n');

	const extended = blocks.length > 0;
	const retrievalQuery = extended
		? clip(question || readable[0]?.content || lead, MAX_RETRIEVAL_QUERY_CHARS) || undefined
		: undefined;

	return { request, display, retrievalQuery, skipped };
}
