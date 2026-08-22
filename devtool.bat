@echo off
rem Developer verbs for proc_gen_temple.  devtool.sh carries the same verbs; keep them in step.
rem
rem   devtool setup        install the venv with the build group (poetry)
rem   devtool test [args]  pytest; args go to pytest (-k, paths, -x ...)
rem   devtool fuzz         the 150-seed union fuzz and every range edge
rem   devtool lint         ruff over the package, tests and tools
rem   devtool check        lint then test: the pre-push gate
rem   devtool run [args]   the editor
rem   devtool export ...   the headless command (mandapa ...)
rem   devtool shot NAME    render examples\NAME.xml to out\NAME.png
rem   devtool icons        draw build\icons\mandapa.{ico,icns,png} from the app's own icon
rem   devtool licenses     fetch the LGPL-3.0 and GPL-3.0 texts into licenses\ (commit them)
rem   devtool build        icons, then the PyInstaller folder, then the smoke test
rem   devtool smoke        smoke-test an existing dist\proc_gen_temple
rem   devtool clean        remove build\ and dist\
setlocal
cd /d "%~dp0"

set "verb=%~1"
if "%verb%"=="" set "verb=help"
set "arg1=%~2"
rem everything after the verb is passed through as-is; shift /1 leaves %0 (this file) alone,
rem which the call "%~f0" verbs below depend on
set "rest="
shift /1
:collect
if "%~1"=="" goto dispatch
set "rest=%rest% %1"
shift /1
goto collect

:dispatch
if /i "%verb%"=="setup"    goto setup
if /i "%verb%"=="test"     goto test
if /i "%verb%"=="fuzz"     goto fuzz
if /i "%verb%"=="lint"     goto lint
if /i "%verb%"=="check"    goto check
if /i "%verb%"=="run"      goto run
if /i "%verb%"=="export"   goto export
if /i "%verb%"=="shot"     goto shot
if /i "%verb%"=="icons"    goto icons
if /i "%verb%"=="licenses" goto licenses
if /i "%verb%"=="build"    goto build
if /i "%verb%"=="smoke"    goto smoke
if /i "%verb%"=="clean"    goto clean
if /i "%verb%"=="help"     goto help
if /i "%verb%"=="-h"       goto help
if /i "%verb%"=="--help"   goto help
echo unknown verb: %verb% 1>&2
call :help
exit /b 2

:setup
poetry install --with build %rest% && poetry env info --path
goto end

:test
poetry run pytest -q %rest%
goto end

:fuzz
if not defined MANDAPA_FUZZ set "MANDAPA_FUZZ=150"
poetry run pytest -q tests\test_builder.py -k "fuzz or edge" %rest%
goto end

:lint
poetry run ruff check mandapa tests tools %rest%
goto end

:check
call "%~f0" lint && call "%~f0" test
goto end

:run
poetry run temple-gen %rest%
goto end

:export
poetry run mandapa %rest%
goto end

:shot
if "%arg1%"=="" (
    echo usage: devtool shot EXAMPLE  ^(a stem from examples\^) 1>&2
    exit /b 2
)
if not exist out mkdir out
poetry run temple-gen --params "examples\%arg1%.xml" --screenshot "out\%arg1%.png" && echo out\%arg1%.png
goto end

:icons
poetry run python tools\make_icons.py
goto end

:licenses
if not exist licenses mkdir licenses
curl -fsSL https://www.gnu.org/licenses/lgpl-3.0.txt -o licenses\LGPL-3.0.txt && curl -fsSL https://www.gnu.org/licenses/gpl-3.0.txt -o licenses\GPL-3.0.txt && echo licenses\LGPL-3.0.txt and licenses\GPL-3.0.txt written; commit them
goto end

:build
call "%~f0" icons && poetry run pyinstaller proc_gen_temple.spec --noconfirm --clean %rest% && call "%~f0" smoke
goto end

:smoke
poetry run python tools\smoke_dist.py %rest%
goto end

:clean
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
goto end

:help
for /f "tokens=1,* delims= " %%a in ('findstr /b /c:"rem   devtool" "%~f0"') do echo   %%b
exit /b 0

:end
exit /b %errorlevel%
