import { writable, type Writable } from 'svelte/store';
import { APP_NAME } from '$lib/constants';

export const WEBUI_NAME = writable(APP_NAME);

/** 当前登录用户；管理员面板依赖 role === 'admin' */
type LocalUser = {
	id: string;
	name: string;
	email: string;
	role: 'admin' | 'user';
	profile_image_url: string;
};

export const user: Writable<LocalUser> = writable({
	id: 'local-admin',
	name: 'Admin',
	email: 'admin@local',
	role: 'admin',
	profile_image_url: '/favicon.png'
});

type LocalConfig = {
	features: Record<string, boolean>;
	license_metadata: unknown;
};

export const config: Writable<LocalConfig> = writable({
	features: {
		enable_admin_chat_access: true,
		enable_admin_analytics: true
	},
	license_metadata: null
});

export const showSidebar = writable(false);
export const mobile = writable(false);
export const knowledge: Writable<unknown> = writable(null);
