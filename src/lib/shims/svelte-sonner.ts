import { toast as base } from '$lib/utils/toast';

/** 兼容 open-webui 的 `import { toast } from 'svelte-sonner'` */
export const toast = {
	error: (message: string) => base.error(String(message)),
	success: (message: string) => base.success(String(message)),
	info: (message: string) => base.info(String(message)),
	message: (message: string) => base.info(String(message))
};
