export type FunctionType = 'pipe' | 'filter' | 'action';

export type MockFunction = {
	id: string;
	name: string;
	type: FunctionType;
	owner: string;
	email: string;
	description: string;
	version: string;
	isActive: boolean;
	isGlobal: boolean;
	fundingUrl: string;
	content: string;
	valves: Record<string, string>;
};

export const FUNCTION_STORAGE_KEY = 'admin-mock-functions';

export const defaultFunctions: MockFunction[] = [
	{
		id: 'research-assistant-pipe',
		name: 'Research Assistant',
		type: 'pipe',
		owner: 'TAgent Team',
		email: 'admin@tagent.local',
		description: '检索并总结研究资料，将多来源信息整理为结构化答案。',
		version: '1.2.0',
		isActive: true,
		isGlobal: false,
		fundingUrl: '',
		content: 'class Pipe:\n    def pipe(self, body: dict):\n        return body',
		valves: { endpoint: 'https://api.example.com', max_results: '5' }
	},
	{
		id: 'safety-check-filter',
		name: 'Safety Check',
		type: 'filter',
		owner: 'TAgent Team',
		email: 'admin@tagent.local',
		description: '检查输入内容并在提交前应用安全规则。',
		version: '0.8.1',
		isActive: true,
		isGlobal: true,
		fundingUrl: 'https://example.com/support',
		content: 'class Filter:\n    def inlet(self, body: dict, user=None):\n        return body',
		valves: { priority: '0', blocked_terms: '' }
	},
	{
		id: 'citation-helper-action',
		name: 'Citation Helper',
		type: 'action',
		owner: 'TAgent Team',
		email: 'admin@tagent.local',
		description: '为回答添加引用检查和格式整理操作。',
		version: '0.4.0',
		isActive: false,
		isGlobal: false,
		fundingUrl: '',
		content:
			'class Action:\n    async def action(self, body: dict, user=None):\n        return body',
		valves: { citation_style: 'APA' }
	},
	{
		id: 'prompt-polisher-filter',
		name: 'Prompt Polisher',
		type: 'filter',
		owner: '林知夏',
		email: 'lin.zx@example.com',
		description: '清理并优化提交给模型的提示词。',
		version: '1.0.0',
		isActive: true,
		isGlobal: false,
		fundingUrl: '',
		content: 'class Filter:\n    def inlet(self, body: dict, user=None):\n        return body',
		valves: { priority: '1' }
	},
	{
		id: 'web-search-pipe',
		name: 'Web Search',
		type: 'pipe',
		owner: '陈嘉木',
		email: 'chen.jm@example.com',
		description: '从配置的搜索源获取实时网页结果。',
		version: '2.1.0',
		isActive: true,
		isGlobal: true,
		fundingUrl: '',
		content: 'class Pipe:\n    def pipe(self, body: dict):\n        return body',
		valves: { search_url: 'https://search.example.com', api_key: '' }
	},
	{
		id: 'answer-rater-action',
		name: 'Answer Rater',
		type: 'action',
		owner: '周予安',
		email: 'zhou.ya@example.com',
		description: '根据参考答案为当前回复生成质量评分。',
		version: '0.6.2',
		isActive: false,
		isGlobal: false,
		fundingUrl: '',
		content:
			'class Action:\n    async def action(self, body: dict, user=None):\n        return body',
		valves: { threshold: '0.75' }
	}
];

export const isBrowser = () => typeof window !== 'undefined' && typeof localStorage !== 'undefined';

export function loadMockFunctions(): MockFunction[] {
	if (!isBrowser()) return defaultFunctions.map((item) => ({ ...item }));
	try {
		const raw = localStorage.getItem(FUNCTION_STORAGE_KEY);
		if (!raw) return defaultFunctions.map((item) => ({ ...item }));
		const parsed: unknown = JSON.parse(raw);
		if (!Array.isArray(parsed)) return defaultFunctions.map((item) => ({ ...item }));
		return parsed.filter(
			(item): item is MockFunction =>
				Boolean(item) && typeof item === 'object' && typeof (item as MockFunction).id === 'string'
		);
	} catch {
		return defaultFunctions.map((item) => ({ ...item }));
	}
}

export function saveMockFunctions(next: MockFunction[]) {
	if (!isBrowser()) return;
	try {
		localStorage.setItem(FUNCTION_STORAGE_KEY, JSON.stringify(next));
	} catch {
		// 忽略本地存储失败（隐私模式等），mock 场景下无需中断交互
	}
}

export function toFunctionId(value: string) {
	return value
		.trim()
		.toLowerCase()
		.replace(/[^a-z0-9]+/g, '-')
		.replace(/^-+|-+$/g, '');
}

export function inferFunctionType(source: string): FunctionType {
	if (/class\s+Action\b/.test(source)) return 'action';
	if (/class\s+Pipe\b/.test(source)) return 'pipe';
	if (/class\s+Filter\b/.test(source)) return 'filter';
	if (/def\s+(inlet|outlet)\b/.test(source)) return 'filter';
	return 'pipe';
}

export const functionBoilerplate = `"""
title: Example Function
author: TAgent
version: 0.1
"""

from pydantic import BaseModel, Field
from typing import Optional


class Filter:
    class Valves(BaseModel):
        priority: int = Field(
            default=0, description="Priority level for the filter operations."
        )
        max_turns: int = Field(
            default=8, description="Maximum allowable conversation turns for a user."
        )
        pass

    def __init__(self):
        # Initialize 'valves' with specific configurations.
        self.valves = self.Valves()
        pass

    def inlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # 在请求发送到模型前处理：校验、改写或补充上下文
        print(f"inlet:{__name__}")
        messages = body.get("messages", [])
        if len(messages) > self.valves.max_turns:
            raise Exception(
                f"Conversation turn limit exceeded. Max turns: {self.valves.max_turns}"
            )
        return body

    def outlet(self, body: dict, __user__: Optional[dict] = None) -> dict:
        # 在模型返回后处理：修改、记录或做安全过滤
        return body
`;
