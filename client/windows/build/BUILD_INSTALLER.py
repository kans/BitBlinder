#!/usr/bin/python
#Copyright 2008 InnomiNet
import subprocess
import os
import shutil
import optparse

from common import Globals
from common.utils import Crypto

product_version=Globals.VERSION
versionDescription = '''There is no real need to update to version %s.
Changes:
* Fixed minor bug with welcome dialog
* Added survey to uninstaller
''' % (product_version)

DO_BUILD = True
DO_INSTALLER = True
DO_ARCHIVE = True
DO_UPLOAD = False
SURVEY_ADDRESS = Globals.BASE_HTTP + "/survey/detail/uninstalled/"

PARSER = optparse.OptionParser()
PARSER.add_option("--live", action="store_true", dest="isLive", default=False)
(options, args) = PARSER.parse_args()

if options.isLive:
  print("THIS IS THE LIVE NETWORK!  These files will not be uploaded to the live server.")
  DO_UPLOAD = False

if DO_BUILD:
  print('Building Executable')
  result = os.system("python setup.py py2exe")
  assert result == 0

  BUILD_DIR = "windows\\build"
  baseFolder = os.path.join(BUILD_DIR, "release")

  if os.path.exists(baseFolder):
    shutil.rmtree(baseFolder, True)
  if not os.path.exists(baseFolder):
    os.makedirs(baseFolder)
  copyCmd = "xcopy \"%s\" \"%s\" /S /Y" % (os.path.join(BUILD_DIR, "dist"), baseFolder)
  print copyCmd
  result = os.system(copyCmd)
  assert result == 0

#TODO:  this variable should not change like that
baseFolder = "release"
product_name = "BitBlinder"
mui_icon='..\\..\\data\\bb_favicon.ico'
mui_unicon="installer\\frowny_face.ico"
outfile="%sInstaller-%s.exe" % (product_name, product_version)

if options.isLive:
  REMOTE_URL = "/home/web/media/windows/"
  WINSCP_ADDRESS = "scp://root@bitblinder.com/"
else:
  REMOTE_URL = "/home/innominet/development/web/trunk/media/windows/"
  WINSCP_ADDRESS = "scp://innominet@64.245.185.132/"

