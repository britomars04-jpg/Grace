# Complete Android SDK setup script
$ErrorActionPreference = "Stop"

Write-Host "Setting up Android SDK for Flutter..." -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan

# 1. Create Android SDK directory
$androidHome = "$env:USERPROFILE\Android\Sdk"
Write-Host "`n1. Creating Android SDK directory..." -ForegroundColor Yellow
if (!(Test-Path $androidHome)) {
    New-Item -ItemType Directory -Force -Path $androidHome | Out-Null
    Write-Host "   Created: $androidHome" -ForegroundColor Green
} else {
    Write-Host "   Already exists: $androidHome" -ForegroundColor Green
}

# 2. Download Android command-line tools
Write-Host "`n2. Downloading Android command-line tools..." -ForegroundColor Yellow
$cmdlineToolsDir = "$androidHome\cmdline-tools\latest"
if (!(Test-Path $cmdlineToolsDir)) {
    $url = "https://dl.google.com/android/repository/commandlinetools-win-15859902_latest.zip"
    $tempZip = "$env:TEMP\commandlinetools.zip"

    Write-Host "   Downloading from: $url" -ForegroundColor Cyan
    try {
        Invoke-WebRequest -Uri $url -OutFile $tempZip -UseBasicParsing
        Write-Host "   Downloaded to: $tempZip" -ForegroundColor Green

        # Extract using Python (more reliable than Expand-Archive for large files)
        $extractDir = "$env:TEMP\cmdline-tools-extract"
        if (Test-Path $extractDir) {
            Remove-Item $extractDir -Recurse -Force
        }
        New-Item -ItemType Directory -Force -Path $extractDir | Out-Null

        Write-Host "   Extracting..." -ForegroundColor Cyan
        python -c "
import zipfile, os
zip_path = r'$tempZip'
extract_dir = r'$extractDir'
with zipfile.ZipFile(zip_path, 'r') as zf:
    zf.extractall(extract_dir)
print('Extraction complete')
"

        # Move to correct location
        if (!(Test-Path "$androidHome\cmdline-tools")) {
            New-Item -ItemType Directory -Force -Path "$androidHome\cmdline-tools" | Out-Null
        }
        if (Test-Path $cmdlineToolsDir) {
            Remove-Item $cmdlineToolsDir -Recurse -Force
        }
        Copy-Item -Path "$extractDir\cmdline-tools" -Destination $cmdlineToolsDir -Recurse -Force

        Write-Host "   Installed to: $cmdlineToolsDir" -ForegroundColor Green
    } catch {
        Write-Host "   ERROR: Failed to download command-line tools" -ForegroundColor Red
        Write-Host "   $($_.Exception.Message)" -ForegroundColor Red
    }
} else {
    Write-Host "   Already installed: $cmdlineToolsDir" -ForegroundColor Green
}

# 3. Set environment variables
Write-Host "`n3. Setting environment variables..." -ForegroundColor Yellow
[Environment]::SetEnvironmentVariable("ANDROID_HOME", $androidHome, "User")
$env:ANDROID_HOME = $androidHome
Write-Host "   ANDROID_HOME = $androidHome" -ForegroundColor Green

# 4. Add to PATH
Write-Host "`n4. Updating PATH..." -ForegroundColor Yellow
$currentPath = [Environment]::GetEnvironmentVariable("PATH", "User")
$pathAdditions = @(
    "$androidHome\platform-tools",
    "$androidHome\cmdline-tools\latest\bin",
    "$androidHome\emulator"
)

foreach ($pathDir in $pathAdditions) {
    if ($currentPath -notlike "*$pathDir*") {
        $currentPath += ";$pathDir"
    }
}
[Environment]::SetEnvironmentVariable("PATH", $currentPath, "User")
$env:PATH += ";$androidHome\platform-tools;$androidHome\cmdline-tools\latest\bin"
Write-Host "   PATH updated" -ForegroundColor Green

# 5. Install platform-tools and SDK platforms if needed
Write-Host "`n5. Installing Android SDK components..." -ForegroundColor Yellow
$sdkmanager = "$androidHome\cmdline-tools\latest\bin\sdkmanager.bat"
$env:JAVA_HOME = "C:\Program Files\Android\Android Studio\jbr"
$env:SKIP_JDK_VERSION_CHECK = "1"

if (Test-Path $sdkmanager) {
    try {
        Write-Host "   Installing platform-tools..." -ForegroundColor Cyan
        echo y | & $sdkmanager --sdk_root=$androidHome --install "platform-tools" 2>&1 | Out-Null
        Write-Host "   Platform-tools installed" -ForegroundColor Green

        Write-Host "   Installing Android platform..." -ForegroundColor Cyan
        echo y | & $sdkmanager --sdk_root=$androidHome --install "platforms;android-36" 2>&1 | Out-Null
        Write-Host "   Android platform installed" -ForegroundColor Green

        Write-Host "   Installing build-tools..." -ForegroundColor Cyan
        echo y | & $sdkmanager --sdk_root=$androidHome --install "build-tools;36.0.0" 2>&1 | Out-Null
        Write-Host "   Build-tools installed" -ForegroundColor Green
    } catch {
        Write-Host "   WARNING: Could not install SDK components" -ForegroundColor Yellow
    }
} else {
    Write-Host "   sdkmanager not found at $sdkmanager" -ForegroundColor Red
}

# 6. Accept Android licenses
Write-Host "`n6. Accepting Android SDK licenses..." -ForegroundColor Yellow
$licenseDir = "$androidHome\licenses"
if (!(Test-Path $licenseDir)) {
    New-Item -ItemType Directory -Force -Path $licenseDir | Out-Null
}

try {
    if (Test-Path $sdkmanager) {
        Write-Host "   Accepting all licenses..." -ForegroundColor Cyan
        $inputStr = "y`n" * 10
        & $sdkmanager --sdk_root=$androidHome --licenses <<< $inputStr 2>&1 | Out-Null

        # Create license files as fallback
        $licenseContent = "1"
        $licenses = @(
            "android-sdk-license",
            "android-sdk-license-cml",
            "maven-sources-license",
            "google-license",
            "google-donors-license",
            "google-googleservices-license"
        )

        foreach ($license in $licenses) {
            Set-Content -Path "$licenseDir\$license" -Value $licenseContent -Force
        }
        Write-Host "   Licenses accepted" -ForegroundColor Green
    }
} catch {
    Write-Host "   WARNING: Could not accept licenses automatically" -ForegroundColor Yellow
    Write-Host "   Run this manually: flutter doctor --android-licenses" -ForegroundColor Yellow
}

Write-Host "`n=========================================" -ForegroundColor Cyan
Write-Host "Android SDK setup complete!" -ForegroundColor Green
Write-Host "=========================================" -ForegroundColor Cyan

Write-Host "`nNext steps:" -ForegroundColor Yellow
Write-Host "1. Restart your terminal/PowerShell" -ForegroundColor White
Write-Host "2. Run: flutter doctor" -ForegroundColor White
Write-Host "3. Verify Android toolchain shows [OK]" -ForegroundColor White

Write-Host "`nANDROID_HOME is now set to:" -ForegroundColor Yellow
Write-Host $androidHome -ForegroundColor Green