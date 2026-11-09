import { browser } from '$app/environment';
import { env } from '$env/dynamic/public';
import { get, writable } from 'svelte/store';
import { clearAdminToken } from '$lib/data/adminToken';

export type Account = {
	id: string;
	email: string | null;
	username?: string | null;
	name: string;
	role: 'student' | 'admin';
	verified: boolean;
	email_verification_required?: boolean;
	active: boolean;
	deletion_pending?: boolean;
};

export type Course = {
	id: string;
	name: string;
	description: string;
	model_ids: string[];
	notebook_ids: string[];
	active: boolean;
};

export const authMode = writable<'loading' | 'enabled' | 'disabled' | 'unavailable'>('loading');
export const currentAccount = writable<Account | null>(null);
export const availableCourses = writable<Course[]>([]);
export const currentCourseId = writable('general');
export const registrationOpen = writable(false);
export const emailVerificationRequired = writable(false);
export const passwordResetAvailable = writable(false);
export const authReady = writable(false);
export const syncError = writable('');
let csrf = '';
let initialized: Promise<void> | null = null;
const dataKeys = {
	settings: 'tagentnote.user.settings.v1',
	qa_chats: 'tagentnote.qa.chats.v1',
	qa_folders: 'tagentnote.qa.folders.v1',
	workspace: 'tagentnote.workspace.v1',
	controls: 'tagentnote.qa.controls.v1'
} as const;
export type PersonalKind = keyof typeof dataKeys;
const versions = new Map<string, number>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
const writes = new Map<string, Promise<void>>();
const blockedKeys = new Set<string>();
const pendingKey = (key: string) => `${key}.pending`;
const userPrefix = (user: Account) => `tagent.account.${user.id}.`;

export function hasPendingPersonalWrites(): boolean {
	if (!browser) return false;
	const user = get(currentAccount);
	if (!user) return false;
	for (let index = 0; index < sessionStorage.length; index++) {
		const key = sessionStorage.key(index);
		if (key?.startsWith(userPrefix(user)) && key.endsWith('.pending')) return true;
	}
	return false;
}

export function exportPendingPersonalData(): Blob {
	const user = get(currentAccount);
	if (!browser || !user) throw new Error('请先登录。');
	const items: { kind: string; context: string; data: unknown }[] = [];
	for (let index = 0; index < sessionStorage.length; index++) {
		const marker = sessionStorage.key(index);
		if (!marker?.startsWith(userPrefix(user)) || !marker.endsWith('.pending')) continue;
		const key = marker.slice(0, -'.pending'.length);
		const raw = sessionStorage.getItem(key);
		if (raw === null) continue;
		const parts = key.slice(userPrefix(user).length).split('.');
		let data: unknown = raw;
		try {
			data = JSON.parse(raw);
		} catch {
			// 格式损坏时保留原文，仍可供人工恢复。
		}
		items.push({ context: parts[0], kind: parts[1], data });
	}
	if (items.length === 0) throw new Error('当前没有可导出的本机草稿。');
	return new Blob(
		[
			JSON.stringify({ account_id: user.id, exported_at: new Date().toISOString(), items }, null, 2)
		],
		{
			type: 'application/json'
		}
	);
}

const contextFor = (kind: PersonalKind) =>
	kind === 'settings' || kind === 'controls' ? 'global' : get(currentCourseId);
const legacyContextFor = (kind: PersonalKind) =>
	kind === 'settings' || kind === 'controls' ? 'global' : 'general';
const scopedKey = (kind: PersonalKind, user: Account, context = contextFor(kind)) =>
	`tagent.account.${user.id}.${context}.${kind}`;

export function legacyDataKinds(): PersonalKind[] {
	if (!browser) return [];
	const user = get(currentAccount);
	return (Object.keys(dataKeys) as PersonalKind[]).filter(
		(kind) =>
			localStorage.getItem(dataKeys[kind]) !== null &&
			(!user || (versions.get(scopedKey(kind, user, legacyContextFor(kind))) || 0) === 0)
	);
}

export type LegacyDataOverview = {
	kind: PersonalKind;
	label: string;
	summary: string;
	valid: boolean;
};

