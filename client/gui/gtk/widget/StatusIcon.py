#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""For controlling a GTK StatusIcon"""

import time
import os
import sys
import pygtk
import gtk
import gobject
 
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.classes import Scheduler
from common.events import GlobalEvents
from common.events import GeneratorMixin
from gui import GUIController
from Applications import BitBlinder

class StatusIcon(gtk.StatusIcon, GlobalEvents.GlobalEventMixin, GeneratorMixin.GeneratorMixin):
  """Our GTK StatusIcon"""
  def __init__(self, iconFile):
    gtk.StatusIcon.__init__(self)
    GeneratorMixin.GeneratorMixin.__init__(self)
    self._add_events("activated", "popup")
    
    #: last window the user hovered over (and left)
    self.windowLeft = None
    self.popupMenu = None
    self.allMenus = []
    self.isHoveringOverMenu = False
    self.lastHoveredOverMenu = 0

    self.set_from_file(iconFile)
    self.connect("popup-menu", self.icon_menu_cb)
    self.connect("activate", self.icon_activate_cb)
    self.catch_event("shutdown")
    self.set_visible(False)
    
  def start(self):
    self.set_visible(True)
    
  def stop(self):
    self.set_visible(False)
    
  def on_shutdown(self, *args):
    self.set_visible(False)
    
  def icon_activate_cb(self, status_icon):
    """unminimizies and shows the window if the user left clicks the icon."""
    log_msg("status_activate", 4, "gui")
    self._trigger_event("activated")
    
  def icon_menu_cb(self, status_icon, button, activate_time):
    """creates a drop down menu on the system tray icon when right clicked hopefully
    pay attention: both the popup menu and the menu list are passed to the trigger,
    which adds to both with new menuitems"""
    if self.popupMenu:
      self.popupMenu.destroy()
    
    self.popupMenu = gtk.Menu()
    self.allMenus = []
    #note, popupMenu and menus are changed externally....
    self._trigger_event("popup", self.popupMenu, self.allMenus)
      
    self.popupMenu.show()

    self.popupMenu.popup(None, None, None, button, activate_time)
      
#    self.popupMenu.connect("selection-done", self._recursive_menu_activate)

    def on_click(menu, event, popupMenu):
      if popupMenu != self.popupMenu:
        return
      log_msg("clicked %s %s" % (event.x, event.y), 4)
      if self.bestWidget:
        self.bestWidget.emit("activate")
      else:
        children = menu.get_children()
        if len(children) > 0:
          children[0].emit("activate")
      self._hide_popup_menu()
      return True
#    def debugprint(widget, eventName):
#      log_msg(eventName)
    for menuItem in self.popupMenu.get_children():
#      for eventName in ("activate", "activate-item"):
#        menuItem.connect(eventName, debugprint, eventName)
      submenu = menuItem.get_submenu()
      if submenu:
        self.popupMenu.window.set_events(gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.ENTER_NOTIFY_MASK | gtk.gdk.LEAVE_NOTIFY_MASK | gtk.gdk.EXPOSURE_MASK | gtk.gdk.STRUCTURE_MASK)
        submenu.connect('button_press_event', on_click, self.popupMenu)
#        for eventName in ("activate-current", "selection-done"):
#          submenu.connect(eventName, debugprint, eventName)
#    self.popupMenu.window.set_events(gtk.gdk.BUTTON_PRESS_MASK)
#    for eventName in ("activate-current", "selection-done"):
#      self.popupMenu.connect(eventName, debugprint, "parent"+eventName)
#    self.popupMenu.connect('button_press_event', on_click)

    self.bestWidget = None

    self.isHoveringOverMenu = False
    self.lastHoveredOverMenu = time.time()
    
