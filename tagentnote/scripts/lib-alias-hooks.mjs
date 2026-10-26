// 让 node --test 认得 SvelteKit 的 $lib 别名：$lib/data/knowledge → src/lib/data/knowledge.ts。
// 只给测试用（被测模块 import 了 $lib 下别的纯 TS 模块时）；用法见 citations-enrich.test.mjs 开头。
export async function resolve(specifier, context, nextResolve) {
	if (specifier.startsWith('$lib/')) {
		const path = specifier.slice('$lib/'.length);
		const url = new URL(`../src/lib/${path}${/\.\w+$/.test(path) ? '' : '.ts'}`, import.meta.url);
		return nextResolve(url.href, context);
	}
	return nextResolve(specifier, context);
}