export function legacyDataOverview(): LegacyDataOverview[] {
	if (!browser) return [];
	const labels: Record<PersonalKind, string> = {
		settings: '个人设置（可能包含第三方连接密钥）',
		qa_chats: '答疑会话',
		qa_folders: '答疑文件夹',
		workspace: '工作空间内容',
		controls: '答疑控制设置'
	};
	return legacyDataKinds().map((kind) => {
		try {
			const parsed: unknown = JSON.parse(localStorage.getItem(dataKeys[kind]) || 'null');
			let count: number | null = null;
			if (kind === 'qa_chats' && parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
				const chats = (parsed as { chats?: unknown }).chats;
				if (!Array.isArray(chats)) throw new Error('invalid chats');
				count = chats.length;
			} else if (kind === 'qa_folders' && Array.isArray(parsed)) {
				count = parsed.length;
			} else if (
				kind === 'workspace' &&
				parsed &&
				typeof parsed === 'object' &&
				!Array.isArray(parsed)
			) {
				count = Object.values(parsed).reduce<number>(
					(total, value) => total + (Array.isArray(value) ? value.length : 0),
					0
				);
			} else if (
				(kind === 'settings' || kind === 'controls') &&
				parsed &&
				typeof parsed === 'object' &&
				!Array.isArray(parsed)
			) {
				// 只展示是否存在，不把设置中的连接信息或密钥展示给下一位使用者。
			} else {
				throw new Error('invalid legacy shape');
			}
			return {
				kind,
				label: labels[kind],
				summary: count === null ? '已保存' : `${count} 项`,
				valid: true
			};
		} catch {
			return { kind, label: labels[kind], summary: '格式无法识别，不能导入', valid: false };
		}
	});
}

export function readPersonalCache(kind: PersonalKind): string | null {
	if (!browser) return null;
	const user = get(currentAccount);
	return get(authMode) === 'enabled'
		? user
			? sessionStorage.getItem(scopedKey(kind, user))
			: null
		: localStorage.getItem(dataKeys[kind]);
}

export function writePersonalCache(kind: PersonalKind, raw: string): void {
	if (!browser) return;
	if (get(authMode) !== 'enabled') {
		localStorage.setItem(dataKeys[kind], raw);
		return;
	}
	const user = get(currentAccount);
	if (!user) throw new Error('请先登录。');
	if (!navigator.onLine) throw new Error('离线时不能保存账号数据。');
	const context = contextFor(kind);
	const key = scopedKey(kind, user, context);
	if (blockedKeys.has(key))
		throw new Error('另一台设备已更新这份内容，请先导出本机草稿并处理冲突。');
	const previousMarker = sessionStorage.getItem(pendingKey(key));
	try {
		sessionStorage.setItem(pendingKey(key), String(versions.get(key) || 0));
		sessionStorage.setItem(key, raw);
	} catch (cause) {
		if (previousMarker === null) sessionStorage.removeItem(pendingKey(key));
		else sessionStorage.setItem(pendingKey(key), previousMarker);
		throw cause;
	}
	const oldTimer = timers.get(key);
	if (oldTimer) clearTimeout(oldTimer);
	timers.set(
		key,
		setTimeout(() => {
			timers.delete(key);
			void persistKey(key, kind, context).catch(() => {});
		}, 350)
	);
}

function persistKey(key: string, kind: PersonalKind, context: string): Promise<void> {
	const prior = writes.get(key) || Promise.resolve();
	const pending = prior
		.catch(() => {})
		.then(async () => {
			const current = sessionStorage.getItem(key);
			if (current === null) return;
			const response = await putPersonal(
				kind,
				JSON.parse(current),
				versions.get(key) || 0,
				context === 'global' ? 'general' : context
			);
			versions.set(key, response.version);
			if (sessionStorage.getItem(key) === current) sessionStorage.removeItem(pendingKey(key));
			else sessionStorage.setItem(pendingKey(key), String(response.version));
			if (!hasPendingPersonalWrites() && blockedKeys.size === 0) syncError.set('');
		})
		.catch((cause) => {
			if (
				cause instanceof AuthError &&
				['version_conflict', 'account_changed', 'account_context_missing'].includes(
					cause.code || ''
				)
			) {
				blockedKeys.add(key);
			}
			syncError.set(
				cause instanceof Error ? `保存到服务器失败：${cause.message}` : '保存到服务器失败。'
			);
			throw cause;
		});
	writes.set(key, pending);
	return pending;
}

