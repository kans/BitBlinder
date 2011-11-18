#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Offers a curses gui."""

import time
import sys
import os
import webbrowser
import getpass
import Queue

from twisted.internet import threads
import curses
import curses.textpad

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.utils import Format
from common.classes import Logger
import gui.console.controller
from core import HTTPClient
from core import ClientUtil
from core import StatusTracker
from Applications import GlobalSettings

hotkey_attr = curses.A_BOLD | curses.A_UNDERLINE

class PsuedoGobject():
  """provides the is_visible interface"""
  def __init__(self):
    pass
    
  def is_visible(self):
    return True
    
class Money():
  def __init__(self, name, value):
    """represents BB credits"""
    self.name = name
    self.value = value
    self.pretty = None
  
  def update(self, value):
    self.value = value
    
  def justify_right(self, maxLen):
    myLen = len(self.name) + len(str(self.value)) + len(self.pretty) + 5 # includes teh :() and 2 spaces
    blanks = maxLen - myLen
    return "%s%s: %s (%s)"%(" "*blanks, self.name, self.value, self.pretty)
    
  def make_pretty(self):
    """Note, pretty is set here!"""
    self.pretty = Format.convert_to_gb(self.value)
    return self.pretty
    
  def __len__(self):
    #                 x GB                     X            the :()
    return(len(self.make_pretty()) + len(str(self.value)) + 3)
    
