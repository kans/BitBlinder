#!/usr/bin/python
#Copyright 2008 InnomiNet
import platform
import os
import shutil
import subprocess

from twisted.internet import threads
from twisted.internet.error import ConnectionDone

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.classes import Scheduler
from common.system import System
from common import Globals
from common.utils import Basic
from common.utils import Crypto
from common.Errors import DownloadSizeError
from common.events import GlobalEvents
from Applications import BitBlinder
from gui import GUIController
from core import ProgramState

if ProgramState.USE_GTK:
  from gui.gtk.utils import GTKUtils
  
def get():
  return _instance

class Updater():
  def __init__(self):
    self.newVersion = None
    self.trueHash = None
    self.updateString = None
    self.downloadingUpdate = False
    self.baseURL = "%s/media/" % (ProgramState.Conf.BASE_HTTPS)
    if System.IS_WINDOWS:
      self.baseURL += "windows/"
    else:
      self.baseURL += "linux/"
    #: whether we should apply an update and restart:
    self.APPLY_UPDATE = False  
    
  def start(self):
    self.check_for_updates()
    Scheduler.schedule_repeat(60 * 60 * 12, self.check_for_updates)
  
  def update_request_done(self, data, httpDownloadInstance=None):
    """Handle the response from the web server telling us about the current version of the program.
    Return True if there is a new version, False otherwise.
    data=web server response
    httpDownloadInstance=HTTP request object that got the response"""
    data = data.replace("\r", "")
    data = data.split("\n\n")
    version = data[0]
    if Basic.compare_versions_strings(version, Globals.VERSION):
      self.download_update(data)
      return True
    else:
      log_msg("Your version is up to date.")
    return False

  def check_for_updates(self, success_cb=None, failure_cb=None):
    """Send out a request to the web server to check the current version information
    Returns True so that it is rescheduled to be called again later.
    success_cb=what to do when we've gotten the current version info
    failure_cb=what to do if we fail to get the current version info"""
    try:
      if not success_cb:
        success_cb = self.update_request_done
      url = self.baseURL + "current_version.txt"
      def on_failure(failure, instance, failure_cb=failure_cb):
        log_ex(failure, "Failed while downloading current version document", [ConnectionDone])
        if failure_cb:
          failure_cb(failure, instance)
      #TODO:  go through a circuit if the user wants to be stealthy:
      BitBlinder.http_download(url, None, success_cb, on_failure)
    except Exception, e:
      log_ex(e, "Failed while attempting to get update document")
    return True
    
  def download_update(self, newVersionData):
    """Download the latest version of InnomiNet from the web server
    newVersion=the version to download"""
    self.newVersion = newVersionData[0]
    self.trueHash = newVersionData[1]
    self.updateString = newVersionData[2]
    if System.IS_WINDOWS:
      #if we're not already doing the update:
      if not self.downloadingUpdate:
        self.downloadingUpdate = True
        #baseURL += "BitBlinderUpdate-%s-%s.exe" % (Globals.VERSION, self.newVersion)
        fileName = "BitBlinderInstaller-%s.exe" % (self.newVersion)
        url = self.baseURL + fileName
        #TODO:  go through a circuit if the user wants to be stealthy:
        BitBlinder.http_download(url, None, self.request_done, self.request_failed, progressCB=self.progressCB, fileName=Globals.UPDATE_FILE_NAME+".download")
        GUIController.get().show_msgbox("BitBlinder found a new version (%s)!\n\nDownloading update now... (you can choose whether to restart later)" % (self.newVersion))
    else:
      #url = self.baseURL + "python-bitblinder_%s_%s.deb" % (self.newVersion, platform.machine())
      url = "%s/download/" % (ProgramState.Conf.BASE_HTTP)
      if ProgramState.USE_GTK:
        link = GTKUtils.make_html_link(url, url)
      else:
        link = url
      GUIController.get().show_msgbox("A new linux package is available!  Changes:\n\n%s\n\nGo download and install it from:" % (self.updateString), title="Update Available", link=link)
    
  def hash_failed(self, error):
    self.downloadingUpdate = False
    log_ex(error, "Error while verifying update")
    #lets just try again in half an hour or something
    Scheduler.schedule_once(30 * 60, self.check_for_updates)
    
  def hash_done(self, ourHash):
    self.downloadingUpdate = False
    if ourHash.lower() != self.trueHash.lower():
      self.hash_failed("Download hash was wrong.")
      return
    shutil.move(Globals.UPDATE_FILE_NAME+".download", Globals.UPDATE_FILE_NAME)
    #Now ask the user if they want to update:
    GUIController.get().update_prompt(self.newVersion, "%s\n\nWould you like to apply the update right now?" % (self.updateString), self.restart_for_update)
  
  def request_failed(self, error, httpDownloadInstance=None):
    self.downloadingUpdate = False
    log_ex(error, "Error while downloading update", [DownloadSizeError])
    #lets try the full installer instead then
    Scheduler.schedule_once(30 * 60, self.check_for_updates)
    
  def request_done(self, fileName, httpDownloadInstance=None):
    #calculate the hash for the new data:
    log_msg("Validating downloaded updater")
    d = threads.deferToThread(Crypto.hash_file_data, fileName)
    d.addCallback(self.hash_done)
    d.addErrback(self.hash_failed)
    
  def progressCB(self, val):
    #log_msg(val)
    return
    
  def restart_for_update(self, newVersion):
    """Trigger an update after it has been downloaded"""
    if System.IS_WINDOWS:
      self.APPLY_UPDATE = True
      GlobalEvents.throw_event("quit_signal")
    else:
      #just prompt the user, since we cant really auto update in linux:
      GUIController.get().show_msgbox("Please close BitBlinder and run the following commands to update BitBlinder:\n\nsudo dpkg -P python-bitblinder\nsudo dpkg -i %s" % (Globals.UPDATE_FILE_NAME))
      
#: responsible for detecting, downloading, and applying updates:
_instance = Updater()