export async function flushPersonalWrites(): Promise<void> {
	if (!browser || get(authMode) !== 'enabled') return;
	for (const [key, timer] of timers) {
		clearTimeout(timer);
		timers.delete(key);
		const parts = key.split('.');
		void persistKey(key, parts[4] as PersonalKind, parts[3]).catch(() => {});
	}
	await Promise.allSettled([...writes.values()]);
	const user = get(currentAccount);
	if (user) {
		for (const key of versions.keys()) {
			if (!key.startsWith(userPrefix(user)) || sessionStorage.getItem(pendingKey(key)) === null)
				continue;
			if (blockedKeys.has(key))
				throw new Error('另一台设备已更新这份内容，请先导出本机草稿并处理冲突。');
			await persistKey(key, key.split('.')[4] as PersonalKind, key.split('.')[3]);
		}
	}
	if (hasPendingPersonalWrites()) throw new Error('仍有本机草稿尚未同步，请重试或先导出草稿。');
	const error = get(syncError);
	if (error) throw new Error(error);
}

const temporaryKey = (name: string) => {
	const user = get(currentAccount);
	return get(authMode) === 'enabled' && user
		? `tagent.account.${user.id}.${get(currentCourseId)}.temporary.${name}`
		: name;
};
const temporaryStore = () => (get(authMode) === 'enabled' ? sessionStorage : localStorage);
export const readTemporary = (name: string) =>
	browser ? temporaryStore().getItem(temporaryKey(name)) : null;
export const writeTemporary = (name: string, raw: string) => {
	if (browser) temporaryStore().setItem(temporaryKey(name), raw);
};
export const removeTemporary = (name: string) => {
	if (browser) temporaryStore().removeItem(temporaryKey(name));
};

async function hydratePersonal(user: Account): Promise<void> {
	for (const kind of Object.keys(dataKeys) as PersonalKind[]) {
		const context = contextFor(kind);
		const key = scopedKey(kind, user, context);
		const result = await getPersonal<unknown>(kind, context === 'global' ? 'general' : context);
		const pending = sessionStorage.getItem(pendingKey(key));
		const local = sessionStorage.getItem(key);
		if (pending !== null && local !== null) {
			const pendingVersion = Number(pending);
			if (Number.isSafeInteger(pendingVersion) && pendingVersion === result.version) {
				versions.set(key, pendingVersion);
				try {
					await persistKey(key, kind, context);
				} catch {
					// 保留本机草稿与待同步标记，用户可重试。
				}
			} else {
				versions.set(key, result.version);
				blockedKeys.add(key);
				syncError.set('另一台设备已更新个人内容；本机草稿已保留，请导出草稿后处理冲突。');
			}
			continue;
		}
		if (pending !== null) sessionStorage.removeItem(pendingKey(key));
		versions.set(key, result.version);
		if (result.data === null) sessionStorage.removeItem(key);
		else sessionStorage.setItem(key, JSON.stringify(result.data));
	}
	// 旧浏览器内容只能导入通用区。若登录时恢复的是课程页，也要先知道通用区
	// 是否已有服务端数据，避免再次提示导入或误以为可以覆盖。
	if (get(currentCourseId) !== 'general') {
		for (const kind of ['qa_chats', 'qa_folders', 'workspace'] as const) {
			const key = scopedKey(kind, user, 'general');
			if (!versions.has(key)) {
				const result = await getPersonal<unknown>(kind, 'general');
				versions.set(key, result.version);
			}
		}
	}
	if (hasPendingPersonalWrites() && !get(syncError)) {
		syncError.set('仍有本机草稿尚未同步，请重试或先导出草稿。');
	}
}

