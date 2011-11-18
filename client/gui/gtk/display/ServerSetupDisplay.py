#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Window for setting up the Tor relay"""

import os

from twisted.internet import defer
import gtk

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Scheduler
from common.system import System
from common.events import GlobalEvents
from common.events import GeneratorMixin
from core import ClientUtil
from gui.gtk.widget import OptionalToggleFrame
from gui.gtk.window import TopWindow
from gui.gtk.utils import GTKUtils
from gui.gtk.utils import WrapLabel
from gui.gtk.utils import Images
from gui.gtk.dialog import BaseDialog
from gui.gtk.display import SettingsDisplay
from Applications import Tor

PADDING = 10

ICON_SIZE = 48
QUESTION_PIXBUF = Images.make_icon("question.png", ICON_SIZE)
WARNING_PIXBUF = Images.make_icon("warning.png", ICON_SIZE)
SUCCESS_PIXBUF = Images.make_icon("apply.png", ICON_SIZE)

STATUS_MARKUP = "<span size='large'>%s</span>"
UNKNOWN_MARKUP = STATUS_MARKUP % ("Unknown")

BUTTON_MARKUP = "<span>%s</span>"

TITLE_MARKUP = "<span size='x-large' weight='bold'>%s</span>"
TITLE_TESTING = TITLE_MARKUP % ("Testing reachability of port %s")
TITLE_SUCCESS = TITLE_MARKUP % ("Relay port (%s) is reachable!")
TITLE_FAILURE = TITLE_MARKUP % ("Forward the relay port (%s)")
TITLE_UNTESTED = TITLE_MARKUP % ("Rerun the test with port %s")

def _unify_widget_widths(widgets):
  maxWidth = max([widget.size_request()[0] for widget in widgets])
  for widget in widgets:
    widget.set_size_request(maxWidth, -1)

