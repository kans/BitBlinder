#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Implements basic operations on linux."""

import os
import subprocess
import re

from twisted.internet.abstract import isIPAddress

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

def get_pid_from_port(port):
  """Figure out the process that has launched a connection from port.  Returns
  the pid, or 0 on failure"""
  port = int(port)
  try:
    #read in netstat -pant
    p = subprocess.Popen("netstat -pant 2>/dev/null | grep %s" % (port), shell=True, stdout=subprocess.PIPE)
    p.wait()
    data = p.stdout.read()
    if not data:
      return 0
    lines = data.split("\n")
    #pop the last line (it's empty)
    lines.pop()
    #for each of the program/port bindings:
    for line in lines:
      line = line.split()
      localAddr = line[3]
      remoteAddr = line[4]
      #dont bother with remote addresses
      if localAddr.rfind(":::") != -1 or remoteAddr.rfind(":::") != -1:
        continue
      localAddr = localAddr.split(":")
      remoteAddr = remoteAddr.split(":")
      #if these are the droids we're looking for:
      if localAddr[0] in ("0.0.0.0", "127.0.0.1") and remoteAddr[0] in ("0.0.0.0", "127.0.0.1") and int(localAddr[1]) == port:
        process = line[6].split("/")
        return process[0]
  except Exception, e:
    log_ex(e, "While doing linux portmapping")
  return 0

#TODO:  no idea what to do when there are multiple gateways.  Maybe I should be filtering based on our adapter or whatever...
def get_default_gateway():
  p = subprocess.Popen(["/sbin/route -n"], shell=True, stdout=subprocess.PIPE)
  for row in p.stdout.readlines():
    a = re.compile("^(.+?)\s+(.+?)\s+.*$").match(row).group(2)
    if isIPAddress(a) and a !="0.0.0.0":
      return a
    
def get_process_ids():
  """Returns a list of tuples of all processes and their respective PIDs"""
  #returns all processes in the form Name PID
  p = subprocess.Popen("ps -eo comm,pid", shell=True, stdout=subprocess.PIPE)
  p.wait()
  data = p.stdout.read()
  processes = []
  if not data:
    return processes
  lines = data.split("\n")
  #pop the last line (it's empty)
  lines.pop()
  for line in lines:
    #we get strange formating back with a bunch of / and \
    a = line.split(" ")
    name = a[0]
    pid = a[len(a)-1]
    try:
      name = name.split('/')[0]
    except:
      pass
    try:
      pid = int(pid.rstrip())
    except:
      pass
    processes.append((name, pid))
  return processes

def process_exists(pid):
  """Check if a given process ID is currently running."""
  proc_ids = get_process_ids()
  for x in proc_ids:
    if x[1] == pid:
      return True
  return False

def kill_process(pid):
  """Kills a process with the given id"""
  killProcess = subprocess.Popen('kill -9 ' + str(pid),  shell=True)
  killProcess.wait()

def is_admin():
  try:
    return os.getuid() == 0
  except:
    return False
  
