# Все проверки одной командой (D-056): тесты backend, тесты frontend, браузерные E2E.
# Всё выполняется в отдельной проверочной среде idea-contest-check (compose.check.yaml):
# своя база, свои контейнеры, без портов на компьютере. Рабочая среда не затрагивается.
#
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1               — все проверки
#   powershell -ExecutionPolicy Bypass -File scripts\check.ps1 backend e2e   — только выбранные
#
# Linux, macOS: sh scripts/check.sh

$Steps = if ($args.Count) { $args } else { @('backend', 'frontend', 'e2e') }
Set-Location (Split-Path -Parent $PSScriptRoot)
$Compose = @('compose', '-f', 'compose.yaml', '-f', 'compose.check.yaml', '--profile', 'test', '--profile', 'e2e')
$Summary = @()
$Failed = $false

# Вывод docker — сразу в консоль (Out-Host), а из функции возвращается только код завершения.
function Invoke-Compose {
    & docker @Compose @args | Out-Host
    return $LASTEXITCODE
}

function Remove-CheckEnvironment {
    & docker @Compose down -v --remove-orphans *> $null
}

function Invoke-Step($Name, [scriptblock]$Body) {
    Write-Host ''
    Write-Host "== $Name"
    $watch = [Diagnostics.Stopwatch]::StartNew()
    $code = & $Body
    $seconds = [int]$watch.Elapsed.TotalSeconds
    if ($code -eq 0) { $status = 'пройдено' } else { $status = "ОШИБКА (код $code)"; $script:Failed = $true }
    $script:Summary += ('  {0,-10} {1,-18} {2} с' -f $Name, $status, $seconds)
}

foreach ($step in $Steps) {
    if (@('backend', 'frontend', 'e2e') -notcontains $step) {
        Write-Host "Неизвестный шаг: $step (есть: backend, frontend, e2e)"
        exit 2
    }
}

try {
    Write-Host '== Подготовка: чистая проверочная среда и сборка образов'
    Remove-CheckEnvironment
    if ((Invoke-Compose build --quiet) -ne 0) { Write-Host 'Сборка образов не удалась'; exit 1 }

    foreach ($step in $Steps) {
        switch ($step) {
            'backend' { Invoke-Step 'backend' { Invoke-Compose run --rm tests } }
            'frontend' { Invoke-Step 'frontend' { Invoke-Compose run --rm frontend-tests } }
            'e2e' {
                Invoke-Step 'e2e' {
                    $up = Invoke-Compose up -d --wait frontend
                    if ($up -ne 0) { return $up }
                    Invoke-Compose run --rm e2e
                }
            }
        }
    }

    Write-Host ''
    Write-Host '== Итог'
    $Summary | ForEach-Object { Write-Host $_ }
    if ($Failed) {
        Write-Host 'Есть ошибки. Снимки экрана и трассы упавших E2E — в e2e/results/.'
        exit 1
    }
    Write-Host 'Все проверки пройдены.'
}
finally {
    Write-Host ''
    Write-Host '== Удаление проверочной среды (контейнеры и её база)'
    Remove-CheckEnvironment
}