class ServerSetupDisplay(GlobalEvents.GlobalEventMixin,  GeneratorMixin.GeneratorMixin):
  def __init__(self, controller):
    GeneratorMixin.GeneratorMixin.__init__(self)
    self.controller = controller
    self.testUpdateEvent = None
    self.torApp = Tor.get()
    self.lastTestResult = None
    ClientUtil.add_updater(self)
    self._add_events("failure", "success", "size_changed")
    
    #make the components for this GUI
    instructionBox = self._make_instruction_box()
    requiredPortsBox = self._make_required_ports_box()
    optionalPortsBox = self._make_optional_ports_box()
    buttonBox = self._make_button_box()
    
    #pack them into our window:
    box = gtk.VBox(spacing=PADDING)
    box.pack_start(instructionBox, False, False, 0)
    box.pack_start(requiredPortsBox, False, False, 0)
    box.pack_start(optionalPortsBox, False, False, 0)
    box.pack_end(buttonBox, False, False, 0)
    box.show()
    
    paddedBox = GTKUtils.add_padding(box, PADDING)
    paddedBox.show()
    frame = GTKUtils.add_frame(paddedBox)
    frame.show()
    
    self.container = frame
    self.label = gtk.Label("Relay Setup")
    
    #make pretty:
    _unify_widget_widths([self.relayBox.label, self.dhtBox.label, self.dirBox.label, self.upnpBox.label])
    _unify_widget_widths([self.relayBox.entry.entry, self.dhtBox.entry.entry, self.dirBox.entry.entry, self.upnpBox.entry.entry])
    self.container.set_focus_child(self.doneButton)
    
  def start(self):
    for box in (self.relayBox, self.dirBox, self.dhtBox):
      box.initialize()
    self._start_test()
    self.container.show()
    
  def stop(self):
    self.container.hide()

  def _restart_test_cb(self, widget=None):
    if self.lastTestResult == None:
      self._on_test_failure()
    else:
      deferreds = []
      for portName in ("orPort", "dirPort", "dhtPort"):
        deferreds.append(self.torApp.stop_forwarded_port(portName))
      allStoppedDeferred = defer.DeferredList(deferreds)
      def on_all_ports_done(result):
        self.progressBar.set_text("Testing...")
      allStoppedDeferred.addCallback(on_all_ports_done)
      allStoppedDeferred.addErrback(on_all_ports_done)
      
      self._start_test()
      
      self.progressBar.set_text("Stopping existing ports...")
    
  def _is_setup_complete(self):
    if not self.torApp or not self.torApp.orPort:
      return False
    return self.torApp.orPort.reachableState == "YES"
    
  def _done_button_cb(self, widget=None):
    """continues if the test succeeded, or launches a dialog to allow a user to bypass the test"""
    if self.lastTestResult:
      self._trigger_event("success")
    else:
      self._launch_click_through_dialog()
    
  def _launch_click_through_dialog(self):
    """launches a dialog that allows the user to continue even with a negative result"""
    text = "The port test did not complete successfully.  If you are certain that you really did forward the port and would like to continue anyway, you can do so.\
  Otherwise, you may want to try again."
    self.controller.show_msgbox(text, title="Do You Really Want to Do That?", cb=self._click_through_dialog_cb, buttons=(gtk.STOCK_CANCEL, 0, gtk.STOCK_OK, 1), width=300)
    
  def _click_through_dialog_cb(self, widget, response):
    """cancels the test and triggers success if the user clicked ok"""
    if response:
      #if the user changed values after running the test, we need to apply them
      for box in (self.relayBox, self.dirBox, self.dhtBox):
        #shouldn't restart tor in the case that the settings haven't changed
        box.apply_value()
      self.torApp.settings.on_apply(self.torApp, "")
      self._trigger_event("success")
    return
    
  def _start_test(self, widget=None):
    self.torApp.start_server()
    for box in (self.relayBox, self.dirBox, self.dhtBox):
      box.apply_value()
    self.torApp.settings.on_apply(self.torApp, "")
    
    self._cancel_test_update()
    self.testUpdateEvent = Scheduler.schedule_repeat(0.1, self._test_update)
    #update the title to reflect the fact that we are currently testing
    self._on_test_started()
    
  def on_update(self):
    #update the status boxes
    self.upnpBox.update()
    for box in (self.relayBox, self.dirBox, self.dhtBox):
      box.update()
    
  def _test_update(self):
    #update progress bar:
    progress = self.progressBar.get_fraction()
    newProgress = progress + 0.01
    if newProgress > 1.0:
      newProgress = 1.0
    self.progressBar.set_fraction(newProgress)
    
    #did the test just succeed?
    if self._is_setup_complete():
      self._on_test_success()
      return False
    #is the test no longer running?  (if tor is no longer a server)
    if not self.torApp.is_server():
      self._on_test_failure()
      return False
    #did the test just fail?
    if self.torApp.orPort.reachableState == "NO":
      self._on_test_failure()
      return False
    #otherwise, keep updating
    else:
      return True
      
  def _cancelled(self, display=None):
    self._trigger_event("failure")
    
  def _on_test_done(self):
    #finish off the progress bar
    self.progressBar.set_fraction(1.0)
    self.progressBar.set_text("Test done.")
    self._cancel_test_update()
    #unlock the buttons and entries:
    #lock all entries until the test is done:
    for entry in (self.relayBox.entry.entry, self.dhtBox.entry.entry, self.dirBox.entry.entry, self.upnpBox.entry.entry):
      entry.set_sensitive(True)
    self.testButton.child.set_markup(BUTTON_MARKUP % ("Restart Test"))
    #self.doneButton.set_sensitive(True)
    #schedule automatically advancing if this wasnt the first test
    #maybe have two buttons--Test and Done.  Both test, just Done auto-advances though
    
  def _cancel_test_update(self):
    if self.testUpdateEvent and self.testUpdateEvent.active():
      self.testUpdateEvent.cancel()
    self.testUpdateEvent = None
    
  def _on_test_started(self):
    self.progressBar.set_fraction(0.0)
    self.progressBar.set_text("Testing...")
    self.lastTestResult = None
    self.set_title_from_test_result()
      
    #lock all entries until the test is done:
    for entry in (self.relayBox.entry.entry, self.dhtBox.entry.entry, self.dirBox.entry.entry, self.upnpBox.entry.entry):
      entry.set_sensitive(False)
    self.testButton.child.set_markup(BUTTON_MARKUP % ("Cancel Test"))
    #self.doneButton.set_sensitive(False)
    self.doneButton.set_label('Continue Anyway')
    
  def _on_test_failure(self):
    self._on_test_done()
    self.lastTestResult = False
    self.set_title_from_test_result()
    self._trigger_event("size_changed")
    
  def set_title_unknown(self):
    self.instructionLabel.set_markup(TITLE_UNTESTED % (self.relayBox.entry.get_value()))
    self.instructionImage.set_from_pixbuf(WARNING_PIXBUF)
  
  def set_title_from_test_result(self):
    if self.lastTestResult == None:
      self.instructionLabel.set_markup(TITLE_TESTING % (self.relayBox.currentPort))
      self.instructionImage.set_from_pixbuf(QUESTION_PIXBUF)
    elif self.lastTestResult == True:
      self.instructionLabel.set_markup(TITLE_SUCCESS % (self.relayBox.currentPort))
      self.instructionImage.set_from_pixbuf(SUCCESS_PIXBUF)
    else:
      self.instructionLabel.set_markup(TITLE_FAILURE % (self.relayBox.currentPort))
      self.instructionImage.set_from_pixbuf(WARNING_PIXBUF)
    
  def _on_test_success(self):
    self._on_test_done()
    self.lastTestResult = True
    self.set_title_from_test_result()
    self.doneButton.set_label('Continue')
    self._trigger_event("size_changed")
  
  def _make_instruction_box(self):
    """Create a box that tells the user what to do in order to set up a relay, 
    with links to get help if they are confused."""
    #make the instructions
    self.instructionLabel = gtk.Label()
    self.instructionImage = gtk.Image()
    instructionBox = gtk.HBox(spacing=PADDING)
    instructionBox.pack_start(self.instructionImage, False, False, 0)
    instructionBox.pack_start(self.instructionLabel, False, False, 0)
    descriptionLabel = WrapLabel.WrapLabel("You must enable UPnP in your router or forward the port manually to be a relay.  Otherwise, peers cannot send traffic through your computer.\n\nAlso remember to unblock BitBlinder.exe and Tor.exe in any firewall.")
    
    #make help link row
    routerAccessLink = GTKUtils.make_html_link("Access your router", "")
    portForwardingLink = GTKUtils.make_html_link("How do I forward a port?", "")
    linkRow = gtk.HBox()
    linkRow.pack_start(portForwardingLink, True, True, 0)
    linkRow.pack_start(routerAccessLink, True, True, 0)
    
    testingBox = self._make_test_bar()
    
    #pack everything together
    box = gtk.VBox(spacing=PADDING)
    box.pack_start(instructionBox, False, False, 0)
    box.pack_start(testingBox, False, False, 0)
    box.pack_start(descriptionLabel, False, False, 0)
    box.pack_start(linkRow, False, False, 0)
    box.show_all()
    return box
    
  def _make_required_ports_box(self):
    """Make a box containing the settings and status for all required ports (currently just the Relay port)"""
    #make entry rows
    self.relayBox = RelayPortStatusBox("Relay Port (TCP)", "orPort", self)
    self.upnpBox = UPnPStatusBox("UPnP")
    
    #pack them together:
    box = gtk.VBox(spacing=PADDING)
    box.pack_start(self.relayBox, False, False, 0)
    box.pack_start(self.upnpBox, False, False, 0)
    box = GTKUtils.add_padding(box, PADDING)
    frame = GTKUtils.add_frame(box, name="Relay Port", width=0)
    frame.show_all()
    return frame
    
  def _make_optional_ports_box(self):
    """Make a box containing the settings and status for all optional ports (DHT and Dir)"""
    #make entry rows
    instructions = WrapLabel.WrapLabel("These ports perform minor misc functions that are helpful to other BitBlinder users.  Set to 0 to disable.")
    self.dhtBox = PortStatusBox("Relay Port (UDP)", "dhtPort")
    self.dirBox = PortStatusBox("Dir Port (TCP)", "dirPort")
    
    #make a box for hiding these entry rows
    optionalPortsBox = gtk.VBox(spacing=PADDING)
    optionalPortsBox.pack_start(instructions, False, False, 0)
    optionalPortsBox.pack_start(self.dhtBox, False, False, 0)
    optionalPortsBox.pack_start(self.dirBox, False, False, 0)
    optionalPortsBox = GTKUtils.add_padding(optionalPortsBox, PADDING)
    optionalPortsBox.show_all()
    #make a frame with a built-in expander for showing and hiding these entry rows
    frame = OptionalToggleFrame.OptionalToggleFrame(optionalPortsBox, "Optional Ports")
    return frame
    
  def _make_button_box(self):
    #make the buttons:
    self.cancelButton = gtk.Button(" ")
    self.cancelButton.connect("clicked", self._cancelled)
    self.cancelButton.child.set_markup(BUTTON_MARKUP % ("Stop Server"))
    self.testButton = gtk.Button(" ")
    self.testButton.connect("clicked", self._restart_test_cb)
    self.testButton.child.set_markup(BUTTON_MARKUP % ("Restart Test"))
    self.doneButton = gtk.Button(" ")
    self.doneButton.connect("clicked", self._done_button_cb)
    self.doneButton.child.set_markup(BUTTON_MARKUP % ("Continue"))
    
    #make the container:
    box = gtk.HBox()
    box.pack_end(self.doneButton, False, False, 0)
    box.pack_end(self.testButton, False, False, 0)
    box.pack_start(self.cancelButton, False, False, 0)
    box.show_all()
    return box
    
  def _make_test_bar(self):
    self.progressBar = gtk.ProgressBar()
    self.progressBar.set_text("Testing")
    self.progressBar.show()
    return self.progressBar
    
