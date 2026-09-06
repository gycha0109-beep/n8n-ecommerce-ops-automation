param([string]$Url = "http://localhost:5678/webhook/ecommerce-order-intake")
$orders = Get-Content "$PSScriptRoot\..\fixtures\shopify_orders.json" -Raw | ConvertFrom-Json
$body = @{ source = "shopify"; payload = $orders[0] } | ConvertTo-Json -Depth 8
Invoke-RestMethod -Method Post -Uri $Url -ContentType "application/json" -Body $body
