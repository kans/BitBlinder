#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""A script to launch the authority servers"""

import os
import sys
import os.path
import shutil
import subprocess
import copy
import optparse

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.system import System
from common.utils import TorUtils
from common.system import Files

if Files.file_exists("THIS_IS_LIVE"):
  from common.conf import Live as Conf
  LOG_FOLDER = "/mnt/logs/authority/"
  if System.IS_WINDOWS:
    TOR_EXE = "tor_authority.exe"
  else:
    TOR_EXE = "tor"
else:
  from common.conf import Dev as Conf
  LOG_FOLDER = "/home/development/authority/"
  if System.IS_WINDOWS:
    TOR_EXE = "tor_authority.exe"
  else:
    TOR_EXE = "/home/innomitor/src/or/tor"  

AUTH_TORRC_DATA = copy.copy(Globals.TORRC_DATA) + [
#Permit an unlimited number of nodes on the same IP address.
("AuthDirMaxServersPerAddr", "5"),
("AuthDirMaxServersPerAuthAddr", "5"),
#Accelerate voting schedule after first consensus has been reached.
("V3AuthVotingInterval", "%s minutes" % (Conf.INTERVAL_MINUTES)),
("V3AuthVoteDelay", "20 seconds"),
("V3AuthDistDelay", "20 seconds"),
#Accelerate initial voting schedule until first consensus is reached.
("TestingV3AuthInitialVotingInterval", "%s minutes" % (Conf.INTERVAL_MINUTES)),
("TestingV3AuthInitialVoteDelay", "20 seconds"),
("TestingV3AuthInitialDistDelay", "20 seconds"),
#Consider routers as Running from the start of running an authority.
("TestingAuthDirTimeToLearnReachability", "0 minutes"),
#this parameter does what it says--no votes about reachability until this amount of time has elapsed.
#That's lame for the way the network is currently, which is why we are keeping it at 0
#TestingAuthDirTimeToLearnReachability 10 minutes
#Clients try downloading router descriptors from directory caches, even when they are not 10 minutes old.
("TestingEstimatedDescriptorPropagationTime", "0 minutes"),
##Omit self-testing for reachability.
#AssumeReachable 1
#gah, actually, no, we want to test reachability:
("AssumeReachable", "0"),
#email address for complaints
("ContactInfo", "admin@innomi.net"),
#TODO:  change this when we rebuild those tor exes on the server
#allow unpaid circuits through us, for bootstrapping and other miscellenary
("CloseUnpaid", "0"),
#Dont allow anyone to connect to this Tor instance
("SocksPort", "0"),
("AuthoritativeDirectory", "1"),
("V2AuthoritativeDirectory", "1"),
("V3AuthoritativeDirectory", "1"),
("AuthDirRejectUnlisted", "0"),
("ExitPolicy", "reject *:*")
]
#TODO:  a bit hackish, since we moved over to the new format for options
AUTH_TORRC_DATA = "\n".join(" ".join([str(x), str(y)]) for x, y in AUTH_TORRC_DATA)

parser = optparse.OptionParser()
parser.add_option("--purge", action="store_true", dest="purge", default=False)
(options, args) = parser.parse_args()

def write_to_file(fileName, data):
  f = open(fileName, "wb")
  f.write(data)
  f.close()
  
def copy_directory(source, target):
  if not os.path.exists(target):
    os.mkdir(target)
  for root, dirs, files in os.walk(source):
    if '.svn' in dirs:
      dirs.remove('.svn')  # don't visit .svn directories           
    for file in files:
      if os.path.splitext(file)[-1] in ('.pyc', '.pyo', '.fs'):
        continue
      from_ = os.path.join(root, file)           
      to_ = from_.replace(source, target, 1)
      to_directory = os.path.split(to_)[0]
      if not os.path.exists(to_directory):
        os.makedirs(to_directory)
      shutil.copyfile(from_, to_)

if __name__ == '__main__':
  #check if the script is already running:
  authFileName = "AUTH.PID"
  processes = []
  if os.path.exists(authFileName):
    pidFile = open(authFileName, "rb")
    data = pidFile.read()
    pidFile.close()
    data = data.split("\n")
    data.pop()
    for pid in data:
      System.kill_process(int(pid))
  pidFile = open(authFileName, "wb")
  #first generate the DirServer entries:
  dirServers = TorUtils.make_auth_lines(Conf.AUTH_SERVERS)
  #now make each of the torrc files and delete any leftover data:
  authConfs = []
  for i in range(1, len(Conf.AUTH_SERVERS)+1):
    data = dirServers + AUTH_TORRC_DATA
    conf = Conf.AUTH_SERVERS[i-1]
    found = False
    for arg in args:
      if arg == conf["address"]:
        found = True
        break
    if not found:
      continue
    dataDir = "tor_data%d" % (i)
    logFile = "%s/tor%d.out" % (LOG_FOLDER, i)
    data += "\nDataDirectory %s\n" % (dataDir)
    data += "Log [DIRSERV, OR] debug info file %s\n" % (logFile)
    data += "DirPort %s\n" % conf["dirport"]
    data += "ORPort %s\n" % conf["orport"]
    data += "Nickname %s\n" % conf["name"]
    data += "Address %s\n" % conf["address"]    
    #clean up any leftover log files:
    Files.delete_file(logFile, True)
    #remove the old data if we're supposed to:
    if options.purge:
      if os.path.exists(dataDir):
        shutil.rmtree(dataDir, True)
      #copy keys over:
      os.makedirs(dataDir)
      copy_directory("keys%d" % (i), os.path.join(dataDir, "keys"))
    #print out the file
    fileName = "authority%d.conf" % (i)
    write_to_file(fileName, data)
    #start the process
    if System.IS_WINDOWS:
      p = subprocess.Popen(TOR_EXE + " -f " + fileName)
    else:
      p = subprocess.Popen([TOR_EXE, "-f", fileName], executable=TOR_EXE, cwd=os.getcwd())
    processes.append(p)
    pidFile.write(str(p.pid) + "\n")
  pidFile.close()
    
  #resp = raw_input("Just hit enter to close.  ")
  for p in processes:
    p.wait()
    
  #clean up the PID file:
  Files.delete_file(pidFile, True)
  
  print("All done.")
  
