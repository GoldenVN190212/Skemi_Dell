# Ollama Setup Script for Skemi
# This script sets up Ollama with the required models

Write-Host "Setting up Skemi AI Models with Ollama..."

# Check if Ollama is installed
try {
    $ollamaVersion = ollama --version 2>$null
    Write-Host "✅ Ollama is already installed (version: $ollamaVersion)" -ForegroundColor Green
} catch {
    Write-Host "❌ Ollama not found. Installing Ollama..." -ForegroundColor Red
    
    # Install Ollama (Windows)
    if ($IsWindows) {
        # Download and install Ollama for Windows
        $ollamaUrl = "https://ollama.com/download/OllamaSetup.exe"
        $ollamaPath = "$env:TEMP\ollama-setup.exe"
        
        try {
            Invoke-WebRequest -Uri $ollamaUrl -OutFile $ollamaPath
            Start-Process -FilePath $ollamaPath -Wait
            Write-Host "✅ Ollama installed successfully" -ForegroundColor Green
        } catch {
            Write-Host "❌ Failed to install Ollama. Please install manually from https://ollama.com" -ForegroundColor Red
            exit 1
        }
    } else {
        # Install Ollama for Linux/Mac
        curl -fsSL https://ollama.com/install.sh | sh
        Write-Host "✅ Ollama installed successfully" -ForegroundColor Green
    }
}

# Start Ollama service
Write-Host "🚀 Starting Ollama service..." -ForegroundColor Yellow

try {
    # Start Ollama in background
    if ($IsWindows) {
        Start-Process -FilePath "ollama" -ArgumentList "serve" -WindowStyle Hidden
    } else {
        ollama serve &
    }
    
    # Wait for Ollama to start
    Start-Sleep -Seconds 5
    
    # Check if Ollama is running
    $maxRetries = 10
    $retryCount = 0
    
    while ($retryCount -lt $maxRetries) {
        try {
            $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 5
            if ($response.StatusCode -eq 200) {
                Write-Host "✅ Ollama is running successfully!" -ForegroundColor Green
                break
            }
        } catch {
            Write-Host "⏳ Waiting for Ollama to start... ($($retryCount + 1)/$maxRetries)" -ForegroundColor Yellow
            Start-Sleep -Seconds 2
            $retryCount++
        }
    }
    
    if ($retryCount -eq $maxRetries) {
        Write-Host "❌ Failed to start Ollama. Please check logs." -ForegroundColor Red
        exit 1
    }
    
} catch {
    Write-Host "❌ Error starting Ollama: $_" -ForegroundColor Red
    exit 1
}

# Pull required models
Write-Host "📥 Pulling required AI models..." -ForegroundColor Cyan

$models = @(
    "gpt-4o-mini:latest",      # Main chat model
    "llava:latest",            # Vision model
    "qwen3-235b-vl:latest"   # Analysis model
)

foreach ($model in $models) {
    Write-Host "📥 Pulling $model..." -ForegroundColor Cyan
    try {
        ollama pull $model
        Write-Host "✅ Successfully pulled $model" -ForegroundColor Green
    } catch {
        Write-Host "❌ Failed to pull $model. Will try later..." -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "🎉 Skemi AI Models Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Available Models:" -ForegroundColor Cyan
Write-Host "  • Chat: gpt-4o-mini:latest" -ForegroundColor White
Write-Host "  • Vision: llava:latest" -ForegroundColor White  
Write-Host "  • Analysis: qwen3-235b-vl:latest" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Start the Skemi server: python Server.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "💡 Ollama will run on http://localhost:11434" -ForegroundColor Gray
Write-Host "💡 Skemi API will run on http://localhost:8010" -ForegroundColor Gray
