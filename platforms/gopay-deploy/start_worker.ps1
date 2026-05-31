$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

Push-Location "$root\app"
try {
    python -m opai worker run @args
} finally {
    Pop-Location
}
