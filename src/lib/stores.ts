import { writable, type Writable } from 'svelte/store';
import { APP_NAME } from '$lib/constants';

export const WEBUI_NAME = writable(APP_NAME);

/** 当前登录用户；管理员面板依赖 role === 'admin' */
export const user: Writable<any> = writable({
	id: 'local-admin',
	name: 'Admin',
	email: 'admin@local',
	role: 'admin',
	profile_image_url: '/favicon.png'
});

export const config: Writable<any> = writable({
	features: {
		enable_admin_chat_access: true,
		enable_admin_analytics: true
	},
	license_metadata: null
});

export const showSidebar = writable(false);
export const mobile = writable(false);
export const knowledge: Writable<any> = writable(null);