export async function importLegacyData(): Promise<{
	imported: PersonalKind[];
	skipped: PersonalKind[];
}> {
	const user = get(currentAccount);
	if (!browser || !user || get(authMode) !== 'enabled') throw new Error('请先登录。');
	const imported: PersonalKind[] = [];
	const skipped: PersonalKind[] = [];
	const candidates = legacyDataOverview();
	if (candidates.some((entry) => !entry.valid)) {
		throw new Error('旧数据中有无法识别的内容。请先备份这台浏览器的数据；未导入任何内容。');
	}
	for (const { kind } of candidates) {
		const context = legacyContextFor(kind);
		const key = scopedKey(kind, user, context);
		if ((versions.get(key) || 0) !== 0) {
			skipped.push(kind);
			continue;
		}
		const raw = localStorage.getItem(dataKeys[kind]);
		if (raw === null) continue;
		const response = await putPersonal(
			kind,
			JSON.parse(raw),
			0,
			context === 'global' ? 'general' : context
		);
		versions.set(key, response.version);
		sessionStorage.setItem(key, raw);
		imported.push(kind);
	}
	return { imported, skipped };
}

const base = () => (env.PUBLIC_AGENT_URL?.trim() || '/agent-api').replace(/\/$/, '');

export class AuthError extends Error {
	constructor(
		message: string,
		readonly status: number,
		readonly code?: string
	) {
		super(message);
		this.name = 'AuthError';
	}
}

export function sessionHeaders(method = 'GET'): Headers {
	const headers = new Headers();
	if (get(authMode) === 'enabled') {
		const account = get(currentAccount);
		if (account) headers.set('X-Tagent-Account-Id', account.id);
		headers.set('X-Tagent-Course-Id', get(currentCourseId));
		if (!['GET', 'HEAD', 'OPTIONS'].includes(method.toUpperCase()) && csrf) {
			headers.set('X-Tagent-CSRF', csrf);
		}
	}
	return headers;
}

export async function authFetch(path: string, init: RequestInit = {}): Promise<Response> {
	const method = init.method || 'GET';
	const headers = new Headers(init.headers);
	sessionHeaders(method).forEach((value, name) => {
		if (!headers.has(name)) headers.set(name, value);
	});
	return fetch(`${base()}${path}`, { ...init, headers, credentials: 'same-origin' });
}

async function json<T>(path: string, init: RequestInit = {}): Promise<T> {
	const response = await authFetch(path, init);
	const payload = await response.json().catch(() => ({}));
	if (!response.ok) {
		const error = payload?.error as { message?: string; code?: string } | undefined;
		if (response.status === 401 && !path.startsWith('/auth/')) currentAccount.set(null);
		throw new AuthError(
			error?.message || `请求失败（${response.status}）`,
			response.status,
			error?.code
		);
	}
	return payload as T;
}

export const identityRequest = <T>(path: string, method = 'GET', data?: unknown): Promise<T> =>
	json<T>(path, {
		method,
		headers: data === undefined ? undefined : { 'Content-Type': 'application/json' },
		body: data === undefined ? undefined : JSON.stringify(data)
	});

const body = (value: unknown) => ({
	method: 'POST',
	headers: { 'Content-Type': 'application/json' },
	body: JSON.stringify(value)
});

async function refreshCourses(user: Account) {
	const result = await json<{ courses: Course[] }>('/me/courses');
	availableCourses.set(result.courses);
	const key = `tagent.course.${user.id}`;
	const remembered = browser ? sessionStorage.getItem(key) : null;
	const selected =
		remembered && result.courses.some((course) => course.id === remembered)
			? remembered
			: 'general';
	currentCourseId.set(selected);
}

export async function initializeAuth(): Promise<void> {
	if (!browser) return;
	if (initialized) return initialized;
	initialized = (async () => {
		authReady.set(false);
		syncError.set('');
		try {
			const status = await json<{
				enabled: boolean;
				registration_open: boolean;
				email_verification_required: boolean;
				password_reset_available: boolean;
			}>('/auth/status');
			registrationOpen.set(status.registration_open);
			emailVerificationRequired.set(Boolean(status.email_verification_required));
			passwordResetAvailable.set(Boolean(status.password_reset_available));
			if (!status.enabled) {
				authMode.set('disabled');
				authReady.set(true);
				return;
			}
			authMode.set('enabled');
			clearAdminToken();
			try {
				const session = await json<{ user: Account; csrf: string }>('/auth/me');
				csrf = session.csrf;
				currentAccount.set(session.user);
				await refreshCourses(session.user);
				await hydratePersonal(session.user);
			} catch (error) {
				if (!(error instanceof AuthError && error.status === 401)) throw error;
			}
			authReady.set(true);
		} catch {
			authMode.set('unavailable');
			authReady.set(false);
		} finally {
			initialized = null;
		}
	})();
	return initialized;
}

