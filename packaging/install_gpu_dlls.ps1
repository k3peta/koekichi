# KoeKichi GPU セットアップ: NVIDIA CUDA ランタイム DLL を PyPI からダウンロードして展開します。
# Python / pip のインストールは不要です。
$ErrorActionPreference = "Stop"

$destDir = Join-Path $env:LOCALAPPDATA "KoeKichi\cuda\bin"
New-Item -ItemType Directory -Force -Path $destDir | Out-Null

$wheels = @(
    @{ Name = "nvidia-cublas-cu12"; Url = "https://pypi.org/pypi/nvidia-cublas-cu12/json" },
    @{ Name = "nvidia-cudnn-cu12"; Url = "https://pypi.org/pypi/nvidia-cudnn-cu12/json" },
    @{ Name = "nvidia-cuda-nvrtc-cu12"; Url = "https://pypi.org/pypi/nvidia-cuda-nvrtc-cu12/json" }
)

$tempDir = Join-Path $env:TEMP "koekichi-gpu-setup"
New-Item -ItemType Directory -Force -Path $tempDir | Out-Null

Write-Host "KoeKichi GPU セットアップを開始します..."

foreach ($wheel in $wheels) {
    Write-Host "$($wheel.Name) の情報を取得しています..."
    try {
        $json = Invoke-RestMethod -Uri $wheel.Url -UseBasicParsing
        $releaseVersion = $json.info.version
        $files = $json.releases.$releaseVersion
        $target = $files | Where-Object { $_.filename -like "*win_amd64.whl" } | Select-Object -First 1
        if (-not $target) {
            Write-Warning "$($wheel.Name): win_amd64 ホイールが見つかりませんでした。スキップします。"
            continue
        }
        $whlPath = Join-Path $tempDir $target.filename
        Write-Host "$($wheel.Name) をダウンロードしています ($($target.filename))..."
        try {
            Start-BitsTransfer -Source $target.url -Destination $whlPath -Description "KoeKichi GPU DLL: $($wheel.Name)"
        } catch {
            Write-Host "BITS 転送に失敗したため Invoke-WebRequest で再試行します..."
            Invoke-WebRequest -Uri $target.url -OutFile $whlPath -UseBasicParsing
        }

        $extractDir = Join-Path $tempDir $wheel.Name
        Expand-Archive -Path $whlPath -DestinationPath $extractDir -Force

        $binDirs = Get-ChildItem -Path $extractDir -Recurse -Directory | Where-Object { $_.Name -eq "bin" }
        foreach ($bin in $binDirs) {
            Copy-Item -Path (Join-Path $bin.FullName "*") -Destination $destDir -Force -Recurse -ErrorAction SilentlyContinue
        }
        Write-Host "$($wheel.Name) の展開が完了しました。"
    } catch {
        Write-Warning "$($wheel.Name) の処理中にエラーが発生しました: $_"
    }
}

Remove-Item -Path $tempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host "KoeKichi GPU セットアップが完了しました。KoeKichi を再起動すると GPU が利用されます。"