class Controller(gui.console.Controller.Controller):
  def __init__(self):
    gui.console.Controller.Controller.__init__(self)
    self.statistics = {}
    #we can't just print stuff out to the screen, so this is called instead until I figure out something less stupidlike
    Logger.PRINT_FUNCTION = self.log_msg
    self.stdscr = None
    #theses objects are usd by the credit display
    for item in ('Wallet', 'Bank Balance', 'Earned', 'Spent'):
      self.statistics[item] = (Money(item, 0))
    self.status = {"Relay": 'Unknown', "UPNP": 'Unknown', "Published": 'Unknown', "Port": 'Unknown', "Client": 'Unknown'}
    self.rows          = {}
    self.lastData      = None
    self.curDownload   = None
    self.socksDisplay  = PsuedoGobject()
    self.statusDisplay = PsuedoGobject()
    self.torrents      = {'torrents':[], 'maxLength': 0}
    self.torStatus     = None
    #Keystrokes go into a threadsafe queue and are popped out in the main thread 
    self.q = Queue.Queue()
    self.shouldListen = True
    #this is used to store the previous N calls to log_msg
    self.msgBuffer = []
    #stores infos about external socks apps
    self.apps = {}
    self.moniesDisplay = [9, None]
    self.statusDisplay = (9, 60)
    self._start_curses()
    Globals.reactor.callInThread(self._listener)
    self.catch_event("shutdown")
    ClientUtil.add_updater(self)
    
  def _start_curses(self):
    # Initialize curses
    self.stdscr = curses.initscr()
    #curses.start_color()
    curses.noecho()
    curses.cbreak()
    curses.nl()
    curses.curs_set(0)
    self.stdscr.keypad(1)
    self.make_display()
    self.size = self._get_screen_size()

  def on_update(self):
    """if the size of the screen has changed, we need to update the screen"""
    self.take_action()
    self.make_display()
      
  def on_shutdown(self):
    """sets everything back to the way it was started"""
    log_msg('Exiting curses!', 3)
    self.shouldListen = False
    self.stdscr.clear()
    self.stdscr.keypad(0)
    self.stdscr = None
    curses.curs_set(1)
    curses.echo()
    curses.nocbreak()
    curses.endwin()
    Logger.PRINT_FUNCTION = None
    
  def _listener(self):
    """listens for keystrokes from the user and puts them in the Queue"""
    self.stdscr.timeout(500)
    while self.shouldListen:
      k = self.stdscr.getch()
      if k == -1:
        continue
      try:
        self.q.put(k)
      except Exception, e:
        log_ex(e, 'Couldn\'t shove in queue')
    log_msg('Stopping curses listener.', 2)

  def take_action(self):
    """takes items out of the key stroke queue and does stuffs with them"""
    while not self.q.empty():        
      k = self.q.get()
      if k in (curses.KEY_END, ord('q'), ord('Q')):
        log_msg('Quiting.', 1)
        GlobalEvents.throw_event("quit_signal")
      else:
        curses.beep()
      self.q.task_done()
  
  def display(self, data):
    """pushes data into our local cache of infos and also gets the length of the longest torrent info string"""
    if not data:
      return
    self.torrents = {'torrents':[], 'maxLength': 0}
    maxLength = 0
    for x in data:
      ( name, status, progress, peers, seeds, seedsmsg, dist,
        uprate, dnrate, upamt, dnamt, size, t, msg, hash, knownSeeds, knownPeers ) = x
      
      progress = float(progress.replace("%", ""))
      progressMsg = "%.0f" % (progress)
      pathname, filename = os.path.split(name)
      #TODO: do this better (truncate the name)
      if len(filename) > 14:
        filename = filename[:10] + '... '
      dist = "%.3f" % (dist*1000)
      uprate = Format.bytes_per_second(uprate)
      dnrate = Format.bytes_per_second(dnrate)
      upamt = Format.format_bytes(upamt)
      dnamt = Format.format_bytes(dnamt)
      s = '%s-> P: (%s)%s | S: (%s)%s | D: %s (%s) | U: %s (%s) | %s%%'%\
      (filename, peers, knownPeers, seeds, knownSeeds, dnamt, dnrate, upamt, uprate, progress)
      if len(s) > maxLength:
        maxLength = len(s)
      self.torrents['torrents'].append(s)
    self.torrents['maxLength'] = maxLength
    return False
  
  def _make_bit_twister_display(self):
    if len(self.torrents['torrents']) == 0:
      #no .torrents yet, still display the header
      height = 1
      width = 9
    else:
      height = 2 * len(self.torrents['torrents']) + 1
      width = self.torrents['maxLength'] + 1
    r, c = self._get_screen_size()
    if r > self.moniesDisplay[0] + height + 1 and \
       c > self.serverDisplay[1] + width + 1:
      win = self.stdscr.derwin(height, width, r - height, c - width)
      win.addstr(0, width - 9, 'Torrents', curses.A_BOLD)
      #add the apps to the gui
      row = 2
      rowSep = 2
      for formatedString in self.torrents['torrents']:
        if len(formatedString) < self.torrents['maxLength']:
          formatedString = ' '*(self.torrents['maxLength'] - len(formatedString)) + formatedString
        win.addstr(row, 0, formatedString)
        row += rowSep
      win.refresh()
    else:
      log_msg('There was not enough screen space (%s, %s) for the torrents display (%s, %s)'%
             (r ,c , height, width), 4)
    return
    
  def _make_server_display(self):
    """Displays infos about the any apps that connect to BB via socks
    This method should be size safe"""

    #first, we need to know how big everything is, so generate the text
    l = []
    maxLen = 0
    for app in self.apps:
      s = '%s-> Hops: %s | Down: %s | Up: %s'%(app,
          self.apps[app][0], self.apps[app][1], self.apps[app][2])
      l.append(s)
      if len(s) > maxLen:
        maxLen = len(s)
    width = maxLen + 1
    r, c = self._get_screen_size()
    if len(l) == 0:
      #no apps yet, still display the header
      height = 1
      width = 11
    else:
      #a app takes three rows including the header and an empty line
      height = 2 * len(l) + 1
    self.serverDisplay = [height, width]
    #bottom left corner with at least one row of padding
    if r > height + self.statusDisplay[0] and c > width:
      win = self.stdscr.derwin(height, width, r - height, 0)
      win.addstr(0, 0, 'Socks Apps', curses.A_BOLD)
      #add the apps to the gui
      row = 2
      rowSep = 2
      for formatedString in l:
        win.addstr(row, 0, formatedString)
        row += rowSep
      win.refresh()
    else:
      log_msg('There was not enough screen space (%s, %s)for server display (%s, %s)'%
                   (r ,c ,height ,width), 4)
    return
      
  def _make_monies_display(self):
    #need to know our width before we can fit
    maxLen = 0
    for key, stat in self.statistics.iteritems():
      #note, this implicitly sets the pretty text 
      statLen = len(stat)
      if statLen > maxLen:
        maxLen = statLen
    totalWidth = maxLen + 15 + 1
    r, c = self._get_screen_size()
    #will it fit in the top right corner (width is variable, though the rows shouldn't change)
    if r > self.moniesDisplay[0]  and \
       c > totalWidth + self.statusDisplay[1] + 1:
      startY = 0
      startX = c - totalWidth - 1
      win = self.stdscr.derwin(self.moniesDisplay[0], totalWidth + 1, startY, startX)
      win.clear()
      #win.border()
      win.addstr(0, 0, "%sCredits"%((totalWidth - 7)*" "), curses.A_BOLD)
      row = 2
      rowSep = 2
      col = 0
      #dump things into the window! (should we sort them first?)
      for key, value in self.statistics.iteritems():
        win.addstr(row, col, value.justify_right(totalWidth))
        row += rowSep
      win.refresh()
    else:
      log_msg('There was not enough screen space (%s, %s) for the credits display (%s, %s)'%
                   (r, c, self.moniesDisplay[0], totalWidth), 4)
    return
    
  def _make_status_display(self):
    r, c = self._get_screen_size()
    if r > self.statusDisplay[0] + 1 and \
       c > self.statusDisplay[1]:
      startY = 0
      startX = 0
      win = self.stdscr.derwin(self.statusDisplay[0], self.statusDisplay[1], startY, startX)
      win.clear()
      win.addstr(0, 0, 'BitBlinder %s Console '%(Globals.VERSION), curses.A_BOLD)
      win.addstr(2, 0, "Client: %s"%(self.status['Client']))
      win.addstr(4, 0, "Port: %s"%(self.status['Port']))
      win.addstr(6, 0, "Published: %s"%(self.status['Published']))
      win.addstr(8, 0, "Relay: %s"%(self.status['Relay']))
      win.refresh()
    else:
      log_msg('There was not enough screen space (%s, %s) for the server display (%s, %s)'%
                   (r ,c , self.statusDisplay[0], self.statusDisplay[1]), 4)
    return
    
  def new_tube_socks(self, stats):
    log_msg('new socks app.', 1)
    self.apps[stats[0]] = stats[1:]
    self.make_display()
    
  def tube_socks_update(self, stats):
    self.apps[stats[0]] = stats[1:]
    self.make_display()
    self.log_msg()
      
  def tube_socks_died(self, app):
    del self.apps[app]
    self.make_display()
    self.log_msg()

  def make_display(self):
    """puts everything together on the screen
    NOTE: these calls are order dependent"""
    #BB probably shouldn't die over the gui
    try:
      if self.stdscr:
        self.stdscr.clear()
        self._make_monies_display()
        self._make_status_display()
        self._make_server_display()
        self._make_bit_twister_display()
        self.stdscr.refresh()
      else:
        return
    except Exception, e:
      log_ex(e, 'Error while making curses gui')
    return
    
  def _get_screen_size(self):
    return self.stdscr.getmaxyx()
  
  def format_text_for_log_msg(self, text=None):
    if text:
      text = str(text)
      if type(text) != str:
        text = " "
      if len(self.msgBuffer) > 25:
        self.msgBuffer.pop()
      self.msgBuffer.insert(0, text)
    t = ""
    for item in self.msgBuffer:
      t += '\n'+item
    if type(t) != str:
      return 'type was: %s'%type(t)
    return t
    
  def log_msg(self, text=None):
    """We could display this to the user..."""
    pass
