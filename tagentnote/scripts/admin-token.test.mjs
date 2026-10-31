import assert from 'node:assert/strict';
import test, { beforeEach } from 'node:test';

const storage = new Map();
globalThis.localStorage = {
	getItem: (key) => storage.get(key) ?? null,
	setItem: (key, value) => storage.set(key, value),
	removeItem: (key) => storage.delete(key)
};

const { get } = await import('svelte/store');
const { adminToken, clearAdminToken, rememberAdminToken, rememberedAdminToken, restoreAdminToken } =
	await import('../src/lib/data/adminToken.ts');

beforeEach(() => {
	storage.clear();
	adminToken.set('');
});

test('不勾记住时什么都不写进浏览器', () => {
	adminToken.set('secret');
	assert.equal(storage.size, 0);
	restoreAdminToken();
	assert.equal(get(adminToken), 'secret');
});

test('记住之后刷新（内存清空）能放回来', () => {
	rememberAdminToken(' secret ');
	assert.equal(rememberedAdminToken(), 'secret');
	restoreAdminToken();
	assert.equal(get(adminToken), 'secret');
});

test('内存里已经有口令时不被记住的那份盖掉', () => {
	rememberAdminToken('old');
	adminToken.set('new');
	restoreAdminToken();
	assert.equal(get(adminToken), 'new');
});

test('锁定或被后端拒了：内存和记住的一起清', () => {
	rememberAdminToken('secret');
	adminToken.set('secret');
	clearAdminToken();
	assert.equal(get(adminToken), '');
	assert.equal(rememberedAdminToken(), '');
	restoreAdminToken();
	assert.equal(get(adminToken), '');
});

test('取消勾选（传空）就不再记住', () => {
	rememberAdminToken('secret');
	rememberAdminToken('');
	assert.equal(storage.size, 0);
});

test('浏览器不让用存储时不报错，只留在内存里', () => {
	const real = globalThis.localStorage;
	globalThis.localStorage = {
		getItem() {
			throw new Error('blocked');
		},
		setItem() {
			throw new Error('blocked');
		},
		removeItem() {
			throw new Error('blocked');
		}
	};
	try {
		rememberAdminToken('secret');
		assert.equal(rememberedAdminToken(), '');
		clearAdminToken();
	} finally {
		globalThis.localStorage = real;
	}
});
