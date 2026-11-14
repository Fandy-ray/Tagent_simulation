const storageKey = 'space-learning.progress.v1';

export function readSpaceProgress(): string[] {
	try {
		const values: unknown = JSON.parse(localStorage.getItem(storageKey) ?? '[]');
		return Array.isArray(values)
			? values.filter((value): value is string => typeof value === 'string')
			: [];
	} catch {
		return [];
	}
}

export function markSpaceComplete(key: string): string[] {
	const progress = [...new Set([...readSpaceProgress(), key])];
	localStorage.setItem(storageKey, JSON.stringify(progress));
	return progress;
}
