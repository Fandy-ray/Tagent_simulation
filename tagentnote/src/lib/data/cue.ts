/**
 * 填空题的提示句（cue）要不要显示。
 *
 * 这个模块**不 import 任何东西**，纯函数，可用 node --test 单测。
 *
 * 出题提示词里 cue 只写了「中文提示语」，模型多半直接把题干又抄一遍放进来
 * （2026-10-24 页面实测：闪卡和整卷的填空几乎张张如此，连 ___ 都抄上了），
 * 于是卡片上同一句话出现两遍，一小一大。只是复述题干的 cue 就不显示；
 * 真是另给的提示（「服务强度的定义」）照常显示。
 */

/** 比较前去掉空白、标点、挖空和公式定界符，只看字面内容 */
const normalize = (value: string) =>
	value.replace(/_{2,}|\$|[\s，,。.、；;：:！!？?（）()「」“”"'《》]/g, '');

export function cueRepeatsText(cue: string, text: string): boolean {
	const shortCue = normalize(cue);
	const sentence = normalize(text);
	if (!shortCue) {
		return true;
	}
	return sentence.includes(shortCue) || shortCue.includes(sentence);
}
