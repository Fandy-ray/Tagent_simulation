import { browser } from '$app/environment';
import { readPersonalCache, writePersonalCache } from '$lib/apis/auth';

export type DirectConnection = {
	url: string;
	key: string;
	enabled?: boolean;
};

export type ToolServer = {
	id?: string;
	type?: 'openapi' | 'mcp';
	url: string;
	key: string;
	path: string;
	enabled?: boolean;
	spec?: string;
	spec_type?: 'url' | 'json';
	auth_type?: 'none' | 'bearer' | 'session' | 'system_oauth' | 'oauth_2.1' | 'oauth_2.1_static';
	headers?: Record<string, string> | string;
	functionNameFilterList?: string;
	name?: string;
	description?: string;
	info?: { id?: string; name?: string; description?: string };
	config?: { enable?: boolean; function_name_filter_list?: string };
	connection?: {
		type?: string;
		url?: string;
		key?: string;
		path?: string;
		enabled?: boolean;
		auth_type?: string;
		config?: { enable?: boolean };
	};
};

export type TerminalServer = {
	url: string;
	key: string;
	name: string;
	enabled: boolean;
	path: string;
	auth_type?: string;
	enable?: boolean;
};

export type MemoryItem = {
	id: string;
	content: string;
	createdAt: number;
};

export type UserSettings = {
	theme: 'system' | 'dark' | 'oled-dark' | 'light';
	language: string;
	notificationEnabled: boolean;
	system: string;
	params: Record<string, unknown>;
	displayName: string;
	avatarText: string;
	statusEmoji: string;
	statusMessage: string;
	bio: string;
	gender: string;
	dateOfBirth: string;
	webhookUrl: string;
	profileImageUrl: string;
	// Interface
	landingPageMode: '' | 'chat';
	widescreenMode: boolean;
	chatBubble: boolean;
	richTextInput: boolean;
	showFormattingToolbar: boolean;
	ctrlEnterToSend: boolean;
	copyFormatted: boolean;
	showUsername: boolean;
	highContrastMode: boolean;
	showChatTitleInTab: boolean;
	notificationSound: boolean;
	notificationSoundAlways: boolean;
	userLocation: boolean;
	hapticFeedback: boolean;
	chatDirection: 'LTR' | 'RTL' | 'auto';
	chatFadeStreamingText: boolean;
	collapseCodeBlocks: boolean;
	expandDetails: boolean;
	temporaryChatByDefault: boolean;
	titleAutoGenerate: boolean;
	autoFollowUps: boolean;
	autoTags: boolean;
	responseAutoCopy: boolean;
	largeTextAsFile: boolean;
	detectArtifacts: boolean;
	enableMessageQueue: boolean;
	textScale: number | null;
	backgroundImageUrl: string | null;
	webSearchAlways: boolean;
	showUpdateToast: boolean;
	showChangelog: boolean;
	insertSuggestionPrompt: boolean;
	keepFollowUpPrompts: boolean;
	insertFollowUpPrompt: boolean;
	regenerateMenu: boolean;
	renderMarkdownInPreviews: boolean;
	displayMultiModelResponsesInTabs: boolean;
	scrollOnBranchChange: boolean;
	stylizedPdfExport: boolean;
	showFloatingActionButtons: boolean;
	floatingActionButtons: { id: string; label: string; input: boolean; prompt: string }[] | null;
	promptAutocomplete: boolean;
	insertPromptAsRichText: boolean;
	iframeSandboxAllowSameOrigin: boolean;
	iframeSandboxAllowForms: boolean;
	voiceInterruption: boolean;
	showEmojiInCall: boolean;
	imageCompression: boolean;
	imageCompressionSize: { width: string; height: string };
	imageCompressionInChannels: boolean;
	splitLargeChunks: boolean;
	// Personalization
	memory: boolean;
	memories: MemoryItem[];
	userBio: string;
	// Audio
	speechAutoSend: boolean;
	responseAutoPlayback: boolean;
	sttEngine: string;
	sttLanguage: string;
	ttsEngine: string;
	ttsVoice: string;
	ttsPlaybackRate: number;
	nonLocalVoices: boolean;
	// Connections / Integrations
	directConnections: DirectConnection[];
	toolServers: ToolServer[];
	terminalServers: TerminalServer[];
};

