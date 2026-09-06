$ErrorActionPreference = "Stop"
$root = Resolve-Path "$PSScriptRoot\.."
Push-Location $root
try {
  docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-order-intake.json
  docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-error-handler.json
  docker compose exec -T n8n n8n import:workflow --input=/workflows/ecommerce-daily-summary.json
  Write-Host "n8n workflow import: PASS"
} finally { Pop-Location }
