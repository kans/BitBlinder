#!/usr/bin/python
#Copyright 2008 InnomiNet
"""A module with a bunch of random functions for building debian packages..."""
import os
import re
import sys
from time import gmtime, strftime

KEY_FILE = '/home/build/.ssh/innomikeypair.pem'
PACKAGE_DIR = "./releases/build"
ARCHIVE_DIR = "./releases/archive"

def syscall(cmd):
  if not os.system(cmd) == 0:
    raise Exception("%s did not finish cleanly" % (cmd))
    
def upload_file(fileName, remotePath):
  CWD = os.getcwd()
  os.chdir(ARCHIVE_DIR)
  syscall("scp -v -i %s %s root@174.129.199.15:%s/%s" % (KEY_FILE, fileName, remotePath, fileName))
  os.chdir(CWD)
  
def check_build_assumptions(BASE_NAME, VERSION, BUILD_DIR, CONTROL_FILE_TEXT, promptUser):
  if not check_changelog(BASE_NAME, VERSION, promptUser):
    print("Changelogs did not match!")
    sys.exit(473629)
  if not make_directory_structure(BUILD_DIR, CONTROL_FILE_TEXT):
    print("You are in the wrong directory!  Run from (something)/client/debian")
    sys.exit(386507)
    
def make_directory_structure(BUILD_DIR, CONTROL_FILE_TEXT):
  if not re.compile("^.*/debian$").match(os.getcwd()):
    return False
  if os.path.exists(PACKAGE_DIR):
    syscall("rm -rf %s" % (PACKAGE_DIR))
  for folder in (BUILD_DIR, ARCHIVE_DIR):
    if not os.path.exists(folder):
      os.makedirs(folder)
  syscall("rm -rf %s" % (BUILD_DIR))
  syscall("svn export --force ../ %s" % (BUILD_DIR))
  f = open("%s/debian/control" % (BUILD_DIR), "wb")
  f.write(CONTROL_FILE_TEXT)
  f.close()
  return True

def make_tar(TAR_NAME, BUILD_DIR, BASE_NAME, VERSION):
  syscall("tar cfz %s/%s %s" % (ARCHIVE_DIR, TAR_NAME, BUILD_DIR))
  syscall("cp %s/%s %s/%s_%s.orig.tar.gz" % (ARCHIVE_DIR, TAR_NAME, BUILD_DIR, BASE_NAME, VERSION))

def build(BUILD_DIR, DEB_NAME):
  CWD = os.getcwd()
  os.chdir(BUILD_DIR)
  syscall("debuild -k415C9DD2")
  os.chdir(CWD)
  syscall("mv %s/%s %s/" % (PACKAGE_DIR, DEB_NAME, ARCHIVE_DIR))
  
def create_changelog_entries(lines, name, version, writeVersionFile, fileName):
  print("What changes were made in this version?")
  print("(Enter a blank line to stop entering text)")
  newLines = []
  while True:
    line = raw_input()
    if not line:
      break
    line = "  * " + line.replace("\r", "")
    newLines.append(line)
  newLines.append("")
  fileLines = ["%s (%s) unstable; urgency=low" % (name, version), ""] + newLines + [" -- Matt Kaniaris <kans@bitblinder.com>  %s" % (strftime("%a, %d %b %Y %H:%M:%S +0000", gmtime())), ""] + lines
  f = open(fileName, "wb")
  f.write("\n".join(fileLines))
  f.close()
  if writeVersionFile:
    fileLines = ["%s" % (version), "", "b196d0018ee789e8cd96b7743626c7f1536de1321b0728b5053d74c9be51535d", "", "You must update to version %s" % (version), "", "%s FIXES:" % (version), ""] + newLines
    f = open("current_version.%s.txt" % (version), "wb")
    f.write("\n".join(fileLines))
    f.close()
    
def check_changelog(name, version, noInput, writeVersionFile=False, fileName="changelog"):
  #GENERATE BUILD FILES:
  #make sure changelog is up to date:
  versionRegex = re.compile("^%s \\((.+?\\..+?\\..+?)\\).*$" % (name))
  f = open(fileName, "rb")
  lines = f.readlines()
  f.close()
  for i in range(0, len(lines)):
    lines[i] = lines[i].replace("\n", "")
  m = versionRegex.match(lines[0])
  if not m or m.group(1) != version:
    print("Changelog has no entries for this version (%s)." % (version))
    if noInput:
      return True
    create_changelog_entries(lines, name, version, writeVersionFile, fileName)
    return True
  else:
    print("There are already changelog entries for this version.")
    if noInput:
      return True
    while len(lines) > 0:
      line = lines.pop(0)
      m = versionRegex.match(line)
      if m and m.group(1) != version:
        lines.insert(0, line)
        break
      print line
    print("Are these changes correct? (y/n) ")
    response = raw_input()
    if response.lower() not in ("y", "yes"):
      create_changelog_entries(lines, name, version, writeVersionFile)
    return True
      