if DO_INSTALLER:
  nsis = '''
  RequestExecutionLevel user
  !include "BitBlinder.nsh"
  !define UACSTR.I.ElvAbortReqAdmin "Windows User Access Control prevented BitBlinder from changing some of the settings you wanted (file handlers and program startup)" 
  !insertmacro BBCommon

  !define PRODUCT_VERSION "%s"
  Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
  OutFile "%s"

  !define PRODUCT_DIR_REGKEY "Software\Microsoft\Windows\CurrentVersion\App Paths\${PRODUCT_NAME}.exe"
  !define PRODUCT_UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${PRODUCT_NAME}"
  !define PRODUCT_UNINST_ROOT_KEY "HKLM"
  !define MUI_ABORTWARNING
  !define MUI_ICON "%s"
  !define MUI_UNICON "%s"

  InstallDirRegKey HKLM "${PRODUCT_DIR_REGKEY}" ""
  Var StartMenuFolder
  !include "MUI.nsh"

  Function ExecAppFile
    UAC::Exec '' '"$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt' '' ''
  FunctionEnd

  ; Welcome page
  !insertmacro MUI_PAGE_WELCOME
  ; License page
  !insertmacro MUI_PAGE_LICENSE "installer\LICENSE.txt"
  ; Directory page
  !insertmacro MUI_PAGE_DIRECTORY
  ;Do you want to start menu stuffs?
  !insertmacro MUI_PAGE_STARTMENU Application $StartMenuFolder
  ; Instfiles page
  !insertmacro MUI_PAGE_INSTFILES
  ; Finish page
  !define MUI_FINISHPAGE_RUN
  !define MUI_FINISHPAGE_RUN_TEXT "Launch BitBlinder"
  !define MUI_FINISHPAGE_RUN_FUNCTION "ExecAppFile"
  ; !define MUI_FINISHPAGE_RUN "$INSTDIR\${PRODUCT_NAME}.exe"
  !insertmacro MUI_PAGE_FINISH

  ; Uninstaller pages
  !insertmacro MUI_UNPAGE_INSTFILES

  ; Language files
  !insertmacro MUI_LANGUAGE "English"

  ; MUI end ------

  Function CreateShortcuts
    CreateShortCut "$DESKTOP\Private BitTorrent.lnk" "$INSTDIR\${PRODUCT_NAME}.exe" "--launch-bt" "$INSTDIR\data\\bb_favicon.ico"
    CreateShortCut "$DESKTOP\Private Browser.lnk" "$INSTDIR\${PRODUCT_NAME}.exe" "--launch-ff" "$INSTDIR\data\\bb_favicon.ico"
  FunctionEnd

  Function un.RemoveShortcuts
    RMDir /r "$APPDATA\.bitblinder\users"
    RMDir /r "$APPDATA\.bitblinder\logs"
    RMDir "$APPDATA\.bitblinder\torrentFolder"
    Delete "$APPDATA\.bitblinder\BitBlinderUpdate.exe"
    Delete "$APPDATA\.bitblinder\BitBlinderUpdate.exe.prev"
    Delete "$APPDATA\.bitblinder\BitBlinderUpdate.exe.download"
    RMDir "$APPDATA\.bitblinder"
    Delete "$DESKTOP\Private BitTorrent.lnk"
    Delete "$DESKTOP\Private Browser.lnk"
  FunctionEnd

  LangString ConfirmUninstall ${LANG_ENGLISH} "Are you sure you want to completely remove $(^Name) and all of its components?$\\r$\\n \\
  Warning, this will remove $INSTDIR and all files and folders in it, even those which have been added later."
    
  Function un.onInit
    ${UAC.I.Elevate.AdminOnly}
    MessageBox MB_ICONQUESTION|MB_YESNO|MB_DEFBUTTON2 $(ConfirmUninstall) IDYES +2
    Abort
  FunctionEnd

  Function un.onUninstSuccess
    ${UAC.Unload}
    HideWindow
    MessageBox MB_ICONINFORMATION|MB_OK "$(^Name) was successfully removed from your computer."
  FunctionEnd

  Function un.OnUninstFailed
    ${UAC.Unload}
  FunctionEnd

  !insertmacro GetOptions 
  Var textHandle
  !include "WinMessages.nsh"

  Function .onInit
    ${IfNot} ${Silent}
      StrCpy $INSTDIR "$PROGRAMFILES\${PRODUCT_NAME}"
    ${Else}
      ClearErrors
      ${GetOptions} $CMDLINE "--LOCATION=" $INSTDIR
      ${If} ${Errors}
        MessageBox MB_OK "Just restart BitBlinder, or if you are trying to install this manually, use the --LOCATION=(path) flag to tell the updater where your installation is."
        Quit
      ${EndIf}
      Banner::show /NOUNLOAD "Waiting for BitBlinder to shut down..."
      Banner::getWindow /NOUNLOAD
      Pop $1
      GetDlgItem $textHandle $1 1030
      ClearErrors
      ${GetOptions} $CMDLINE "--PID=" $value
      ${Unless} ${Errors}
        ;MessageBox MB_OK 'We would be calling this:  "$INSTDIR\${PRODUCT_NAME}.exe" --WAIT_FOR_PROCESS $value'
        ExecWait '"$INSTDIR\${PRODUCT_NAME}.exe" --WAIT_FOR_PROCESS $value'
      ${EndIf}
    ${EndIf}
    ${UAC.I.Elevate.AdminOnly}
  FunctionEnd
    
  Function .onInstSuccess
    ${If} ${Silent}
      Banner::destroy
      UAC::Exec '' '"$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt --FINISHED_UPDATE' '' ''
    ${EndIf}
    ${UAC.Unload}
  FunctionEnd

  Function .onInstFailed
    ${If} ${Silent}
      Banner::destroy
      UAC::Exec '' '"$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt --FINISHED_UPDATE' '' ''
    ${EndIf}
    ${UAC.Unload}
  FunctionEnd
    
  InstallDir "$INSTDIR"
  ShowInstDetails show
  ShowUnInstDetails show 
  Section "MainSection" SEC01
    SetOverwrite on 
    SetOutPath "$INSTDIR"
    ${If} ${Silent}
      SendMessage $textHandle ${WM_SETTEXT} 0 "STR:Updating BitBlinder..."
      ;MessageBox MB_OK "Dumping my files to $INSTDIR"
      ;Without this line, stupid NSIS doesnt ACTUALLY wait for the other process to FULLY finish, which means we cant update the exe  :(
      Sleep 5000
    ${EndIf}
    File /r %s\*.*
    ;#TODO:  fix this, not really sure the best way.  Portable installs of the whole thing are really what we want...
    AccessControl::EnableFileInheritance "$INSTDIR\\apps\FirefoxPortable"
    AccessControl::GrantOnFile "$INSTDIR\\apps\FirefoxPortable" "(BU)" "GenericRead + GenericWrite"
    
    ;add exceptions to the windows firewall:
    nsisFirewall::AddAuthorizedApplication "$INSTDIR\${PRODUCT_NAME}.exe" "${PRODUCT_NAME}"
    Pop $0
    ${IfNot} $0 = 0
      MessageBox MB_OK "An error happened while adding ${PRODUCT_NAME}.exe to Firewall exception list (result=$0)"
    ${EndIf}
    nsisFirewall::AddAuthorizedApplication "$INSTDIR\Tor.exe" "Custom Tor (for BitBlinder)"
    Pop $0
    ${IfNot} $0 = 0
      MessageBox MB_OK "An error happened while adding Tor.exe to Firewall exception list (result=$0)"
    ${EndIf}
    
    ${IfNot} ${Silent}
      !insertmacro MUI_STARTMENU_WRITE_BEGIN Application
        CreateDirectory "$SMPROGRAMS\${PRODUCT_NAME}"
        CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Website.lnk" "$INSTDIR\Visit Website.url"
        CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Private BitTorrent.lnk" "$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt
        CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Private Browser.lnk" "$INSTDIR\${PRODUCT_NAME}.exe" --launch-ff
        CreateShortCut "$SMPROGRAMS\${PRODUCT_NAME}\Uninstall.lnk" "$INSTDIR\Uninstall.exe"
        GetFunctionAddress $0 CreateShortcuts
        UAC::ExecCodeSegment $0
      !insertmacro MUI_STARTMENU_WRITE_END
    ${EndIf}
  SectionEnd

  Section -Post
    ${IfNot} ${Silent}
      ;MessageBox MB_OK "$INSTDIR is where we put stuff"
      WriteUninstaller "$INSTDIR\Uninstall.exe"
      WriteRegStr HKLM "${PRODUCT_DIR_REGKEY}" "" "$INSTDIR\${PRODUCT_NAME}.exe"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayName" "${PRODUCT_NAME}"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "UninstallString" "$INSTDIR\Uninstall.exe"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayIcon" "$INSTDIR\${PRODUCT_NAME}.exe"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "DisplayVersion" "${PRODUCT_VERSION}"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "URLInfoAbout" "${PRODUCT_WEB_SITE}"
      WriteRegStr ${PRODUCT_UNINST_ROOT_KEY} "${PRODUCT_UNINST_KEY}" "Publisher" "${PRODUCT_PUBLISHER}"
    ${EndIf}
  SectionEnd

  Section Uninstall
    ;MessageBox MB_OK "$INSTDIR is where stuff is stored?"
    RMDir /r $INSTDIR
    RMDir /r "$SMPROGRAMS\${PRODUCT_NAME}"
    GetFunctionAddress $0 un.RemoveShortcuts
    UAC::ExecCodeSegment $0
    !insertmacro removeStartupKey
    !insertmacro removeTorrentKey
    
    ;remove exceptions to the windows firewall:
    nsisFirewall::RemoveAuthorizedApplication "$INSTDIR\${PRODUCT_NAME}.exe"
    Pop $0
    ${IfNot} $0 = 0
      MessageBox MB_OK "An error happened while removing program to Firewall exception list (result=$0)"
    ${EndIf}
    nsisFirewall::RemoveAuthorizedApplication "$INSTDIR\Tor.exe"
    Pop $0
    ${IfNot} $0 = 0
      MessageBox MB_OK "An error happened while removing program to Firewall exception list (result=$0)"
    ${EndIf}
    
    ;ask them to fill out a survey for us:
    ExecShell "open" "%s"
    
  SectionEnd
  ''' % (product_version, outfile, mui_icon, mui_unicon, baseFolder, SURVEY_ADDRESS)

  file=open(os.path.join(BUILD_DIR, "installer.nsi"),'w')
  file.write(nsis)
  file.close()

  print('Building Installer')
  #os.chdir('windows\\build')
  p = subprocess.Popen('makensis.exe installer.nsi', stdout=subprocess.PIPE, shell=True, cwd=BUILD_DIR)
  print p.communicate()[0]
  exitStat = p.wait()
  assert exitStat == 0

  print("Creating current_version.txt")
  fileHash = Crypto.hash_file_data(os.path.join(BUILD_DIR, outfile))
  f = open(os.path.join(BUILD_DIR, "releases", "current_version.txt"), "wb")
  f.write(Globals.VERSION + "\n\n")
  f.write(fileHash + "\n\n")
  f.write(versionDescription)
  f.close()

