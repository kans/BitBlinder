#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Implements basic operations on windows."""

import time
import win32api
import win32con
import win32process
import win32event
import ctypes
import win32com.client
try:
  from windows.lib import PortMap
except:
  import PortMap
from ctypes import c_long, c_int, c_uint, c_char, c_void_p
from ctypes import windll
from ctypes import Structure
from ctypes import sizeof, POINTER, pointer

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic

#blocking, obviously
def wait_for_pid(pid):
  handles = [win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, 0, pid)]
  #NOTE: WaitForMultipleObjects() supports at most 64 processes at a time
  index = win32event.WaitForMultipleObjects(handles, False, win32event.INFINITE)
  return handles[index]
  
def get_pid_from_port(port):
  """Figure out the process that has launched a connection from port.  Returns
  the pid, or 0 on failure"""
  port = int(port)
  return PortMap.find_pid_by_port(port)

#TODO:  no idea what to do when there are multiple gateways.  Maybe I should be filtering based on our adapter or whatever...
def get_default_gateway():
  #TODO:  execing route print is probably a better idea here
  try:
    strComputer = "."
    objWMIService = win32com.client.Dispatch("WbemScripting.SWbemLocator")
    objSWbemServices = objWMIService.ConnectServer(strComputer,"root\cimv2")
    colItems = objSWbemServices.ExecQuery("Select * from Win32_NetworkAdapterConfiguration")
    gateways = []
    for objItem in colItems:
      z = objItem.DefaultIPGateway
      if z:
        for x in z:
          gateways.append(x)
    if len(gateways) > 1:
      log_msg("Why are there multiple gateways?  :(  %s" % (Basic.clean(gateways)), 2)
    elif len(gateways) == 0:
      return None
    return gateways.pop(0)
  except Exception, e:
    log_ex(e, "Failed to get default gateway")
    return "192.168.1.1"

#TODO:  validate that this is called from the main thread, within the function
def get_process_and_children(pid, processes=None):
  """Returns a list of pids corresponding to the process tree of which id is the
  parent, in depth-first search order.  Includes id.  Should almost certainly be called from the main thread.
  """
  if not processes:
    processes = [pid]
  allProcesses = get_all_processes()
  for p in allProcesses:
    if p[2] == pid and p[0] not in processes:
      processes = get_process_and_children(p[0], processes)
  return processes
    
def get_process_ids():
  """Returns a list of tuples of all processes and their respective PIDs"""
  proc_ids = []
  processes = get_all_processes()
  for p in processes:
    name = p[1].split("\\")[-1]
    proc_ids.append([name, p[0]])
  return proc_ids

def process_exists(pid):
  """Check if a given process ID is currently running."""
  try:
    handle = win32api.OpenProcess(win32con.PROCESS_ALL_ACCESS, 0, pid)
  except Exception, e:
    #5 is access denied, I forget what 87 is
    if hasattr(e, "args") and len(e.args) > 1 and e.args[0] in (5, 87) and e.args[1]=="OpenProcess":
      return False
    raise e
  code = win32process.GetExitCodeProcess(handle)
  #print("CODE:  %s" % (code))
  if code == 259:
    return True
  else:
    return False

#TODO:  this is pretty powerful.  We could use this on startup to kill anything launched as part of our portable installation that was leftover from last time
def get_process_ids_by_exe_path(path_regex):
  processes = []
  allProcesses = get_all_processes()
  for p in allProcesses:
    if p[1] and path_regex.match(p[1]):
      processes.append(p[0])
  return processes

def kill_process(pid):
  """Kills a process with the given id"""
  try:
    handle = win32api.OpenProcess(win32con.PROCESS_TERMINATE, 0, pid)
    #JOSH:  intarwebs says this:
    #handle = win32api.OpenProcess(True, win32con.PROCESS_TERMINATE, pid)
    #win32api.TerminateProcess(handle,-1)
    if handle:
      win32api.TerminateProcess(handle, 0)
      win32api.CloseHandle(handle)
  except Exception, e:
    #this basically means that the process died while we were trying to kill it, which is fine
    if hasattr(e, "args") and len(e.args) > 1 and e.args[0]==5 and e.args[1]=="TerminateProcess":
      return
    if hasattr(e, "args") and len(e.args) > 1 and e.args[0]==87 and e.args[1]=="OpenProcess":
      return
    raise e
  #wait until it is dead for sure, or it has taken too long:
  startWait = time.time()
  while startWait + 10 > time.time():
    if not process_exists(pid):
      break
    #TODO:  not the best way to wait for program to close itself so that we dont get an exception...
    time.sleep(0.5)
  
def is_admin():
  try:
    return ctypes.windll.shell32.IsUserAnAdmin()
  except:
    return False
    
