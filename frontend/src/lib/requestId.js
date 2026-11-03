// Идентификатор запроса для защиты от повторной отправки формы (D-031, D-050).
//
// crypto.randomUUID есть только в «безопасном контексте» (https или localhost).
// Если приложение открыто по адресу вида http://192.168.…, собираем UUID v4 сами
// из crypto.getRandomValues — он доступен всегда.
export function newRequestId(cryptoImpl = globalThis.crypto) {
  if (typeof cryptoImpl.randomUUID === 'function') return cryptoImpl.randomUUID()
  const bytes = cryptoImpl.getRandomValues(new Uint8Array(16))
  bytes[6] = (bytes[6] & 0x0f) | 0x40 // версия 4
  bytes[8] = (bytes[8] & 0x3f) | 0x80 // вариант RFC 4122
  const hex = [...bytes].map((b) => b.toString(16).padStart(2, '0')).join('')
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`
}
