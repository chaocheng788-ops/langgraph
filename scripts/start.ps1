Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  LangGraph 可视化编排平台" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$venvPath = Join-Path $PSScriptRoot "..\venv\Scripts\Activate.ps1"
$mainPy = Join-Path $PSScriptRoot "..\main.py"

if (-not (Test-Path $venvPath)) {
    Write-Host "[错误] 虚拟环境不存在，请先运行 setup.ps1" -ForegroundColor Red
    exit 1
}

# Activate venv
& $venvPath

Write-Host "[信息] 启动服务..." -ForegroundColor Green
Write-Host "[信息] API 文档: http://localhost:8765/docs" -ForegroundColor Yellow
Write-Host "[信息] 可视化界面: http://localhost:8765" -ForegroundColor Yellow
Write-Host ""

python $mainPy
