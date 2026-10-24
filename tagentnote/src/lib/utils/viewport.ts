/**
 * 窄屏（手机竖屏）判断，和 Tailwind 的 md 断点（768px）一致。
 *
 * 窄屏上侧栏不再占位：它盖在内容上（见 MockSidebar 的 aside），默认收起，
 * 在里面选完对话就自己收起。以前 375 宽时侧栏默认展开，把对话挤成一条细缝。
 */
export const isNarrowScreen = (): boolean =>
	typeof window !== 'undefined' && window.matchMedia?.('(max-width: 767px)').matches === true;
