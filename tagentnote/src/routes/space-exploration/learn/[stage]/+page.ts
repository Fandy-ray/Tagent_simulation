import { error } from '@sveltejs/kit';
import { spaceTopics, stageKeys } from '$lib/data/spaceLearning';
import type { PageLoad } from './$types';

export const load: PageLoad = ({ params, url }) => {
	const stage = stageKeys.find((key) => key === params.stage);
	if (!stage) error(404, '找不到这个学段');
	const topic = spaceTopics[stage].find((item) => item.id === url.searchParams.get('topic'));
	const requestedLesson = url.searchParams.get('lesson');
	const lesson = topic?.lessons.find((item) => item.id === requestedLesson);
	return { stage, topic, lesson, assessment: Boolean(topic && requestedLesson === 'review') };
};
