// Защита от устаревших ответов (D-040, D-049).
//
// Снимки могут приходить не в том порядке, в каком запрашивались. Применяем ответ,
// только если он не старее уже показанного: сначала сравниваем revision (номер
// изменения данных), а при равном revision — время сервера (снимки до и после срока
// различаются только им).
export function isFresher(candidate, current) {
  if (!current) return true
  if (candidate.revision !== current.revision) return candidate.revision > current.revision
  return Date.parse(candidate.server_time) >= Date.parse(current.server_time)
}