export async function login(identifier: string, password: string): Promise<Account> {
	if (get(currentAccount)) {
		throw new AuthError('请先退出当前账号，再登录其他账号。', 409, 'already_logged_in');
	}
	authReady.set(false);
	syncError.set('');
	try {
		const session = await json<{ user: Account; csrf: string }>(
			'/auth/login',
			body({ identifier, password })
		);
		csrf = session.csrf;
		currentAccount.set(session.user);
		await refreshCourses(session.user);
		await hydratePersonal(session.user);
		return session.user;
	} catch (cause) {
		if (get(currentAccount)) {
			syncError.set('账号已登录，但个人数据未能完整载入。请检查连接后刷新页面。');
		}
		throw cause;
	} finally {
		authReady.set(true);
	}
}

export async function logout(): Promise<void> {
	await flushPersonalWrites();
	const user = get(currentAccount);
	try {
		await json('/auth/logout', body({}));
	} catch (cause) {
		if (!(cause instanceof AuthError && cause.status === 401)) throw cause;
	} finally {
		csrf = '';
		if (browser && user) {
			for (let index = sessionStorage.length - 1; index >= 0; index--) {
				const key = sessionStorage.key(index);
				if (key?.startsWith(`tagent.account.${user.id}.`)) sessionStorage.removeItem(key);
			}
		}
		for (const timer of timers.values()) clearTimeout(timer);
		timers.clear();
		writes.clear();
		versions.clear();
		blockedKeys.clear();
		syncError.set('');
		currentAccount.set(null);
		availableCourses.set([]);
		currentCourseId.set('general');
	}
}

export async function chooseCourse(id: string): Promise<void> {
	if (id !== 'general' && !get(availableCourses).some((course) => course.id === id)) {
		throw new Error('你尚未加入这门课程。');
	}
	authReady.set(false);
	const previous = get(currentCourseId);
	const user = get(currentAccount);
	try {
		await flushPersonalWrites();
		syncError.set('');
		currentCourseId.set(id);
		if (user) await hydratePersonal(user);
		if (browser && user) sessionStorage.setItem(`tagent.course.${user.id}`, id);
	} catch (cause) {
		currentCourseId.set(previous);
		syncError.set('切换课程失败。请检查连接后重试。');
		throw cause;
	} finally {
		authReady.set(true);
	}
}

export const register = (identifier: string, password: string, name: string) =>
	json<{ message: string }>('/auth/register', body({ email: identifier, password, name }));
export const verifyEmail = (token: string) =>
	json<{ verified: boolean }>('/auth/verify-email', body({ token }));
export const requestPasswordReset = (email: string) =>
	json<{ message: string }>('/auth/password/forgot', body({ email }));
export const resetPassword = (token: string, password: string) =>
	json<{ reset: boolean }>('/auth/password/reset', body({ token, password }));

export async function getPersonal<T>(
	kind: string,
	course = get(currentCourseId)
): Promise<{ version: number; data: T | null }> {
	return json(`/me/data/${kind}`, { headers: { 'X-Tagent-Course-Id': course } });
}

export async function putPersonal<T>(
	kind: string,
	data: T,
	version: number,
	course = get(currentCourseId)
): Promise<{ version: number }> {
	return json(`/me/data/${kind}`, {
		method: 'PUT',
		headers: { 'Content-Type': 'application/json', 'X-Tagent-Course-Id': course },
		body: JSON.stringify({ data, version })
	});
}

export async function exportAccount(): Promise<Blob> {
	const response = await authFetch('/me/export');
	if (!response.ok) throw new AuthError('导出失败', response.status);
	return response.blob();
}

export async function deleteAccount(password: string): Promise<{ deleted: boolean }> {
	await flushPersonalWrites();
	return json('/me/account', {
		method: 'DELETE',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ password })
	});
}

export async function changePassword(
	currentPassword: string,
	newPassword: string
): Promise<{ changed: boolean }> {
	await flushPersonalWrites();
	return json(
		'/me/password',
		body({ current_password: currentPassword, new_password: newPassword })
	);
}