class StatusBox(gtk.HBox):
  def __init__(self, rowName):
    gtk.HBox.__init__(self, spacing=15)
    #make the elements of the row
    self.label = gtk.Label()
    self.label.set_markup("<span size='large' weight='bold'>%s</span>" % (rowName))
    self.label.set_alignment(0.0, 0.5)
    self.statusLabel = gtk.Label()
    self.statusLabel.set_markup(UNKNOWN_MARKUP)
    self.statusImage = gtk.Image()
    self.statusImage.set_from_pixbuf(Images.YELLOW_CIRCLE)
    self._make_entry()
    
    #add the elements to the row:
    self.pack_start(self.label, False, False, 0)
    self.pack_start(self.entry.entry, False, False, 0)
    self.pack_start(self.statusImage, False, False, 0)
    self.pack_start(self.statusLabel, False, False, 0)
    
class UPnPStatusBox(StatusBox):
  def _make_entry(self):
    self.entry = SettingsDisplay.make_entry("bool", True)
    self.entry.entry.connect("toggled", self._entry_changed)
    
  def _entry_changed(self, widget, *args):
    self.update()
    
  def update(self):
    torApp = Tor.get()
#    #is upnp even supported on this platform?
#    if not System.IS_WINDOWS:
#      self.statusImage.set_from_pixbuf(Images.GREY_CIRCLE)
#      self.statusLabel.set_markup(STATUS_MARKUP % ("Not supported in linux"))
#    #update UPnP label based on the result of the port tests
#    else:
    upnpSucceeded = False
    upnpFailed = False
    for portObj in (torApp.orPort, torApp.dirPort, torApp.dhtPort):
      if portObj:
        if portObj.upnpState == "YES":
          upnpSucceeded = True
        elif portObj.upnpState == "NO":
          upnpFailed = True
    if upnpSucceeded:
      self.statusImage.set_from_pixbuf(Images.GREEN_CIRCLE)
      self.statusLabel.set_markup(STATUS_MARKUP % ("Succeeded"))
    elif upnpFailed:
      self.statusImage.set_from_pixbuf(Images.RED_CIRCLE)
      self.statusLabel.set_markup(STATUS_MARKUP % ("Failed.  Please enable UPnP in your router."))
    else:
      self.statusImage.set_from_pixbuf(Images.YELLOW_CIRCLE)
      self.statusLabel.set_markup(UNKNOWN_MARKUP)
    
