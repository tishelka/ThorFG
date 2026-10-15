param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('update', 'package-runtime', 'check', 'host-load', 'loader', 'cube', 'deliver-plugin', 'install-plugin')]
    [string]$Action,
    [Parameter(Mandatory = $true)][string]$SSHHost,
    [string]$SSHUser = 'armada',
    [string]$RemoteRepo = '/var/home/armada/thorfg',
    [string]$Ref = 'master',
    [string]$ExpectedSha256,
    [string]$RuntimeOutput = 'artifacts/runtime',
    [string]$WaylandDisplay,
    [string]$Package = (Join-Path $PSScriptRoot '../artifacts/ThorFG-dev.zip')
)
$ErrorActionPreference = 'Stop'
if ($SSHUser -notmatch '^[a-z_][a-z0-9_-]*$' -or $SSHHost -notmatch '^[a-zA-Z0-9.:-]+$') {
    throw 'Некорректный SSH user/host'
}
if ($RemoteRepo -notmatch '^/[A-Za-z0-9_./-]+$' -or $RemoteRepo.Contains('..')) { throw 'Нужен абсолютный REMOTE_REPO без .., пробелов и специальных символов' }
if ($ExpectedSha256 -and $ExpectedSha256 -notmatch '^[a-f0-9]{64}$') { throw 'Некорректный SHA-256' }
if ($RuntimeOutput -notmatch '^[A-Za-z0-9_./-]+$' -or $RuntimeOutput.StartsWith('/') -or $RuntimeOutput.Contains('..')) { throw 'RuntimeOutput должен быть относительным путём внутри проекта' }
function Quote-Sh([string]$Value) {
    $singleQuoteChar = [string][char]39
    $doubleQuoteChar = [string][char]34
    $escapedQuote = $singleQuoteChar + $doubleQuoteChar + $singleQuoteChar + $doubleQuoteChar + $singleQuoteChar
    return $singleQuoteChar + $Value.Replace($singleQuoteChar, $escapedQuote) + $singleQuoteChar
}
function Invoke-Remote([string[]]$Arguments) {
    $command = 'cd ' + (Quote-Sh $RemoteRepo) + ' && ' + (($Arguments | ForEach-Object { Quote-Sh $_ }) -join ' ')
    & ssh "$SSHUser@$SSHHost" $command
    if ($LASTEXITCODE -ne 0) { throw "Удалённая операция завершилась с кодом $LASTEXITCODE" }
}
switch ($Action) {
    'update' {
        # Новый helper передаётся через stdin: существующий checkout ещё не обязан его содержать.
        $source = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'safe_update.py') -Encoding UTF8 -Raw
        $command = 'python3 - --repo ' + (Quote-Sh $RemoteRepo) + ' --ref ' + (Quote-Sh $Ref)
        $previousEncoding = $OutputEncoding
        try {
            $OutputEncoding = New-Object System.Text.UTF8Encoding($false)
            $source | & ssh "$SSHUser@$SSHHost" $command
            if ($LASTEXITCODE -ne 0) { throw 'Обновление остановлено; проверьте локальную резервную копию на Thor' }
        } finally { $OutputEncoding = $previousEncoding }
    }
    'package-runtime' {
        if (-not $ExpectedSha256) { throw 'Для ручной сборки явно укажите -ExpectedSha256 из вашего протокола' }
        Invoke-Remote @('distrobox', 'enter', '--name', 'thorfg-build-f44', '--', 'python3',
            "$RemoteRepo/runtime/build.py", '--variant', 'historical', '--package-existing',
            '--use-existing-checkout', "$RemoteRepo/.build/historical", '--build-dir', "$RemoteRepo/.build/historical/build-llvm",
            '--expected-sha256', $ExpectedSha256, '--output', "$RemoteRepo/$RuntimeOutput")
    }
    'deliver-plugin' {
        $resolvedPackage = (Resolve-Path -LiteralPath $Package).Path
        $localDigest = (Get-FileHash -LiteralPath $resolvedPackage -Algorithm SHA256).Hash.ToLowerInvariant()
        # Фиксированное имя назначения; существующая установка плагина не затрагивается.
        & scp $resolvedPackage "$SSHUser@${SSHHost}:$RemoteRepo/ThorFG-dev.zip"
        if ($LASTEXITCODE -ne 0) { throw 'SCP завершился ошибкой' }
        $check = "import hashlib,pathlib,sys; p=pathlib.Path('ThorFG-dev.zip'); sys.exit(0 if hashlib.sha256(p.read_bytes()).hexdigest()==sys.argv[1] else 1)"
        Invoke-Remote @('python3', '-c', $check, $localDigest)
        Write-Output 'ZIP передан; SHA-256 совпал. Плагин и runtime ещё не устанавливались.'
    }
    'install-plugin' {
        Invoke-Remote @('python3', 'scripts/decky_plugin.py', 'install', '--package', 'ThorFG-dev.zip')
    }
    default {
        $probeArgs = @('python3', 'scripts/device_probe.py', '--mode', $Action)
        if ($ExpectedSha256) { $probeArgs += @('--expected-sha256', $ExpectedSha256) }
        if ($WaylandDisplay) { $probeArgs += @('--wayland-display', $WaylandDisplay) }
        Invoke-Remote $probeArgs
    }
}
