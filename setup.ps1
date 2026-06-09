# LangGraph 平台安装脚本
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  LangGraph 可视化编排平台 - 安装" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# Check Python
$pythonVersion = python --version 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 未找到 Python，请安装 Python 3.10+" -ForegroundColor Red
    exit 1
}
Write-Host "[✓] $pythonVersion" -ForegroundColor Green

$projectRoot = $PSScriptRoot
$venvPath = Join-Path $projectRoot "venv"

# Create virtual environment
Write-Host "[信息] 创建虚拟环境..." -ForegroundColor Yellow
python -m venv $venvPath
if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 创建虚拟环境失败" -ForegroundColor Red
    exit 1
}
Write-Host "[✓] 虚拟环境已创建" -ForegroundColor Green

# Activate and install packages
$pip = Join-Path $venvPath "Scripts\pip.exe"
$python = Join-Path $venvPath "Scripts\python.exe"

Write-Host "[信息] 安装依赖包 (可能需要几分钟)..." -ForegroundColor Yellow
& $pip install --upgrade pip

& $pip install langgraph langgraph-cli langgraph-sdk fastapi uvicorn pyyaml jinja2 pydantic python-multipart httpx sse-starlette

if ($LASTEXITCODE -ne 0) {
    Write-Host "[错误] 安装依赖失败" -ForegroundColor Red
    exit 1
}
Write-Host "[✓] 依赖安装完成" -ForegroundColor Green

# Create directories
$dirs = @("workflows", "configs", "frontend", "scripts")
foreach ($dir in $dirs) {
    $path = Join-Path $projectRoot $dir
    if (-not (Test-Path $path)) {
        New-Item -ItemType Directory -Path $path -Force | Out-Null
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  安装完成!" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "启动服务: .\scripts\start.ps1" -ForegroundColor Yellow
Write-Host "或: .\scripts\start.bat" -ForegroundColor Yellow
Write-Host ""
Write-Host "访问地址: http://localhost:8765" -ForegroundColor Green
Write-Host "API 文档: http://localhost:8765/docs" -ForegroundColor Green
