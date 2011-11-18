#!/usr/bin/python
#Copyright 2009 InnomiNet
"""Show settings for client, relay, and applications"""

import gtk
import gobject

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common import Globals
from common.events import GlobalEvents
from core import ProgramState
from gui.gtk.utils import GTKUtils
from gui.gtk.display import SettingsDisplay

class SettingsDialog(GlobalEvents.GlobalEventMixin):
  def __init__(self, applications, root):
    """Responsible for user interface to settings.
    @param applications: BitBlinder applications to show settings for
    @type applications: list
    @param showGlobalSettings: Bool to show the global settings- ie, username and pw
    """
    #: settings name to application instance
    self.applications = applications
    #create the dialog:
    self.dia = gtk.Dialog("Settings", root, gtk.DIALOG_DESTROY_WITH_PARENT, None)
    #: the collection of displays, organized as [appName][categoryName]
    self.settingsDisplays = {}
    
    #: the Application that corresponds to the currently selected row on the left
    self.selectedApp = None
    #: the SettingsDisplay that corresponds to the currently selected row on the left
    self.selectedDisplay = None
    #: the settings category that corresponds to the currently selected row on the left
    self.selectedCategory = None
    
    self.mdl = gtk.TreeStore(gobject.TYPE_STRING)
    self.view = gtk.TreeView(self.mdl)
    #make column
    column = gtk.TreeViewColumn("Category")
    #basic string renderer for the data in the column
    column.cell = gtk.CellRendererText()
    #add the renderer to the column...  idk if you can add more than one
    column.pack_start(column.cell, True)
    #add the column to the treeview
    self.view.append_column(column)
    column.set_attributes(column.cell, text=0)
    self.view.connect("cursor-changed", self.row_changed)
    
    #Make the apply/ok/cancel buttons:
    i = 1
    #for name in ("Ok", "Apply", "Defaults", "Cancel"):
    for name in ("Ok", "Apply", "Cancel"):
      self.prevButton = self.dia.add_button(name, i)
      i += 1
    
    #glue:
    self.hbox = gtk.HBox()
    vbox = gtk.VBox()
    vbox.pack_start(self.hbox, True, True, 0)
    self.hbox.show()
    
    hbox = gtk.HBox()
    align = gtk.Alignment(xalign=0.5, yalign=0.5, xscale=1.0, yscale=1.0)
    align.add(GTKUtils.add_frame(self.view))
    align.set_padding(0, 0, 10, 0)
    align.show_all()
    hbox.pack_start(align, False, False, 0)
    hbox.pack_end(vbox, True, True, 0)
    hbox.show()
    vbox.show()
    
    for name, app in self.applications.iteritems():
      #create the application row:
      self.settingsDisplays[app.get_settings_name()] = {}
      rowIter = self.mdl.append(None, [app.get_settings_name()])
      #make permanent reference for the row:
      app.settingsTreeRow = gtk.TreeRowReference(self.mdl, self.mdl.get_string_from_iter(rowIter))
      #make each subcategory:
      for category in app.settings.categories.keys():
        self.settingsDisplays[app.get_settings_name()][category] = SettingsDisplay.SettingsDisplay(app.settings, category)
        if category == "":
          continue
        if category == "DEV" and not ProgramState.DEBUG:
          continue
        self.mdl.append(rowIter, [category])
    
    self.dia.vbox.pack_start(hbox, True, True, 10)
    #connect the handler:
    self.dia.connect("response", self.on_response)
    #self.dia.connect("destroy", self.destroy_cb)
    self.dia.connect('delete-event', self.hide)
    #start the dialog
    self.dia.vbox.set_size_request(700, 500)
    self.dia.show()
    
  def hide(self, dialog=None, event=None) :
    self.dia.hide()
    return True

  def show(self, callback = None):
    for app in self.applications.values():
      for category in app.settings.categories.keys():
        self.settingsDisplays[app.get_settings_name()][category].clear()
    #self.dia.vbox.set_size_request(700, 500)
    self.dia.show()
    
  def set_app(self, app, category=""):
    if not app:
      appString = "General"
    else:
      appString = app.get_settings_name()
    def find_app(model, path, rowIter):
      #are we looking for a general category?
      if category == "":
        #just have to match the appString:
        if len(path) == 1 and model.get_value(rowIter, 0) == appString:
          self.view.set_cursor(path)
      #must be looking for a specific category underneath an app, match both:
      else:
        if len(path) == 2:
          iterParent = model.iter_parent(rowIter)
          #match both the category and appString
          if model.get_value(rowIter, 0) == category and model.get_value(iterParent, 0) == appString:
            self.view.set_cursor(path)
    self.mdl.foreach(find_app)
      
  def row_changed(self, treeview):
    #get the selection
    sel = treeview.get_selection()
    #get the selected row
    model, rowIter = sel.get_selected()
    if not rowIter:
      return
    #figure out what level:
    path = model.get_path(rowIter)
    self.selectedCategory = ""
    if len(path) > 1:
      self.selectedCategory = model.get_value(rowIter, 0)
      rowIter = model.iter_parent(rowIter)
    appName = model.get_value(rowIter, 0)
    self.selectedApp = self.applications[appName]
    self.selectedDisplay = self.settingsDisplays[appName][self.selectedCategory]
    #clear the current content:
    children = self.hbox.get_children()
    for child in children:
      self.hbox.remove(child)
    self.selectedDisplay.clear_parent()
    self.hbox.pack_start(self.selectedDisplay.container, True, True, 10)
    
  #handle the result of the dialog:
  def on_response(self, dialog, response_id):
    #Apply all changes, starting with app.  End on the first tab that fails, otherwise return to the main GUI.
    if response_id == 1:
      if not self.apply_all():
        return
    #apply all changes for the selected app
    elif response_id == 2:
      self.selectedDisplay.apply(self.selectedApp)
      return
    ##revert to default values:
    #elif response_id == 3:
    #  self.selectedApp.settings.reset_defaults()
    #  return
    #Just close the dialog without apply any changes.
    elif response_id == 3 or response_id == gtk.RESPONSE_DELETE_EVENT:
      pass
    else:
      raise Exception("Got bad response id (%s) for SettingsDialog!" % (response_id))
    self.hide()
    
  def apply_all(self):
    #apply to the current screen:
    if self.selectedApp and not self.selectedDisplay.apply(self.selectedApp):
      return False
    #apply the other categories for this app:
    for category in self.selectedApp.settings.categories.keys():
      #already did this category:
      if category == self.selectedCategory:
        continue
      #if we fail to apply
      settingsDisplay = self.settingsDisplays[self.selectedApp.get_settings_name()][category]
      if not settingsDisplay.apply(self.selectedApp):
        #select the place we failed and return
        self.set_app(self.selectedApp, category)
        return False
    #then save to disk:
    self.selectedApp.settings.save()
    #apply to the rest of the apps:
    for app in self.applications.values():
      #already did this app:
      if app == self.selectedApp:
        continue
      #apply to each category for this app:
      for category in app.settings.categories.keys():
        #if we fail to apply
        settingsDisplay = self.settingsDisplays[app.get_settings_name()][category]
        if not settingsDisplay.apply(app):
          #select the place we failed and return
          self.set_app(app, category)
          return False
      #then save to disk:
      app.settings.save()
    return True
    
