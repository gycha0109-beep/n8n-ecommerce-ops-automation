$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
node --check "$root\mock-api\dist\server.js"
$proc = Start-Process node -ArgumentList "$root\mock-api\dist\server.js" -PassThru -WindowStyle Hidden
try {
  Start-Sleep -Milliseconds 500
  python "$root\scripts\smoke_harness.py"
  python "$root\scripts\verify-results.py"
  node "$root\scripts\verify-workflows.mjs"
} finally {
  Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
}