#    r, c = self._get_screen_size()
#    pad = None
#    try:
#      pad = curses.newpad(150, c-4)
#    except:
#      log_msg('not enough screen space for msg log', 0)
#    #try stuffing text into pad
#    if pad:
#      try:
#        pad.addstr(0, 0, 'Log: ', curses.A_BOLD)
#        pad.addstr(0, 5, 'note, all messages are saved to disk.')
#        formatedText = self.format_text_for_log_msg(text)
#        pad.addstr(1, 0, formatedText)
#      except Exception, e:
#        #log_ex(e, 'bad log msg')
#        #the last msg must have been too big to fit,TODO: leave a note
#        self.msgBuffer[0] != ' '
##        pad.addstr(0, 0, 'Log:\n', curses.A_BOLD)
##        #TODO: the window could have been downsized, so previous msgs may not fit
##        formatedText = self.format_text_for_log_msg(text)
##        pad.addstr(1, 0, formatedText)
#      #TODO: this will break with a small screen
#      pminrow = 0
#      pmincol = 0
#      sminrow = r/2
#      smincol = 2
#      smaxrow = r-3
#      smaxcol = c - 2 #assuming c > 2 > smincol
#      pad.refresh(pminrow, pmincol, sminrow, smincol, smaxrow, smaxcol)
    return
    
  def do_verification_prompt(self, callback):
    #global config stores the last user that logged in (and his password)
    settings = GlobalSettings.get()
    
    def make_textpad():
      editWindow = self.stdscr.derwin(1, curses.COLS-startX, startY + 1, startX)
      editWindow.clear()
      textpad = curses.textpad.Textbox(editWindow)
      return textpad, editWindow
      
    #just directly login:
    self.username = str(settings.username)
    self.password = str(settings.password)
    self.savePass = settings.save_password
    startY = 1
    startX = 0
    while not self.username or not self.password:
      self.stdscr.addstr(startY, startX, 'Enter your username- use emacs bindings (ctrl-g to enter).')
      curses.curs_set(1)
      self.stdscr.refresh()
      textpad, win = make_textpad()
      #TODO: this should be in a thread
      self.username = textpad.edit().rstrip()
      win.clear()
      self.stdscr.addstr(startY, startX, 'Enter your password- use emacs bindings (ctrl-g to enter).')
      textpad, win = make_textpad()
      win.clear()
      self.stdscr.refresh()
      self.password = textpad.edit().rstrip()
      #check that the username is possibly valid:
      if not Globals.USERNAME_REGEX.match(self.username):
        log_msg("Usernames can only contain A-Z, a-z, 0-9, -, _, and spaces in the middle", 0)
        self.username = None
    
    curses.curs_set(0)
    callback(self.username, self.password)
      
  def status_update(self, isServer, torStatus=None, portStatus=None, publishedStatus=None, upnpStatus=None, relayStatus=None, statistics=None, portNum=None):
    #get new infos on the monies
    for key, value in statistics.iteritems():
      self.statistics[key].update(value)
    
    if not isServer:
      self._make_monies_display()
      return
      
    #____ Port ____
    if portStatus is StatusTracker.OK:
      self.status['Port'] = 'Port %s is reachable.'%portNum
    elif portStatus is StatusTracker.PURGATORY:
      self.status['Port'] = 'Testing if %s is reachable.'%portNum
    elif portStatus is StatusTracker.DEAD:
      self.status['Port'] = 'Port %s is unreachable :('%portNum
    else:
      raise Exception('Unknown tor app status: %s'%status)
      
    #___Tor____
    if torStatus is StatusTracker.OK:
      self.status['Client'] = 'InnomiTor started correctly.'
    elif torStatus is StatusTracker.PURGATORY:
      self.status['Client'] = "Innomitor is bootstrapping."
    elif torStatus is StatusTracker.DEAD:
      self.status['Client'] = "Innomitor failed to launch :("
    else:
      raise Exception('Unknown tor app status: %s'%status)
    
    #___Published___
    if publishedStatus is StatusTracker.OK:
      self.status['Published'] = "Your relay descriptor is published."
    elif publishedStatus is StatusTracker.PURGATORY:
      self.status['Published'] = "Your relay descriptor has not been published."
    elif publishedStatus is StatusTracker.DEAD:
      self.status['Published'] = "Your relay descriptor is not published."
    else:
      raise Exception('Unknown tor app status: %s'%status)
      
    #___UPNP____
    if upnpStatus is StatusTracker.OK:
      self.status['UPNP'] = "UPNP appears to be supported."
    elif upnpStatus is StatusTracker.PURGATORY:
      self.status['UPNP'] = "Testing for UPNP support"
    elif upnpStatus is StatusTracker.DEAD:
      self.status['UPNP'] = "UPNP is not supported."
    else:
      raise Exception('Unknown tor app status: %s'%status)
      
    #___Relay___
    if relayStatus is StatusTracker.OK:
      self.status['Relay'] = "Your relay is all good!"
    elif relayStatus is StatusTracker.PURGATORY:
      self.status['Relay'] = "Your relay is starting."
    elif relayStatus is StatusTracker.OTHER:
      self.status['Relay'] = "BB is not configured to relay."
    elif relayStatus is StatusTracker.DEAD:
      self.status['Relay'] = "An error was experienced starting your relay."
    else:
      raise Exception('Unknown tor app status: %s'%status)
    
    #___Updates___
    if self.stdscr:
      self._make_monies_display()
      self._make_status_display()
  
