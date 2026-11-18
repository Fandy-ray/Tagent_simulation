export const audioSettingsKey = 'admin-audio-settings';

export function readBrowserVoice(): SpeechSynthesisVoice | undefined {
	try {
		const saved = JSON.parse(localStorage.getItem(audioSettingsKey) ?? '{}');
		if (saved.ttsEngine !== 'web' || !saved.browserVoice) return;
		return window.speechSynthesis
			.getVoices()
			.find(({ voiceURI }) => voiceURI === saved.browserVoice);
	} catch {
		return undefined;
	}
}