#    self.popupMenu.window.raise_()
#    self.popupMenu.window.set_accept_focus(True)
##    self.popupMenu.window.focus()
#    self.popupMenu.window.set_modal_hint(True)

    #need to kill the popup when the mouse leaves... menus was populated in the triggered events
    self.allMenus.append(self.popupMenu)
    for menu in self.allMenus:
      menu.connect("enter_notify_event", self._on_hover_over_menu)
      menu.connect("leave_notify_event", self._on_leave_menu)
      if menu != self.popupMenu:
        for child in menu.get_children():
          child.connect("enter_notify_event", self._on_hover_over_widget)
          child.connect("leave_notify_event", self._on_leave_widget)
    
    Scheduler.schedule_repeat(0.1, self._fade_out_window)
    
  def _on_hover_over_widget(self, widget, event):
    log_msg("entered %s" % (widget.child.get_text()))
    self.bestWidget = widget
    
  def _on_leave_widget(self, widget, event):
    log_msg("exited %s" % (widget.child.get_text()))
    self.bestWidget = None
    
  def _recursive_menu_activate(self, menu):
    if not menu:
      return False
    activeItem = menu.get_active()
    if not activeItem:
      return False
    activeSubmenu = activeItem.get_submenu()
    didSubmenuHandle = False
    if activeSubmenu:
      didSubmenuHandle = self._recursive_menu_activate(activeSubmenu)
    if didSubmenuHandle:
      return True
    #otherwise, try handling it ourself:
    activeItem.emit("activate")
    return True
    
  def _on_hover_over_menu(self, window, event):
#    log_msg("entered")
    self.isHoveringOverMenu = True
      
  def _on_leave_menu(self, window, event):
#    log_msg("exited")
    self.isHoveringOverMenu = False
    self.lastHoveredOverMenu = time.time()
    self.windowLeft = window
    
  def _fade_out_window(self):
    #the popup menu and parent must exist 
    if not self.popupMenu:
      return False
    
    fadeSubMenu = False
    #if the widget left was a submenu, 
    if self.windowLeft != self.popupMenu:
      fadeSubMenu = True
    
    popupMenuWindow = self.popupMenu.get_parent()
    #parent must exist...
    if not popupMenuWindow:
      return False
      
    if self.isHoveringOverMenu:
      self._set_submenu_opacity(1.0)
      return True
    if time.time() - self.lastHoveredOverMenu < 0.3:
      self._set_submenu_opacity(1.0)
      return True
    if not popupMenuWindow:
      return False
    currentOpacity = popupMenuWindow.get_opacity()
    newOpacity = currentOpacity - 0.1
    if newOpacity <= 0:
      self._hide_popup_menu()
      return False
    self._set_submenu_opacity(newOpacity)
    return True
    
  def _hide_popup_menu(self):
    if self.popupMenu:
      self.popupMenu.popdown()
      self.popupMenu.get_parent().hide()
    self.popupMenu = None
    
  def _set_submenu_opacity(self, opacity):
    for menu in self.allMenus:
      parentWindow = menu.get_parent()
      if parentWindow:
        parentWindow.set_opacity(opacity)
    
#    def _fade_out_window(self):
#    #the popup menu and parent must exist 
#    if not self.popupMenu:
#      return False
#    popupMenuWindow = self.popupMenu.get_parent()
#   #parent must exist...
#    if not popupMenuWindow:
#      return False
#      
#    if self.isHoveringOverMenu:
#      popupMenuWindow.set_opacity(1.0)
#      return True
#    if time.time() - self.lastHoveredOverMenu < 0.3:
#      popupMenuWindow.set_opacity(1.0)
#      return True
#    if not popupMenuWindow:
#      return False
#    currentOpacity = popupMenuWindow.get_opacity()
#    newOpacity = currentOpacity - 0.1
#    if newOpacity <= 0:
#      self.popupMenu.popdown()
#      self.popupMenu = None
#      popupMenuWindow.hide()
#      return False
#    popupMenuWindow.set_opacity(newOpacity)
#    return True
    
