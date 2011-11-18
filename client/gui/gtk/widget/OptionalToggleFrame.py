#!/usr/bin/python
#Copyright 2009 InnomiNet
"""Frame which can be toggled to show or hide its contents"""

import gtk

from gui.gtk.utils import GTKUtils

class OptionalToggleFrame(gtk.Frame):
  """A frame with a toggle button and a title that can show or hide its contents"""
  def __init__(self, contents, title=None, startHidden=True):
    """contents should be a container of some sort to be packed into the frame
    @param title: the frame title of course
    @type title: string"""
    gtk.Frame.__init__(self)
    self.contents = contents
  
    #make a box for hiding
    self.contentBox = gtk.VBox()
    self.contentBox.pack_start(self.contents, True, True, 0)
    self.add(self.contentBox)
    
    #make a built-in expander for showing and hiding the contents
    frameWidget = gtk.Expander(title)
    frameWidget.connect("notify::expanded", self._toggle_content_box)
    self.set_label_widget(frameWidget)
    
    self.show_all()
    if startHidden:
      self.contentBox.hide()
    
  def _toggle_content_box(self, expander, param_spec):
    """shows or hides the contents"""
    if expander.get_expanded():
      self.contentBox.show_all()
    else:
      self.contentBox.hide()
    
    GTKUtils.refit(self)
    