class PortStatusBox(StatusBox):
  def __init__(self, rowName, portObjName):
    StatusBox.__init__(self, rowName)
    self.portObjName = portObjName
    self.currentPort = None
    
  def _make_entry(self):
    self.entry = SettingsDisplay.make_entry(Globals.PORT_RANGE, 0)
    self.entry.entry.connect("changed", self._entry_changed)

  def _entry_changed(self, widget, *args):
    self.entry.entry.update()
    self.update()

  def apply_value(self):
    self.currentPort = self.entry.get_value()
    setattr(Tor.get().settings, self.portObjName, self.currentPort)
    
  def initialize(self):
    self.entry.set_value(getattr(Tor.get().settings, self.portObjName))
    
  def update(self):
    portObj = getattr(Tor.get(), self.portObjName)
    if not portObj or self.entry.get_value() == 0:
      self.statusImage.set_from_pixbuf(Images.GREY_CIRCLE)
      self.statusLabel.set_markup(STATUS_MARKUP % ("Disabled"))
      return
    if self.entry.get_value() != portObj.get_port():
      self.statusImage.set_from_pixbuf(Images.YELLOW_CIRCLE)
      self.statusLabel.set_markup(UNKNOWN_MARKUP)
    elif portObj.reachableState == "YES":
      self.statusImage.set_from_pixbuf(Images.GREEN_CIRCLE)
      self.statusLabel.set_markup(STATUS_MARKUP % ("Reachable"))
    elif portObj.reachableState == "NO":
      self.statusImage.set_from_pixbuf(Images.RED_CIRCLE)
      self.statusLabel.set_markup(STATUS_MARKUP % ("Not reachable"))
    else:
      self.statusImage.set_from_pixbuf(Images.YELLOW_CIRCLE)
      self.statusLabel.set_markup(UNKNOWN_MARKUP)
      
class RelayPortStatusBox(PortStatusBox):
  def __init__(self, rowName, portObjName, serverSetupWindow):
    PortStatusBox.__init__(self, rowName, portObjName)
    self.serverSetupWindow = serverSetupWindow
    
  def _entry_changed(self, widget, *args):
    self.update()
    portObj = getattr(Tor.get(), self.portObjName, None)
    if not portObj:
      return
    if self.entry.get_value() != portObj.get_port():
      self.serverSetupWindow.set_title_unknown()
    else:
      self.serverSetupWindow.set_title_from_test_result()
