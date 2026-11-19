import type { Handle } from '@sveltejs/kit';

export const handle: Handle = async ({ event, resolve }) => {
	const response = await resolve(event);
	response.headers.set('X-Content-Type-Options', 'nosniff');
	response.headers.set('X-Frame-Options', 'DENY');
	response.headers.set('Referrer-Policy', 'no-referrer');
	response.headers.set(
		'Content-Security-Policy',
		"frame-ancestors 'none'; base-uri 'self'; object-src 'none'"
	);
	response.headers.set('Strict-Transport-Security', 'max-age=31536000');
	return response;
};
