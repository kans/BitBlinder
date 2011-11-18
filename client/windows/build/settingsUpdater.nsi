!include "BitBlinder.nsh"
!define UACSTR.I.ElvAbortReqAdmin "Windows User Access Control prevented BitBlinder from changing some of the settings you wanted (file handlers and program startup)" 
!insertmacro BBCommon
!insertmacro UACCommon
!insertmacro GetOptions 

OutFile "..\bin\${PRODUCT_NAME}SettingsUpdate.exe"

Function addStartupKeyFunc
  !insertmacro addStartupKey
FunctionEnd

Function removeStartupKeyFunc
  !insertmacro removeStartupKey
FunctionEnd

Function addTorrentKeyFunc
  !insertmacro addTorrentKey
FunctionEnd

Function removeTorrentKeyFunc
  !insertmacro removeTorrentKey
FunctionEnd

Section
  ClearErrors
  ${GetOptions} $CMDLINE "--add-startup=" $value
	IfErrors +2
    Call addStartupKeyFunc
  ClearErrors
  ${GetOptions} $CMDLINE "--remove-startup" $value
	IfErrors +2
    Call removeStartupKeyFunc
  ClearErrors
  ${GetOptions} $CMDLINE "--add-torrent=" $value
  IfErrors +2
    Call addTorrentKeyFunc
  ClearErrors
  ${GetOptions} $CMDLINE "--remove-torrent" $value
	IfErrors +2
    Call removeTorrentKeyFunc
  Quit
SectionEnd