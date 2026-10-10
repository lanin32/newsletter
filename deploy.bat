@echo off
setlocal
cd /d "%~dp0"

rem ---------------------------------------------------------------------
rem One-command deploy for the crypto newsletter bot (run from cmd.exe).
rem
rem   deploy.bat            check, then build + push the image
rem   deploy.bat weekly     ...then run the weekly job once
rem   deploy.bat monthly    ...then run the monthly job once
rem   deploy.bat both       ...then run weekly, then monthly
rem
rem Running a job sends a real email and spends real API credits, so it
rem only happens when you ask for it. One image serves both jobs, and Cloud
rem Run Jobs pick up the new image on their next run, so no job update is
rem needed after a build.
rem ---------------------------------------------------------------------

set PROJECT=crypto-newsletter-503220
set REGION=europe-west1
set IMAGE=europe-west1-docker.pkg.dev/crypto-newsletter-503220/crypto-newsletter/weekly-job

set TARGET=%~1
if "%TARGET%"=="" goto :preflight
if /i "%TARGET%"=="weekly" goto :preflight
if /i "%TARGET%"=="monthly" goto :preflight
if /i "%TARGET%"=="both" goto :preflight
echo Unknown option "%TARGET%". Use: deploy.bat [weekly, monthly or both]
exit /b 1

:preflight
where gcloud >nul 2>nul
if errorlevel 1 (
  echo gcloud was not found on PATH. Install the Google Cloud CLI first.
  exit /b 1
)

echo [1/3] Checking config.yaml and Python syntax...
python -c "import ast,glob,yaml; yaml.safe_load(open('config.yaml',encoding='utf-8-sig')); [ast.parse(open(f,encoding='utf-8-sig').read()) for f in glob.glob('*.py')]"
if errorlevel 1 (
  echo.
  echo Pre-flight check failed. Fix the error above; nothing was deployed.
  exit /b 1
)

echo.
echo [2/3] Building and pushing the image...
call gcloud builds submit --project=%PROJECT% --tag %IMAGE% .
if errorlevel 1 (
  echo.
  echo Build failed. The deployed jobs still run the previous image.
  exit /b 1
)

echo.
echo [3/3] Image pushed. Scheduled runs will use it from now on.

if /i "%TARGET%"=="weekly" call :run crypto-weekly-job
if /i "%TARGET%"=="monthly" call :run crypto-monthly-job
if /i "%TARGET%"=="both" call :run crypto-weekly-job
if /i "%TARGET%"=="both" if not errorlevel 1 call :run crypto-monthly-job
if errorlevel 1 exit /b 1

echo.
echo Done.
exit /b 0

:run
echo.
echo Running %~1 now. This sends a real email and spends real API credits.
call gcloud run jobs execute %~1 --project=%PROJECT% --region=%REGION% --wait
if errorlevel 1 (
  echo.
  echo %~1 failed. Check its logs in the Cloud Run console.
  exit /b 1
)
exit /b 0
