const key = 'space-learning.records.v1';

export type SpaceRecord = {
	id: string;
	kind: '笔记' | '问答' | '实验' | '测评';
	context: string;
	title: string;
	content: string;
	date: string;
};

export function readSpaceRecords(): SpaceRecord[] {
	try {
		const stored = JSON.parse(localStorage.getItem(key) ?? '[]');
		return Array.isArray(stored) ? stored : [];
	} catch {
		return [];
	}
}

export function saveSpaceRecord(record: Omit<SpaceRecord, 'date'>) {
	const entries = readSpaceRecords().filter((item) => item.id !== record.id);
	localStorage.setItem(
		key,
		JSON.stringify([{ ...record, date: new Date().toISOString() }, ...entries])
	);
}

export function downloadSpaceRecords(entries: SpaceRecord[]) {
	const text = entries
		.map(
			({ kind, context, title, content, date }) =>
				`[${kind}] ${title}\n${context} · ${new Date(date).toLocaleString('zh-CN')}\n${content}`
		)
		.join('\n\n');
	const url = URL.createObjectURL(new Blob([text], { type: 'text/plain;charset=utf-8' }));
	const link = document.createElement('a');
	link.href = url;
	link.download = '航天探究学案.txt';
	link.click();
	window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}
