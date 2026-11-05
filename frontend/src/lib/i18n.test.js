// Переводы (D-065): словари полны, подстановки совпадают, формы множественного числа верны.
import { afterEach, describe, expect, it } from 'vitest'

import { dictionaries, locale, pluralIndex, setLocale, t, tn } from './i18n.js'

afterEach(() => setLocale('ru'))

function flatten(node, prefix = '', out = {}) {
  for (const [key, value] of Object.entries(node ?? {})) {
    const path = prefix ? `${prefix}.${key}` : key
    if (value && typeof value === 'object' && !Array.isArray(value)) flatten(value, path, out)
    else out[path] = value
  }
  return out
}

const placeholders = (value) =>
  [...new Set([value].flat().join(' ').match(/\{\w+\}/g) ?? [])].sort()

describe('словари', () => {
  for (const [area, { ru, en }] of Object.entries(dictionaries)) {
    it(`«${area}»: одинаковые ключи и подстановки в ru и en`, () => {
      const r = flatten(ru)
      const e = flatten(en)
      expect(Object.keys(e).sort()).toEqual(Object.keys(r).sort())
      for (const key of Object.keys(r)) {
        expect(placeholders(e[key]), `${area}.${key}`).toEqual(placeholders(r[key]))
        if (Array.isArray(r[key])) {
          expect(r[key], `${area}.${key}: три формы для русского`).toHaveLength(3)
          expect(e[key], `${area}.${key}: две формы для английского`).toHaveLength(2)
        } else {
          expect(typeof e[key], `${area}.${key}`).toBe('string')
          expect(e[key].trim(), `${area}.${key}: пустой перевод`).not.toBe('')
        }
      }
    })

    it(`«${area}»: в английском словаре нет кириллицы`, () => {
      const cyrillic = Object.entries(flatten(en)).filter(([, value]) => /[А-Яа-яЁё]/.test([value].flat().join(' ')))
      // Исключение — образцы текста, которые показывают именно кириллицу (шрифты, языки).
      expect(cyrillic.filter(([key]) => !key.endsWith('sample')).map(([key]) => key)).toEqual([])
    })
  }
})

describe('t и tn', () => {
  it('подстановка и смена языка', () => {
    expect(t('settings.notSaved', { error: 'нет связи' })).toBe('Настройка не сохранена: нет связи')
    setLocale('en')
    expect(locale.value).toBe('en')
    expect(t('settings.title')).toBe('Settings')
    expect(document.documentElement.lang).toBe('en')
  })

  it('формы множественного числа', () => {
    expect([1, 2, 5, 11, 21, 22, 25].map((n) => tn('common.votes', n))).toEqual([
      '1 голос', '2 голоса', '5 голосов', '11 голосов', '21 голос', '22 голоса', '25 голосов',
    ])
    setLocale('en')
    expect([0, 1, 2].map((n) => tn('common.votes', n))).toEqual(['0 votes', '1 vote', '2 votes'])
    expect(pluralIndex(1, 'en')).toBe(0)
  })

  it('неизвестный язык — русский; неизвестный ключ — сам ключ', () => {
    setLocale('de')
    expect(locale.value).toBe('ru')
    expect(t('нет.такого')).toBe('нет.такого')
  })
})
