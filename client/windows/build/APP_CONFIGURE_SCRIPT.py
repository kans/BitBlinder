#!/usr/bin/env python

#HOW TO USE:
#1.  Install firefoxportable to \apps_clean
#2.  Unzip my custom Deluge (also from the dependencies svn folder) to \apps_clean
#3.  Run this script.  It should generate the \apps folder, with all the proper modifications to the apps to make
#    them work through Tor.

#NOTE:  DO NOT HAVE FIREFOX RUNNING WHILE YOU RUN THIS SCRIPT, IT WONT WORK
#NOTE:  these modification are based on the trunk of torbrowser (r16696)
#NOTE:  change FirefoxPortableSettings.ini to contain AllowMultipleInstances=True
#so that it can be launched independently, pew pew

import os
import sys
import shutil
import traceback

def copy_file(fromFile, toFile):
  try:
    shutil.copy(fromFile, toFile)
  except:
    traceback.print_exception(*sys.exc_info())
    return False
  return True

#def copy_files(files, dest):
#  for file in files:
#    copy_file("torbrowser\\build-scripts\\config\\" + file, dest + "\\" + file)
#

#print("Removing existing folder...")
##remove any previous app folder (dont worry about errors, like it not existing)
#shutil.rmtree("apps", True)
##copy the clean apps folder, ignoring svn and stuff
##IGNORE_PATTERNS = ('^.git','.svn')
#print("Copying apps_clean folder...  (this can take quite a while)")
##NOTE:   argh, only works in 2.6
##shutil.copytree("apps_clean", "apps", ignore=shutil.ignore_patterns(IGNORE_PATTERNS))
#shutil.copytree("apps_clean", "apps")

##copy over pidgin settings:
#PIDGIN_PORTABLE_LOC = "apps\\PidginPortable"
#if not os.path.exists(PIDGIN_PORTABLE_LOC + "\\Data\\settings\\.purple"):
#  os.makedirs(PIDGIN_PORTABLE_LOC + "\\Data\\settings\\.purple")
#copy_files(["PidginPortable.ini"], PIDGIN_PORTABLE_LOC)
#copy_files(["PidginPortableSettings.ini", "prefs.xml"], PIDGIN_PORTABLE_LOC + "\\Data\\settings\\.purple")

#copy over firefox settings:
FF_PORTABLE_LOC = "apps\\FirefoxPortable"
#copy_files(["prefs.js", "bookmarks.html"], FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
#copy_files(["FirefoxPortableSettings.ini", "FirefoxPortable.ini"], FF_PORTABLE_LOC)
copy_file("apps\\prefs.js", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
copy_file("apps\\bookmarks.html", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
copy_file("apps\\localstore.rdf", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
copy_file("apps\\polipo.exe", FF_PORTABLE_LOC)
copy_file("apps\\polipo.conf", FF_PORTABLE_LOC)
copy_file("apps\\libgnurx-0.dll", FF_PORTABLE_LOC)

#C:\Projects\web\innominet\apps\FirefoxPortable\Data\profile
#FirefoxPortable\App\DefaultData\profile
copy_file("apps\\cert_override.txt", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
copy_file("apps\\cert8.db", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")
copy_file("apps\\key3.db", FF_PORTABLE_LOC + "\\App\\DefaultData\\profile")

#create dummy profile:
DUMMY_PROFILE = FF_PORTABLE_LOC + "\\App\\DummyProfile"
shutil.copytree(FF_PORTABLE_LOC + "\\App\\DefaultData", DUMMY_PROFILE)
#install FF extensions globally:
cmd = "%s\\App\\Firefox\\firefox.exe -profile %s\\profile -install-global-extension apps\\torbutton-1.2.1.xpi" % (FF_PORTABLE_LOC, DUMMY_PROFILE)
temp = os.system(cmd)
print temp
#remove dummy profile:
shutil.rmtree(DUMMY_PROFILE, True)

#overwrite the default prefs:
copy_file("apps\\torbutton_prefs.js", FF_PORTABLE_LOC + "\\App\\Firefox\\extensions\\{e0204bd5-9d31-402b-a99d-a6aa8ffebdca}\\defaults\\preferences\\preferences.js")
if not os.path.exists(FF_PORTABLE_LOC + "\\Data\\settings"):
  os.mkdir(FF_PORTABLE_LOC + "\\Data\\settings")
copy_file("apps\\FirefoxPortableSettings.ini", FF_PORTABLE_LOC + "\\Data\\settings")
copy_file("apps\\FirefoxPortable.ini.base", FF_PORTABLE_LOC)
copy_file("apps\\FirefoxPortable.ini.base", FF_PORTABLE_LOC + "\\FirefoxPortable.ini")
