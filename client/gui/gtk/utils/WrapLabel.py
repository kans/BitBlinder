#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Misc. GUI functions"""

import gtk
import pango

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611

class WrapLabel(gtk.Label):
  """A GTK Label that does word-wrapping"""
  __gtype_name__ = 'WrapLabel'

  def __init__(self, text=None):
    gtk.Label.__init__(self)
    self.__wrap_width = 0
    self.layout = self.get_layout()
    self.layout.set_wrap(pango.WRAP_WORD_CHAR)
    if text != None:
      self.set_text(text)
    self.set_alignment(0.0, 0.0)
  
  def do_size_request(self, requisition):
    layout = self.get_layout()
    width, height = layout.get_pixel_size()
    requisition.width = 0
    requisition.height = height

  def do_size_allocate(self, allocation):
    gtk.Label.do_size_allocate(self, allocation)
    self.__set_wrap_width(allocation.width)
  
  def set_text(self, text):
    gtk.Label.set_text(self, text)
    self.__set_wrap_width(self.__wrap_width)
      
  def set_markup(self, text):
    gtk.Label.set_markup(self, text)
    self.__set_wrap_width(self.__wrap_width)
  
  def __set_wrap_width(self, width):
    if width == 0:
      return
    layout = self.get_layout()
    layout.set_width(width * pango.SCALE)
    if self.__wrap_width != width:
      self.__wrap_width = width
      self.queue_resize()
      
  def get_wrap_width(self):
    return self.__wrap_width
      
