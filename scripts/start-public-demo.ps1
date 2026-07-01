# BI Platform — Public Demo Links
# Requires: ngrok auth token (free) from https://dashboard.ngrok.com/get-started/your-authtoken

$token = Read-Host "Введите ваш ngrok auth token (получить на https://dashboard.ngrok.com/get-started/your-authtoken)"

if ([string]::IsNullOrWhiteSpace($token)) {
    Write-Host "❌ Ngrok token не введен. Регистрация: https://ngrok.com/signup" -ForegroundColor Red
    exit 1
}

# Configure ngrok
ngrok config add-authtoken $token

Write-Host ""
Write-Host "🚀 Запускаю публичные туннели..." -ForegroundColor Cyan
Write-Host "   Metabase  -> порт 3000"
Write-Host "   FastAPI   -> порт 8000"
Write-Host ""

# Start tunnels in separate windows
Start-Process powershell -ArgumentList "-Command", "ngrok http 3000 --name metabase; Read-Host 'Press Enter to close'" -WindowStyle Normal
Start-Process powershell -ArgumentList "-Command", "ngrok http 8000 --name fastapi; Read-Host 'Press Enter to close'" -WindowStyle Normal

Write-Host "⏳ Ждем 5 секунд для инициализации..."
Start-Sleep -Seconds 5

# Fetch public URLs from ngrok API
try {
    $tunnels = Invoke-RestMethod -Uri "http://localhost:4040/api/tunnels" -ErrorAction Stop
    Write-Host ""
    Write-Host "✅ Публичные ссылки готовы:" -ForegroundColor Green
    foreach ($t in $tunnels.tunnels) {
        $name = $t.name
        $url = $t.public_url
        if ($name -eq "metabase") {
            Write-Host "   📊 Metabase (BI Dashboard): $url" -ForegroundColor Yellow
        } elseif ($name -eq "fastapi") {
            Write-Host "   🔌 FastAPI (Swagger UI):    $url/docs" -ForegroundColor Yellow
        }
    }
} catch {
    Write-Host "⚠️  Не удалось получить ссылки автоматически. Откройте http://localhost:4040 в браузере, чтобы увидеть URL." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "💡 Чтобы остановить: закройте окна PowerShell с ngrok или нажмите Ctrl+C в них."
