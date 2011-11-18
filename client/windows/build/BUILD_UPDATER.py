#!/usr/bin/python
#Copyright 2008 InnomiNet
import subprocess
import os
import shutil
from common import Globals
from common.utils import Crypto

REMOTE_FILE_NAME = "/home/web/media/windows/releases/BitBlinderUpdate-%s.exe" % (Globals.VERSION)
LOCAL_FILE_NAME = "BitBlinder.exe"
WINSCP_ADDRESS = "scp://root@bitblinder.com/"

##TODO:  this code works, actually start using it
#import os
#from os.path import join, getsize
#
#OLD_VERSION = "0.3.0"
#NEW_VERSION = "0.3.1"
#BASE_PATH = "windows\\build"
#os.chdir(BASE_PATH)
#
#def missing_files(dir1, dir2):
#  missingDirs = []
#  missingFiles = []
#  os.chdir(dir1)
#  otherFolder = "..\\%s" % (dir2)
#  for root, dirs, files in os.walk(''):
#    if not os.path.exists(os.path.join(otherFolder, root)):
#      print root
#      missingDirs.append(root)
#    for file in files:
#      if not os.path.exists(os.path.join(otherFolder, root, file)):
#        name = "%s\\%s" % (root, file)
#        print name
#        missingFiles.append(name)
#  os.chdir("..")
#  return missingDirs, missingFiles
#  
#def changed_files(dir1, dir2):
#  os.chdir(dir1)
#  modifiedFiles = []
#  otherFolder = "..\\%s" % (dir2)
#  for root, dirs, files in os.walk(''):
#    if not os.path.exists(os.path.join(otherFolder, root)):
#      continue
#    for file in files:
#      otherFile = os.path.join(otherFolder, root, file)
#      thisFile = os.path.join(root, file)
#      if os.path.exists(otherFile):
#        #are they the same size?
#        if getsize(thisFile) != getsize(otherFile):
#          print "%s sizes differ" % (thisFile)
#          modifiedFiles.append(thisFile)
#        else:
#          #bleh, have to read and compare:
#          f1 = open(thisFile, "rb")
#          f2 = open(otherFile, "rb")
#          if f1.read() != f2.read():
#            print "%s contents differ" % (thisFile)
#            modifiedFiles.append(thisFile)
#          f1.close()
#          f2.close()
#  os.chdir("..")
#
#print "Removed:"
#removedDirs, removedFiles = missing_files(OLD_VERSION, NEW_VERSION)
#print "Added:"
#addedDirs, addedFiles = missing_files(NEW_VERSION, OLD_VERSION)
#print "Changed:"
#changedFiles = changed_files(NEW_VERSION, OLD_VERSION)
#addedFiles += changedFiles
#
##clear the update folder:
#updateFolder = "update"
#if os.path.exists(updateFolder):
#  shutil.rmtree(updateFolder, True)
#if not os.path.exists(updateFolder):
#  os.makedirs(updateFolder)
##move the added and changed files to the update folder:
#for folder in addedDirs:
#  os.makedirs(os.path.join(updateFolder, folder))
#for file in addedFiles:
#  shutil.copy(os.path.join(NEW_VERSION, file), os.path.join(updateFolder, file))
##make the list of files and folder to delete:
#fileDeleteList = ""
#for file in removedFiles:
#  fileDeleteList += "  Delete %s\n"
#folderDeleteList = ""
#for file in removedDirs:
#  folderDeleteList += "  RMDir %s\n"

baseFolder = "update"
product_version=Globals.VERSION
product_name = "BitBlinder"
mui_icon='..\\..\\data\\bb_favicon.ico'
outfile = "%sUpdate-%s.exe"%(product_name, product_version)

versionDescription = '''You must update to version %s.
Changes:
* Fixed some bugs
* Added some features
* Many more...
''' % (product_version)

nsis = '''
!include "BitBlinder.nsh"
!define UACSTR.I.ElvAbortReqAdmin "BitBlinder Updater requires Admin priveleges to properly update your version of BitBlinder" 
!insertmacro BBCommon
!insertmacro GetOptions 
Var textHandle

!include "WinMessages.nsh"

!define PRODUCT_VERSION "%s"

Function .onInit
  ${UAC.I.Elevate.AdminOnly}
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
FunctionEnd

Name "${PRODUCT_NAME} ${PRODUCT_VERSION}"
OutFile "%s"
InstallDir "$INSTDIR"

ShowInstDetails show

Section "MainSection" SEC01
  SendMessage $textHandle ${WM_SETTEXT} 0 "STR:Updating BitBlinder..."
  SetOverwrite try 
  SetOutPath "$INSTDIR"
  File /r %s\*.*
SectionEnd

Function .onInstSuccess
  Banner::destroy
  ${UAC.Unload}
  UAC::Exec '' '"$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt --FINISHED_UPDATE' '' ''
FunctionEnd

Function .onInstFailed
  Banner::destroy
  ${UAC.Unload}
  UAC::Exec '' '"$INSTDIR\${PRODUCT_NAME}.exe" --launch-bt --FINISHED_UPDATE' '' ''
FunctionEnd
''' % (product_version, outfile, baseFolder)

file=open('windows\\build\\updater.nsi','w')
file.write(nsis)
file.close()

print('Building Installer')
p = subprocess.Popen('"C:\\Program Files\\NSIS\\makensis.exe" updater.nsi', stdout=subprocess.PIPE, shell=True, cwd='windows\\build')
print p.communicate()[0]
exitStat = p.wait()

print("Creating current_version.txt")
fileHash = Crypto.hash_file_data("windows\\build\\%s" % (outfile))
f = open("windows\\build\\current_version.txt", "wb")
f.write(Globals.VERSION + "\n\n")
f.write(fileHash + "\n\n")
f.write(versionDescription)
f.close()

print("uploading")
#p = subprocess.Popen(['C:\\Program Files\\winscp\\winscp418.exe', "/console", "/command", "open %s" % (WINSCP_ADDRESS), "put %s\\%s %s" % (os.getcwdu(), LOCAL_FILE_NAME, REMOTE_FILE_NAME), "exit"], cwd="C:\\Program Files\\winscp")
#x = p.wait()
print("all done")
