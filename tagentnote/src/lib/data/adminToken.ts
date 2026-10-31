/**
 * 管理口令放在哪：默认只在内存里；勾了「在这台电脑上记住」才写进 localStorage（说明见 $lib/apis/admin）。
 */
import { get, writable } from 'svelte/store';

export const adminToken = writable('');

const REMEMBERED_TOKEN_KEY = 'tagent:admin-token';

/** 这台电脑记住的口令；浏览器不让读（无痕、禁用存储）时当作没记住 */
export function rememberedAdminToken(): string {
	try {
		return localStorage.getItem(REMEMBERED_TOKEN_KEY) ?? '';
	} catch {
		return '';
	}
}

/** 记住这份口令；传空字符串＝不再记住。存不了就只留在内存里，不影响这次使用 */
export function rememberAdminToken(token: string): void {
	try {
		if (token.trim()) {
			localStorage.setItem(REMEMBERED_TOKEN_KEY, token.trim());
		} else {
			localStorage.removeItem(REMEMBERED_TOKEN_KEY);
		}
	} catch {
		/* 见上 */
	}
}

/**
 * 把记住的口令放回内存，页面 onMount 时调。不能在模块加载时读：
 * 服务端渲染时没有 localStorage，两边渲染出来的东西会对不上。
 */
export function restoreAdminToken(): void {
	const remembered = rememberedAdminToken();
	if (remembered && !get(adminToken)) {
		adminToken.set(remembered);
	}
}

/** 锁定、或口令被后端拒了：内存里的和这台电脑记住的一起清掉 */
export function clearAdminToken(): void {
	adminToken.set('');
	rememberAdminToken('');
}