#Code from here:
#http://code.activestate.com/recipes/576362/

# const variable
TH32CS_SNAPPROCESS = 2
STANDARD_RIGHTS_REQUIRED = 0x000F0000
SYNCHRONIZE = 0x00100000
PROCESS_ALL_ACCESS = (STANDARD_RIGHTS_REQUIRED | SYNCHRONIZE | 0xFFF)
TH32CS_SNAPMODULE = 0x00000008

# struct 
class PROCESSENTRY32(Structure):
    _fields_ = [ ( 'dwSize' , c_uint ) , 
                 ( 'cntUsage' , c_uint) ,
                 ( 'th32ProcessID' , c_uint) ,
                 ( 'th32DefaultHeapID' , c_uint) ,
                 ( 'th32ModuleID' , c_uint) ,
                 ( 'cntThreads' , c_uint) ,
                 ( 'th32ParentProcessID' , c_uint) ,
                 ( 'pcPriClassBase' , c_long) ,
                 ( 'dwFlags' , c_uint) ,
                 ( 'szExeFile' , c_char * 260 ) , 
                 ( 'th32MemoryBase' , c_long) ,
                 ( 'th32AccessKey' , c_long ) ]

class MODULEENTRY32(Structure):
    _fields_ = [ ( 'dwSize' , c_long ) , 
                ( 'th32ModuleID' , c_long ),
                ( 'th32ProcessID' , c_long ),
                ( 'GlblcntUsage' , c_long ),
                ( 'ProccntUsage' , c_long ) ,
                ( 'modBaseAddr' , c_long ) ,
                ( 'modBaseSize' , c_long ) , 
                ( 'hModule' , c_void_p ) ,
                ( 'szModule' , c_char * 256 ),
                ( 'szExePath' , c_char * 260 ) ]

# forigen function
## CreateToolhelp32Snapshot
CreateToolhelp32Snapshot = windll.kernel32.CreateToolhelp32Snapshot
CreateToolhelp32Snapshot.reltype = c_long
CreateToolhelp32Snapshot.argtypes = [ c_int , c_int ]
## Process32First
Process32First = windll.kernel32.Process32First
Process32First.argtypes = [ c_void_p , POINTER( PROCESSENTRY32 ) ]
Process32First.rettype = c_int
## Process32Next
Process32Next = windll.kernel32.Process32Next
Process32Next.argtypes = [ c_void_p , POINTER(PROCESSENTRY32) ]
Process32Next.rettype = c_int
## OpenProcess
OpenProcess = windll.kernel32.OpenProcess
OpenProcess.argtypes = [ c_void_p , c_int , c_long ]
OpenProcess.rettype = c_long
## GetPriorityClass
GetPriorityClass = windll.kernel32.GetPriorityClass
GetPriorityClass.argtypes = [ c_void_p ]
GetPriorityClass.rettype = c_long
## CloseHandle
CloseHandle = windll.kernel32.CloseHandle
CloseHandle.argtypes = [ c_void_p ]
CloseHandle.rettype = c_int
## Module32First
Module32First = windll.kernel32.Module32First
Module32First.argtypes = [ c_void_p , POINTER(MODULEENTRY32) ]
Module32First.rettype = c_int

def get_all_processes():
  processList = []
  hProcessSnap = c_void_p(0)
  hProcessSnap = CreateToolhelp32Snapshot( TH32CS_SNAPPROCESS , 0 )
  try:
    pe32 = PROCESSENTRY32()
    pe32.dwSize = sizeof( PROCESSENTRY32 )
    ret = Process32First( hProcessSnap , pointer( pe32 ) )
    while ret :
      hProcess = OpenProcess( PROCESS_ALL_ACCESS , 0 , pe32.th32ProcessID )
      try:
        dwPriorityClass = GetPriorityClass( hProcess )
        if dwPriorityClass != 0 :
          hModuleSnap = c_void_p(0)
          me32 = MODULEENTRY32()
          me32.dwSize = sizeof( MODULEENTRY32 )
          exePath = ""
          hModuleSnap = CreateToolhelp32Snapshot( TH32CS_SNAPMODULE, pe32.th32ProcessID )
          try:
            ret = Module32First( hModuleSnap, pointer(me32) )
            if ret != 0 :
              exePath = me32.szExePath
          finally:
            CloseHandle( hModuleSnap )
          processList.append((pe32.th32ProcessID, exePath, pe32.th32ParentProcessID))
      finally:
        CloseHandle( hProcess )
      ret = Process32Next( hProcessSnap, pointer(pe32) )
  except Exception, e:
    log_ex(e, "Error while getting detailed process list")
  finally:
    CloseHandle(hProcessSnap)
  return processList
