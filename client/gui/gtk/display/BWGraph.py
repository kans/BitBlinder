#!/usr/bin/python
#Copyright 2009 InnomiNet
"""Display a graph of bandwidth using cairo"""
import math

import pygtk
pygtk.require('2.0')
import gtk, gobject
import cairo

from common import Globals
from common.system import System
from common.classes import Scheduler
from common.events import GlobalEvents
from common.utils import Format
from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.utils import GTKUtils

#Draw a graph of up and downstream bandwidth in response to an expose-event.
#Might be nice to abstract this class in the future to handle different graphs
class BWGraph(gtk.DrawingArea, GlobalEvents.GlobalEventMixin):
  __gsignals__ = { "expose-event": "override" }
  
  def __init__(self, dataSource, useLabels=True, fontSize=12.0, lineWidth=4, paddingLeft=7,
               paddingRight=10, paddingTop=10, paddingBottom=10, paddingAxis=10,
               numHorLines=4, numVerLines=6, numValues=60, xMiddleTics=0,
               yMiddleTics=0, showRemoteTraffic=True, root=None):
    gtk.DrawingArea.__init__(self)
    self.catch_event('palette_known')
    #set some temporary colors 
    self.cFill = (0, 0, 0)
    self.text = (0, 0, 0)
    self.cInnerShade = (0, 0, 0)
    self.cLines = (0, 0, 0)
    self.cWritten = (0, 0, 0)
    self.cRead = (0, 0, 0)
    
    self.root = root
    self.dataSource = dataSource
    self.set_palette = False
    self.show()
    self.useLabels = useLabels
    self.FONT_SIZE = fontSize
    self.PADDING_LEFT = paddingLeft
    self.PADDING_RIGHT = paddingRight
    self.PADDING_TOP = paddingTop
    self.PADDING_BOTTOM = paddingBottom
    self.PADDING_AXIS = paddingAxis
    self.NUM_HORIZ_LINES = numHorLines
    self.NUM_VERT_LINES = numVerLines
    self.lineWidth = lineWidth
    self.xMiddleTics = xMiddleTics
    self.yMiddleTics = yMiddleTics
    self.showRemoteTraffic = showRemoteTraffic
    #Initial maximum y value is 32KB
    self.maxVal = 1024 * 32
    #Indicates that the scale of the Y axis is much larger than all of the data values
    self.scale_too_big = 0
    #whether we should start drawing or not
    self.shouldDraw = False
    
    self.NUM_VALUES = numValues
    
    #these are used when adding this component to the main GUI
    self.label = gtk.Label("Bandwidth Graph")
    self.container = self
    self.show()
  
#  def on_palette_known(self, palette):
#    self.cFill, self.text, self.cInnerShade, self.cLines, self.cWritten, self.cRead = palette[0]
    
  def visible_cb(self):
    if self.set_palette:
      return
    def hex_to_rbg(color):
      """convert for digit hex strings to 0-1 rgb"""
      return int(color, 16)/float(int('ffff', 16))
      
    style = self.root.get_style()
    #grab some colors
    colors = [style.fg[0], style.fg[1], style.fg[2], style.fg[3], style.fg[4], 
              style.bg[0], style.bg[1], style.bg[2], style.bg[3], style.bg[4],
              style.base[0], style.base[1], style.base[2], style.base[3], style.base[4]]
    #convert to hex strings and drop leading char
    palette = []
    try:
      colors = [c.to_string()[1:] for c in colors]
      #split into components
      colors = [[c[0:4], c[4:8], c[8:12]] for c in colors]
      convertedColors = []
      for subColor in colors:
        convertedColors.append(tuple([hex_to_rbg(c) for c in subColor]))
      
      #get the colors we want
      if System.IS_WINDOWS:
        #aurora theme, our choice for windows, has a gradient on notebook leaves that makes
        #this color offensive without a correction
        palette.append(tuple([1.02*c for c in convertedColors[9]]))
      else:
        #use the gtk rc defined theme- I don't think windows users will be changing the theme too often...
        palette.append(tuple(convertedColors[9]))
      palette.append((0, 0, 0)) #text
      palette.append((1, 1, 1)) #shading color
      palette.append(tuple(convertedColors[4])) #line color
      palette.append((0,0,0)) #write color
      #read and write colors can't be the same, nor can read be white or black
      s = False
      for i in convertedColors:
        if i != (0.0, 0.0, 0.0) and i != (1.0, 1.0, 1.0):
          palette.append(tuple(i))
          s = True
          break
      #fall back to a default otherwise...
      if not s:
        palette.append((.2, .2, .2))
    except Exception, e:
      #older versions of pygtk don't have __str__ on colors
      palette.append((1, 1, 1)) 
      palette.append((.2, .2, .2))
      palette.append((1, 1, 1)) 
      palette.append((0, 0, 0)) #write color
      palette.append((0, 0, 0)) #line color
      palette.append((.7, .7, .7))