export const defaultUserSettings = (): UserSettings => ({
	theme: 'dark',
	language: 'zh-CN',
	notificationEnabled: false,
	system: '',
	params: {},
	displayName: 'Tagent',
	avatarText: 'T',
	statusEmoji: '',
	statusMessage: '',
	bio: '',
	gender: '',
	dateOfBirth: '',
	webhookUrl: '',
	profileImageUrl: '',
	landingPageMode: '',
	widescreenMode: false,
	chatBubble: true,
	richTextInput: true,
	showFormattingToolbar: false,
	ctrlEnterToSend: false,
	copyFormatted: true,
	showUsername: false,
	highContrastMode: false,
	showChatTitleInTab: true,
	notificationSound: true,
	notificationSoundAlways: false,
	userLocation: false,
	hapticFeedback: false,
	chatDirection: 'auto',
	chatFadeStreamingText: true,
	collapseCodeBlocks: false,
	expandDetails: false,
	temporaryChatByDefault: false,
	titleAutoGenerate: true,
	autoFollowUps: true,
	autoTags: true,
	responseAutoCopy: false,
	largeTextAsFile: false,
	detectArtifacts: true,
	enableMessageQueue: true,
	textScale: null,
	backgroundImageUrl: null,
	webSearchAlways: false,
	showUpdateToast: true,
	showChangelog: true,
	insertSuggestionPrompt: false,
	keepFollowUpPrompts: false,
	insertFollowUpPrompt: false,
	regenerateMenu: true,
	renderMarkdownInPreviews: true,
	displayMultiModelResponsesInTabs: false,
	scrollOnBranchChange: true,
	stylizedPdfExport: true,
	showFloatingActionButtons: true,
	floatingActionButtons: null,
	promptAutocomplete: false,
	insertPromptAsRichText: false,
	iframeSandboxAllowSameOrigin: false,
	iframeSandboxAllowForms: false,
	voiceInterruption: false,
	showEmojiInCall: false,
	imageCompression: false,
	imageCompressionSize: { width: '', height: '' },
	imageCompressionInChannels: true,
	splitLargeChunks: false,
	memory: false,
	memories: [],
	userBio: '',
	speechAutoSend: false,
	responseAutoPlayback: false,
	sttEngine: '',
	sttLanguage: '',
	ttsEngine: '',
	ttsVoice: '',
	ttsPlaybackRate: 1,
	nonLocalVoices: false,
	directConnections: [],
	toolServers: [],
	terminalServers: []
});

export function loadUserSettings(): UserSettings {
	const defaults = defaultUserSettings();
	if (!browser) return defaults;
	try {
		const raw = readPersonalCache('settings');
		if (!raw) return defaults;
		const parsed = JSON.parse(raw) as Partial<UserSettings>;
		return {
			...defaults,
			...parsed,
			textScale:
				typeof parsed.textScale === 'number' && Number.isFinite(parsed.textScale)
					? Math.min(1.5, Math.max(1, parsed.textScale))
					: null,
			params: { ...(defaults.params ?? {}), ...(parsed.params ?? {}) },
			memories: Array.isArray(parsed.memories) ? parsed.memories : defaults.memories,
			directConnections: Array.isArray(parsed.directConnections)
				? parsed.directConnections
				: defaults.directConnections,
			toolServers: Array.isArray(parsed.toolServers) ? parsed.toolServers : defaults.toolServers,
			terminalServers: Array.isArray(parsed.terminalServers)
				? parsed.terminalServers
				: defaults.terminalServers,
			imageCompressionSize: {
				...defaults.imageCompressionSize,
				...(parsed.imageCompressionSize ?? {})
			},
			floatingActionButtons: Array.isArray(parsed.floatingActionButtons)
				? parsed.floatingActionButtons
				: (parsed.floatingActionButtons ?? null)
		};
	} catch {
		return defaults;
	}
}

export function saveUserSettings(settings: UserSettings) {
	if (!browser) return;
	try {
		writePersonalCache('settings', JSON.stringify(settings));
	} catch {
		// ignore
	}
}

export function applyTheme(theme: UserSettings['theme']) {
	if (!browser) return;

	const root = document.documentElement;
	const themes = ['dark', 'light', 'oled-dark', 'system'];

	// 移除所有主题类
	themes.forEach((t) => root.classList.remove(t));

	// 重置 CSS 变量
	root.style.removeProperty('--color-gray-800');
	root.style.removeProperty('--color-gray-850');
	root.style.removeProperty('--color-gray-900');
	root.style.removeProperty('--color-gray-950');

	let themeToApply = theme;

	if (theme === 'oled-dark') {
		root.style.setProperty('--color-gray-800', '#101010');
		root.style.setProperty('--color-gray-850', '#050505');
		root.style.setProperty('--color-gray-900', '#000000');
		root.style.setProperty('--color-gray-950', '#000000');
		themeToApply = 'dark';
	} else if (theme === 'dark') {
		root.style.setProperty('--color-gray-800', '#333');
		root.style.setProperty('--color-gray-850', '#262626');
		root.style.setProperty('--color-gray-900', '#171717');
		root.style.setProperty('--color-gray-950', '#0d0d0d');
		themeToApply = 'dark';
	}

	root.classList.add(themeToApply);

	localStorage.setItem('theme', theme);
}

export function applyTextScale(scale: number | null) {
	if (!browser) return;
	const safe =
		typeof scale === 'number' && Number.isFinite(scale) ? Math.min(1.5, Math.max(1, scale)) : null;
	const effective = safe && safe !== 1 ? safe : null;
	document.documentElement.style.setProperty(
		'--app-text-scale',
		effective ? String(effective) : '1'
	);
	document.documentElement.style.fontSize = effective ? `${16 * effective}px` : '';
}

export function applyHighContrast(enabled: boolean) {
	if (!browser) return;
	document.documentElement.classList.toggle('high-contrast', enabled);
}

export function playNotificationSound() {
	if (!browser) return;
	try {
		const AudioContextCtor =
			window.AudioContext ??
			(window as Window & { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
		if (!AudioContextCtor) return;
		const ctx = new AudioContextCtor();
		const osc = ctx.createOscillator();
		const gain = ctx.createGain();
		osc.type = 'sine';
		osc.frequency.value = 880;
		gain.gain.value = 0.04;
		osc.connect(gain);
		gain.connect(ctx.destination);
		osc.start();
		osc.stop(ctx.currentTime + 0.12);
	} catch {
		// ignore
	}
}
