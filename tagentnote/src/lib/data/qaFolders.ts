import { browser } from '$app/environment';
import { readPersonalCache, writePersonalCache } from '$lib/apis/auth';

export type QaFolder = {
	id: string;
	name: string;
	parentId: string | null;
	expanded?: boolean;
	systemPrompt?: string;
	backgroundImageUrl?: string | null;
	icon?: string;
	knowledgeItems?: { id: string; name: string; type: 'collection' | 'file' }[];
	createdAt: number;
	updatedAt: number;
};

const normalize = (item: Partial<QaFolder>): QaFolder | null => {
	if (!item || typeof item.id !== 'string' || typeof item.name !== 'string') return null;
	return {
		id: item.id,
		name: item.name,
		parentId: item.parentId ?? null,
		expanded: item.expanded ?? true,
		systemPrompt: item.systemPrompt ?? '',
		backgroundImageUrl: item.backgroundImageUrl ?? null,
		icon: item.icon ?? '',
		knowledgeItems: Array.isArray(item.knowledgeItems) ? item.knowledgeItems : [],
		createdAt: item.createdAt ?? Date.now(),
		updatedAt: item.updatedAt ?? Date.now()
	};
};

export function loadQaFolders(): QaFolder[] {
	if (!browser) return [];
	try {
		const raw = readPersonalCache('qa_folders');
		if (!raw) return [];
		const parsed = JSON.parse(raw) as unknown;
		if (!Array.isArray(parsed)) return [];
		return parsed.map((item) => normalize(item as Partial<QaFolder>)).filter(Boolean) as QaFolder[];
	} catch {
		return [];
	}
}

export function saveQaFolders(folders: QaFolder[]) {
	if (!browser) return;
	try {
		writePersonalCache('qa_folders', JSON.stringify(folders));
	} catch {
		// ignore quota
	}
}

export function createQaFolder(
	name: string,
	parentId: string | null = null,
	extra: Partial<
		Pick<QaFolder, 'systemPrompt' | 'backgroundImageUrl' | 'icon' | 'knowledgeItems'>
	> = {}
): QaFolder {
	const now = Date.now();
	return {
		id: `folder-${now}-${Math.random().toString(36).slice(2, 7)}`,
		name: name.trim() || '未命名分组',
		parentId,
		expanded: true,
		systemPrompt: extra.systemPrompt ?? '',
		backgroundImageUrl: extra.backgroundImageUrl ?? null,
		icon: extra.icon ?? '',
		knowledgeItems: extra.knowledgeItems ?? [],
		createdAt: now,
		updatedAt: now
	};
}

/** Collect folder id + all descendant ids */
export function collectFolderTreeIds(folders: QaFolder[], rootId: string): Set<string> {
	const ids = new Set<string>([rootId]);
	let changed = true;
	while (changed) {
		changed = false;
		for (const folder of folders) {
			if (folder.parentId && ids.has(folder.parentId) && !ids.has(folder.id)) {
				ids.add(folder.id);
				changed = true;
			}
		}
	}
	return ids;
}

export function wouldCreateCycle(
	folders: QaFolder[],
	folderId: string,
	newParentId: string | null
): boolean {
	if (!newParentId) return false;
	if (folderId === newParentId) return true;
	const descendants = collectFolderTreeIds(folders, folderId);
	return descendants.has(newParentId);
}