if DO_ARCHIVE:
  #archive the build:
  print("Archiving release")
  archiveLocation = os.path.join(BUILD_DIR, "releases", product_version)
  if os.path.exists(archiveLocation):
    shutil.rmtree(archiveLocation, True)
  shutil.move(os.path.join(BUILD_DIR, "release"), archiveLocation)
  archiveBuild = os.path.join(BUILD_DIR, "releases", outfile)
  if os.path.exists(archiveBuild):
    os.remove(archiveBuild)
  shutil.move(os.path.join(BUILD_DIR, outfile), archiveBuild)
  versionFile = os.path.join(BUILD_DIR, "releases", product_version+".txt")
  if os.path.exists(versionFile):
    os.remove(versionFile)
  shutil.copy(os.path.join(BUILD_DIR, "releases", "current_version.txt"), versionFile)

if DO_UPLOAD:
  print("uploading")
  for file in (outfile, "current_version.txt"):
    p = subprocess.Popen(['C:\\Program Files\\winscp\\winscp418.exe', "/console", "/command", "open %s" % (WINSCP_ADDRESS), "put %s\\%s %s" % (os.getcwdu(), os.path.join(BUILD_DIR, "releases", file), REMOTE_URL + file), "exit"], cwd="C:\\Program Files\\winscp")
    x = p.wait()
    assert x == 0
    
print("all done")