#    GlobalEvents.throw_event('palette_known', [palette])
    self.set_palette = True
    self.cFill, self.text, self.cInnerShade, self.cLines, self.cWritten, self.cRead = palette
    
  #Handle the expose-event by drawing
  def do_expose_event(self, event):
    #schedule the draw event if this is the first time we've ever been exposed
    if not self.shouldDraw:
      self.shouldDraw = True
      Scheduler.schedule_repeat(1.0, self.draw)
    self.visible_cb()
    #Create the cairo context
    self.cr = self.window.cairo_create()
    #Restrict Cairo to the exposed area; avoid extra work
    self.cr.rectangle(event.area.x, event.area.y, event.area.width, event.area.height)
    self.cr.clip()
    width, height = self.window.get_size()
    cr = self.cr

    cr.set_source_rgb(*self.cFill)
    cr.rectangle(0, 0, width, height)
    cr.fill()
    
    #figure out the scale mapping between values and pixels:
    maxYVal = self.maxVal
    maxValueText, maxValueUnits = Format.bytes_per_second(maxYVal).split(" ")
    x_bearing, y_bearing, w, h = cr.text_extents(maxValueText)[:4]
    xStart = w + self.PADDING_LEFT + self.PADDING_AXIS
    xEnd = width - self.PADDING_RIGHT 
    xStepSize = float(xEnd - xStart) / float(self.NUM_VALUES)
    x_bearing, y_bearing, w, h = cr.text_extents("100MB/s")[:4]
    bottomY = height - (self.PADDING_BOTTOM + h + self.PADDING_AXIS)
    yScale = float(bottomY - self.PADDING_TOP) / float(maxYVal)
    
    #shade enclosed rectangle white
    cr.set_source_rgb(self.cInnerShade[0], self.cInnerShade[1], self.cInnerShade[2])
    cr.rectangle(xStart, self.PADDING_TOP, width-self.PADDING_RIGHT-xStart, bottomY-self.PADDING_TOP)
    cr.fill()
    
    #labels
    cr.set_line_width(0.6)
    cr.set_font_size(self.FONT_SIZE)
    
    #vertical lines:
    numLines = self.NUM_VERT_LINES
    cr.set_source_rgb(self.cLines[0], self.cLines[1], self.cLines[2])
    if self.xMiddleTics:
      numLines = (numLines * (self.xMiddleTics+1))
    for i in range(0, numLines + 1):
      if self.xMiddleTics:
        if i % (1+self.xMiddleTics) == 0:
          cr.set_line_width(0.6)
        else:
          cr.set_line_width(0.2)
      s = (self.NUM_VALUES / numLines) * i
      #should be a dark color...
      x = xStart + int(xStepSize * s)
      cr.move_to(x, self.PADDING_TOP)
      cr.line_to(x, bottomY)
      cr.stroke()

    x_bearing, y_bearing, w, h = cr.text_extents("Time (1 second step)")[:4]
    yPos = bottomY + self.PADDING_AXIS + h - self.lineWidth
    #make left label:
    cr.move_to(xStart, yPos)
    cr.show_text("Time (1 second step)")
        
    #middle label:
    x_bearing, y_bearing, w, h = cr.text_extents("Grid: 10 seconds")[:4]
    cr.move_to((xStart+xEnd)/2 - w/2, yPos)
    cr.show_text("Grid: 10 seconds")
    
    #make right label:
    x_bearing, y_bearing, w, h = cr.text_extents("Now")[:4]
    cr.move_to(xEnd-w, yPos)
    cr.show_text("Now")

    #horizontal lines:
    cr.set_source_rgb(self.cLines[0], self.cLines[1], self.cLines[2])
    numLines = self.NUM_HORIZ_LINES
    if self.yMiddleTics:
      numLines = (numLines * (self.yMiddleTics+1))
    j = 0
    for i in range(0,maxYVal+1,maxYVal/numLines):
      if self.yMiddleTics:
        if j % (1+self.yMiddleTics) == 0:
          cr.set_line_width(0.6)
        else:
          cr.set_line_width(0.2)
        j += 1
      #should be a dark color...
      y = bottomY - int(yScale * i)
      cr.move_to(xEnd, y)
      cr.line_to(xStart, y)
      cr.stroke()
        
    #make top label:
    x_bearing, y_bearing, w, h = cr.text_extents("0")[:4]
    cr.move_to(self.PADDING_LEFT, self.PADDING_TOP+h)
    cr.show_text(maxValueText)
        
    #middle label:
    self.cr.rotate(-1*math.pi / 2.0)
    x_bearing, y_bearing, w, h = cr.text_extents(maxValueUnits)[:4]
    cr.move_to(-1 * height / 2.0 - w/2 + self.PADDING_TOP, self.PADDING_LEFT + h + 2)
    cr.show_text(maxValueUnits)
    self.cr.rotate(math.pi / 2.0)
    
    #make bottom label:
    x_bearing, y_bearing, w, h = cr.text_extents("0")[:4]
    cr.move_to(xStart-self.PADDING_AXIS-w, bottomY)
    cr.show_text("0")

    #draw the data lines on the graph:
    for sourceVals in (self.dataSource.bytesRead, self.dataSource.bytesWritten):
      # Set properties for the line (different colors for read and written)
      if sourceVals == self.dataSource.bytesWritten:
        cr.set_source_rgb(self.cWritten[0], self.cWritten[1], self.cWritten[2])
      else:
        cr.set_source_rgb(self.cRead[0], self.cRead[1], self.cRead[2])
      cr.set_line_width(self.lineWidth)
      #for every bw value,
      vals = sourceVals[len(sourceVals)-self.NUM_VALUES:]
      for i in range(0, len(vals)-1):
        #draw a line segment:
        startX = xStart + int(xStepSize * i)
        endX = xStart + int(xStepSize * (i+1))
        y1 = bottomY - (vals[i] * yScale)
        y2 = bottomY - (vals[i+1] * yScale)
        cr.move_to(startX, y1)
        cr.line_to(endX, y2)
      #Apply the ink
      cr.stroke()
      #update the maximum y value and scale for next time:
      newMax = 0
      for v in vals:
        if v > newMax:
          newMax = v
      #double the scale until we contain the max value:
      while newMax > self.maxVal:
        self.maxVal *= 2
      else:
        if newMax < self.maxVal / 2:
          self.scale_too_big += 1
        else:
          self.scale_too_big = 0
      #if the scale has been too big for more than 5 ticks, make it smaller
      if self.scale_too_big > 5:
        #dont go below the original axis value:
        if self.maxVal > 32 * 1024:
          self.maxVal /= 2

  #Ask to be updated sometime in the near future:
  def draw(self):
    if self.shouldDraw:
      if GTKUtils.is_visible(self):
        self.queue_draw()
    return True
  
  