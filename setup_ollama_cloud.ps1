# Ollama Cloud Setup Script for Skemi
# This script sets up Ollama Cloud models

Write-Host "Setting up Skemi AI Models with Ollama Cloud..."

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

# Check available cloud models
Write-Host "🔍 Checking available cloud models..." -ForegroundColor Cyan

try {
    $response = Invoke-WebRequest -Uri "http://localhost:11434/api/tags" -TimeoutSec 10
    $models = ($response.Content | ConvertFrom-Json).models
    
    Write-Host "📊 Available Models:" -ForegroundColor Green
    foreach ($model in $models) {
        $modelName = $model.name
        if ($modelName -like "*cloud*") {
            Write-Host "  • $modelName (Cloud)" -ForegroundColor Cyan
        } else {
            Write-Host "  • $modelName (Local)" -ForegroundColor Gray
        }
    }
    
    # Check for required cloud models
    $requiredModels = @("gpt-oss:120b-cloud", "qwen3-coder:480b-cloud")
    $foundModels = @()
    
    foreach ($model in $models) {
        if ($model.name -in $requiredModels) {
            $foundModels += $model.name
        }
    }
    
    if ($foundModels.Count -eq $requiredModels.Count) {
        Write-Host "✅ All required cloud models are available!" -ForegroundColor Green
    } else {
        Write-Host "⚠️ Some required models are missing. Available: $($foundModels -join ', ')" -ForegroundColor Yellow
        Write-Host "💡 You can still use the available models, or pull additional ones with:" -ForegroundColor Gray
        Write-Host "   ollama pull <model-name>" -ForegroundColor Gray
    }
    
} catch {
    Write-Host "❌ Error checking models: $_" -ForegroundColor Red
}

Write-Host ""
Write-Host "🎉 Skemi AI Models Setup Complete!" -ForegroundColor Green
Write-Host ""
Write-Host "📊 Using Cloud Models:" -ForegroundColor Cyan
Write-Host "  • Chat: gpt-oss:120b-cloud" -ForegroundColor White
Write-Host "  • Vision: qwen3-coder:480b-cloud" -ForegroundColor White  
Write-Host "  • Analysis: gpt-oss:120b-cloud" -ForegroundColor White
Write-Host ""
Write-Host "🚀 Start the Skemi server: python Server.py" -ForegroundColor Yellow
Write-Host ""
Write-Host "💡 Ollama runs on http://localhost:11434" -ForegroundColor Gray
Write-Host "💡 Skemi API runs on http://localhost:8010" -ForegroundColor Gray
Write-Host "💡 Cloud models require internet connection" -ForegroundColor Gray
