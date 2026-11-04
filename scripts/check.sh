#!/usr/bin/env sh
# Все проверки одной командой (D-056): тесты backend, тесты frontend, браузерные E2E.
# Всё выполняется в отдельной проверочной среде idea-contest-check (compose.check.yaml):
# своя база, свои контейнеры, без портов на компьютере. Рабочая среда не затрагивается.
#
#   sh scripts/check.sh                  — все проверки
#   sh scripts/check.sh backend e2e      — только выбранные: backend, frontend, e2e
#
# Windows (PowerShell): powershell -ExecutionPolicy Bypass -File scripts\check.ps1

cd "$(dirname "$0")/.." || exit 2
STEPS=${*:-backend frontend e2e}
COMPOSE="docker compose -f compose.yaml -f compose.check.yaml --profile test --profile e2e"
SUMMARY=""
FAILED=0

cleanup() {
  echo
  echo "== Удаление проверочной среды (контейнеры и её база)"
  $COMPOSE down -v --remove-orphans >/dev/null 2>&1
}
trap cleanup EXIT
trap 'exit 130' INT TERM

record() { # шаг, код возврата, секунды
  if [ "$2" -eq 0 ]; then status="пройдено"; else status="ОШИБКА (код $2)"; FAILED=1; fi
  SUMMARY="$SUMMARY$(printf '  %-10s %-18s %s с' "$1" "$status" "$3")
"
}

run_step() { # название, команда...
  name=$1
  shift
  echo
  echo "== $name"
  started=$(date +%s)
  "$@"
  code=$?
  record "$name" "$code" "$(($(date +%s) - started))"
}

e2e() {
  $COMPOSE up -d --wait frontend || return $?
  $COMPOSE run --rm e2e
}

for step in $STEPS; do
  case $step in
    backend | frontend | e2e) ;;
    *) echo "Неизвестный шаг: $step (есть: backend, frontend, e2e)"; exit 2 ;;
  esac
done

echo "== Подготовка: чистая проверочная среда и сборка образов"
$COMPOSE down -v --remove-orphans >/dev/null 2>&1
$COMPOSE build --quiet || { echo "Сборка образов не удалась"; exit 1; }

for step in $STEPS; do
  case $step in
    backend) run_step backend $COMPOSE run --rm tests ;;
    frontend) run_step frontend $COMPOSE run --rm frontend-tests ;;
    e2e) run_step e2e e2e ;;
  esac
done

echo
echo "== Итог"
printf '%s' "$SUMMARY"
if [ "$FAILED" -ne 0 ]; then
  echo "Есть ошибки. Снимки экрана и трассы упавших E2E — в e2e/results/."
  exit 1
fi
echo "Все проверки пройдены."
