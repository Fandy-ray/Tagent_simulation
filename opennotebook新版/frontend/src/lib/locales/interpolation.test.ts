import { describe, it, expect, beforeAll } from 'vitest'
import { createInstance } from 'i18next'
import { resources } from './index'

// Mirrors the interpolation config in src/lib/i18n.ts
const i18n = createInstance()

beforeAll(async () => {
  await i18n.init({
    resources,
    lng: 'en-US',
    fallbackLng: 'en-US',
    interpolation: {
      escapeValue: false, // react already safes from xss
    },
  })
})

describe('i18next interpolation', () => {
  it('interpolates a single variable', () => {
    expect(i18n.t('chat.chatWith', { name: 'Sources' })).toBe('Chat with Sources')
  })

  it('interpolates multiple variables', () => {
    expect(i18n.t('sources.batchPartial', { success: 2, failed: 1 })).toBe(
      '2 succeeded, 1 failed',
    )
  })

  it('resolves plural forms from the base key', () => {
    // 原版用的是播客页的 podcasts.usedByCount；新版砍掉了播客，界面里已没有复数键，
    // 这里临时加一组，照样检验 i18next 的 _one/_other 解析没被配置坏。
    i18n.addResource('en-US', 'translation', 'pluralProbe.items_one', '{{count}} item')
    i18n.addResource('en-US', 'translation', 'pluralProbe.items_other', '{{count}} items')
    expect(i18n.t('pluralProbe.items', { count: 1, lng: 'en-US' })).toBe('1 item')
    expect(i18n.t('pluralProbe.items', { count: 3, lng: 'en-US' })).toBe('3 items')
  })

  it('does not escape interpolated values (React escapes at render)', () => {
    expect(i18n.t('notebooks.deleteNotebookDesc', { name: 'Research & Notes' })).toBe(
      'Are you sure you want to delete "Research & Notes"? This action cannot be undone.',
    )
  })

  it('interpolates in a non-English locale', () => {
    expect(
      i18n.t('sources.selectedCount', { count: 4, lng: 'pt-BR' }),
    ).toContain('4')
  })
})
