#!/usr/bin/python
import os
import sys
import re
import signal
import subprocess

from common import Globals
from common.system import System
from common.system import Files

if Files.file_exists("THIS_IS_LIVE"):
  from common.conf import Live as Conf
else:
  from common.conf import Dev as Conf
  
def syscall(cmd):
  return os.system(cmd)

ADDRESS = "98.236.61.1"
NUM_CLIENTS = 3
BB_CMD = "python Main.py --allow-multiple --no-gui --dev-network"
TEST_PASSWORD = "password"
TEST_USERNAME = "baconface"

#make sure there are no leftover Tor or BitBlinder processes:
torIds = System.get_process_ids_by_name(Globals.TOR_RE)
for pid in torIds:
  System.kill_process(pid)
bbIds = System.get_process_ids_by_name(re.compile("^%s.*$" % (BB_CMD)))
for pid in bbIds:
  System.kill_process(pid)

processes = []
def kill_all():
  for p in processes:
    System.kill_process(p.pid)
def handler(signum, frame):
  kill_all()
signal.signal(signal.SIGTERM, handler)

#for each checkout:
for i in range(1, NUM_CLIENTS+1):
  baseDir = os.path.join("clients", str(i))
  userName = TEST_USERNAME + str(i)
  #do SVN checkouts if necessary:
  if not os.path.exists(baseDir):
    os.makedirs(baseDir)
    syscall("svn checkout svn://svn.bitblinder.com:3690/repo/public/client/trunk %s" % (baseDir))
    #create the initial settings:
    userFolder = os.path.join(baseDir, "users")
    os.makedirs(userFolder)
    #make the login file
    f = open(os.path.join(baseDir, "users", "globals.ini"), "wb")
    f.write("""username = %s
password = %s
save_password = True""" % (userName, TEST_PASSWORD))
    f.close()
    #make the tor settings file
    basePort = 33376 + i * 4
    f = open(os.path.join(userFolder, "torSettings.ini"), "wb")
    f.write("""address = "%s"
dirPort = %s
orPort = %s
dhtPort = 0
socksPort = %s
controlPort = %s
beRelay = True
wasRelay = True""" % (ADDRESS, basePort, basePort+1, basePort+2, basePort+3))
    f.close()
    #make sure we dont send bug reports:
    f = open(os.path.join(userFolder, "commonSettings.ini"), "wb")
    f.write("""askAboutRelay = False
sendBugReports = False
askedAboutBugReports = True
usePsyco = False""")
    f.close()
  #otherwise do SVN updates:
  else:
    syscall("svn update %s" % (baseDir))
  #launch bitblinder
  p = subprocess.Popen(BB_CMD, cwd=baseDir, shell=True)
  #and save the process id for later
  processes.append(p)

#then wait for them all to complete:
try:
  for p in processes:
    p.wait()
except KeyboardInterrupt, e:
  kill_all()
  
