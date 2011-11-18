@echo off
set PATH=%CD%;%PATH%;
set FOLDER=%CD%
"%CD%\BitBlinder.exe" "--WAIT_FOR_PROCESS" "%1" & 
"%CD%\newVersion.exe" "-o." "-y" & 
"%CD%\BitBlinder.exe" "--FINISHED_UPDATE" "--launch-bt"
