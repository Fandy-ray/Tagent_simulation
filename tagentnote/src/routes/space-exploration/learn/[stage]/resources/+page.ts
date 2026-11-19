import { error } from '@sveltejs/kit';
import { stageKeys } from '$lib/data/spaceLearning';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params }) => {
	const stage = stageKeys.find((key) => key === params.stage);
	if (!stage) error(404, '找不到这个学段');
	return { stage };
};
