import { WEBUI_BASE_URL } from '$lib/constants';

export * from './toast';
export * from './fileSaver';
export * from './transitions';

/** 生成首字母头像（参考 open-webui 实现，浏览器环境专用） */
export const generateInitialsImage = (name: string): string => {
	if (typeof document === 'undefined') return `${WEBUI_BASE_URL}/user.png`;

	const canvas = document.createElement('canvas');
	const ctx = canvas.getContext('2d');
	if (!ctx) return `${WEBUI_BASE_URL}/user.png`;

	canvas.width = 100;
	canvas.height = 100;

	ctx.fillStyle = '#F39C12';
	ctx.fillRect(0, 0, canvas.width, canvas.height);

	ctx.fillStyle = '#FFFFFF';
	ctx.font = '40px Helvetica';
	ctx.textAlign = 'center';
	ctx.textBaseline = 'middle';

	const sanitizedName = (name ?? '').trim();
	const initials =
		sanitizedName.length > 0
			? sanitizedName[0] +
				(sanitizedName.split(' ').length > 1
					? sanitizedName[sanitizedName.lastIndexOf(' ') + 1]
					: '')
			: '';

	ctx.fillText(initials.toUpperCase(), canvas.width / 2, canvas.height / 2);

	return canvas.toDataURL();
};

/** 获取浏览器定位（无权限时抛出错误，调用方可自行兜底） */
export const getUserPosition = async (raw = false) => {
	const position = await new Promise<GeolocationPosition>((resolve, reject) => {
		navigator.geolocation.getCurrentPosition(resolve, reject);
	});

	const { latitude, longitude } = position.coords;

	if (raw) return { latitude, longitude };
	return `${latitude.toFixed(3)}, ${longitude.toFixed(3)} (lat, long)`;
};

/** 名称转 ID（小写、连字符） */
export const nameToId = (name: string): string =>
	(name ?? '')
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '');

/** 简单版本比较：required 是否高于 current */
export const compareVersion = (required: string, current: string): boolean => {
	const parse = (value: string) =>
		(value ?? '').split('.').map((part) => Number.parseInt(part, 10) || 0);
	const a = parse(required);
	const b = parse(current);
	const length = Math.max(a.length, b.length);
	for (let i = 0; i < length; i += 1) {
		const left = a[i] ?? 0;
		const right = b[i] ?? 0;
		if (left > right) return true;
		if (left < right) return false;
	}
	return false;
};

export const capitalizeFirstLetter = (text: string): string =>
	text ? text.charAt(0).toUpperCase() + text.slice(1) : text;
