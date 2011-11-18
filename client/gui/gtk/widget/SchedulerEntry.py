#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Interface for scheduling bandwidth limits"""

import gtk
import time

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from gui.gtk.widget import Entry
from gui.gtk.widget import Entries
from gui.gtk.utils import GTKUtils

class SchedulerEntry(Entry.Entry):
  def make_wrapper(self, nameString, helpString=None, helpSize="small"):
    #create a name label:
    nameLabel = GTKUtils.make_text("<span size='large' weight='bold'>%s</span>" % (nameString))
    #create a help label:
    helpLabel = GTKUtils.make_text("<span size='%s'>%s</span>" % (helpSize, helpString))
    self.errorLabel = GTKUtils.make_text("")
    vbox = gtk.VBox()
    vbox.pack_start(nameLabel, False, False, 5)
    vbox.pack_start(self.get_gtk_element(), True, True, 5)
    vbox.pack_end(self.errorLabel, False, False, 5)
    align = gtk.Alignment(xalign=0.0, yalign=0.5, xscale=1.0, yscale=1.0)
    align.add(helpLabel)
    align.set_padding(15, 0, 0, 0)
    vbox.pack_start(align, True, True, 0)
    vbox.set_spacing(0)
    return vbox
  
  def get_gtk_element(self):
    return self.entry.container
  
  def make_entry(self, range):
    self.entry = Scheduler()
    
  def set_value(self, val):
    self.entry.set_mapping(val)
      
  def get_value(self):
    return self.entry.get_mapping()

class Scheduler():
  """
  Base class for a graphic interface for a scheduler;
  allows the user to limit what the client does at certain weekly recurring times.
  """
  def __init__(self, mapping=None):
    """
    Optionally takes mapping- see get_mapping for formatting
    Other options include the width and height, but you probably shouldn't touch those for now...
    """
    self.limitedUpEntry = Entries.UnitEntry("KBps")
    self.limitedDownEntry = Entries.UnitEntry("KBps")
    
    if not mapping:
      self.downloadLimit = 100
      self.uploadLimit = 100
      self.mapping = [[], [], [], [], [], [], []]
      for i in range(7):
        for j in range(24):
          self.mapping[i].append(0)
    else:
      self.set_mapping(mapping)
      
    self.initialized = False #we need to initialize the gui mapping of the schedule?
    
    self.layout = None
    self.pixmap = None
    self.text = None
    self.previousTime = time.time()
    self.previousBox = []
    
    #warning, these proportions need to be exact- xBlock and yBlock shouldn't have any rounding errors apart from the width wtf?!?
    self.width = 391
    self.height = 130
    self.textOffset = 30
    self.legendOffset = 25
    self.xBlock = int((self.width-self.textOffset)/24) #quantized x unit
    self.yBlock = int((self.height-self.legendOffset)/7) #quantized y unit
    self.drawing_area = gtk.DrawingArea()
    
    #connections
    self.drawing_area.set_size_request(self.width, self.height) #24/7 + 30 : 1
    self.drawing_area.connect("expose_event", self.expose_event)
    self.drawing_area.connect("motion_notify_event", self.motion_notify_event)
    self.drawing_area.connect("button_press_event", self.button_press_event)
    self.drawing_area.connect("leave_notify_event", self.mouse_left)

    self.drawing_area.set_events(gtk.gdk.EXPOSURE_MASK
                            | gtk.gdk.LEAVE_NOTIFY_MASK
                            | gtk.gdk.BUTTON_PRESS_MASK
                            | gtk.gdk.POINTER_MOTION_MASK
                            | gtk.gdk.POINTER_MOTION_HINT_MASK)
    
    self.limitedUpEntry.set_value(self.uploadLimit)
    self.limitedDownEntry.set_value(self.downloadLimit)
    
    vbox = gtk.VBox(False, 0)
    frame = gtk.AspectFrame('Scheduler', ratio=self.width/self.height, obey_child=True)
    self.label = gtk.Label("")
    
    hbox = gtk.HBox(False, 4)
    label = gtk.Label("Limited Upload (0=unlimited)")
    label.show()
    vbox.pack_start(label, False, True, 2)
    entryHBox = gtk.HBox()
    entryHBox.pack_start(self.limitedUpEntry.get_gtk_element(), True, True, 0)
    entryLabel = gtk.Label("")
    entryLabel.set_markup('<span size="large" weight="bold">KBps</span>')
    entryHBox.pack_end(entryLabel, False, False, 0)
    entryHBox.show_all()
    vbox.pack_start(entryHBox, False, True, 0)
    
    sep = gtk.HSeparator()
    sep.show()
    
    label = gtk.Label("Limited Download (0=unlimited)")
    label.show()
    vbox.pack_start(sep, False, True, 6)
    vbox.pack_start(label, False, True, 0)
    entryHBox = gtk.HBox()
    entryHBox.pack_start(self.limitedDownEntry.get_gtk_element(), True, True, 0)
    entryLabel = gtk.Label("")
    entryLabel.set_markup('<span size="large" weight="bold">KBps</span>')
    entryHBox.pack_end(entryLabel, False, False, 0)
    entryHBox.show_all()
    vbox.pack_start(entryHBox, False, True, 0)
    
    sep = gtk.HSeparator()
    sep.show()
    
    vbox.pack_start(sep, False, True, 6)
    vbox.pack_start(self.label, False, True, 0)
    
    hbox.pack_start(self.drawing_area, False, False, 0)
    hbox.pack_start(vbox, False, False, 0)
    
    frame.add(hbox)

    self.drawing_area.show()
    self.limitedDownEntry.get_gtk_element().show()
    self.limitedUpEntry.get_gtk_element().show()
    self.label.show()
    vbox.show()
    hbox.show()
    frame.show()
    self.container = frame #use the hbox above if you want a handle on the child 
    
  def set_mapping(self, jashString):
    """creates the mapping from a Jash string."""
    if not jashString:
      jashString = '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0|0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0||400,400'
    self.mapping = []
    days, limits = jashString.rsplit("||", 1)
    days = days.split("|")
    for day in days:
      self.mapping.append([int(value) for value in day.split(",")]) #cause Jash likes teh Perls
    up, down = limits.split(',')
    self.uploadLimit = int(up)
    self.downloadLimit = int(down)
    self.limitedUpEntry.set_value(self.uploadLimit)
    self.limitedDownEntry.set_value(self.downloadLimit)
    if self.pixmap and self.initialized:
      self.init_drawing_area()

  def get_mapping(self):
    """Makes an easily saveable string out of mapping, but wtf does it do?"""
    self.uploadLimit = self.limitedUpEntry.get_value()
    self.downloadLimit = self.limitedDownEntry.get_value()
    jashString = "|".join(",".join(str(v) for v in r) for r in self.mapping) + ('||%s,%s'%(self.uploadLimit, self.downloadLimit))
    return jashString
    
  def init_drawing_area(self):
    """initializes the drawing area with the mapping"""
    for day, dayValues in enumerate(self.mapping):
      for hour, value in enumerate(dayValues):
        rect = (hour * self.xBlock + self.textOffset, day * self.yBlock, self.xBlock, self.yBlock)
        self.pixmap.draw_rectangle(self.color[value], True, rect[0], rect[1], rect[2], rect[3])
        self.drawing_area.queue_draw_area(rect[0], rect[1], rect[2], rect[3])
    self.draw_grid()
    
  def draw_text(self):
    """writes some text on the pixmap"""
    week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
    layout = self.drawing_area.create_pango_layout("")
    for count, day in enumerate(week):
      #layout.set_alignment(pango.ALIGN_RIGHT)
      layout.set_text(day)
      self.pixmap.draw_layout(self.color[3], 4, count * self.yBlock, layout)
      
  def draw_grid(self):
    """responsible for drawing the grid on the pixmap"""
    for x in range(0, 24, 1):
      self.pixmap.draw_line(self.color[3], x*self.xBlock+self.textOffset, 0, x*self.xBlock+self.textOffset, self.height - self.legendOffset)
    for y in range(0, 8, 1):
      self.pixmap.draw_line(self.color[3], self.textOffset, y*self.yBlock, self.width+self.textOffset, y*self.yBlock)
    return True
  
  def draw_legend(self):
    """turn away now"""
    #some extra special magic numbers
    horSpacer = 3
    verSpacer = 4
    #where the legend starts
    vertical = self.yBlock*7 + verSpacer
    horizontal = self.textOffset + self.xBlock*3 + 7
    
    def returnSquare(x, y, width, height):
      return ((x, y), (x+width, y), (x+width, y+height), (x, y+height))
      
    #Full Speed
    self.xStartStop0 = (horizontal, horizontal+self.xBlock*5) #basically, the starting position and the ending position (for use when updating the label)
    square = returnSquare(horizontal, vertical, self.xBlock, self.yBlock)
    self.pixmap.draw_polygon(self.color[3], False, square)
    layout = self.drawing_area.create_pango_layout("Full Speed")
    self.pixmap.draw_layout(self.color[3], horizontal+self.xBlock+horSpacer, vertical+verSpacer, layout)
    #Limited Speed
    self.xStartStop1 = (horizontal+self.xBlock*6, horizontal+self.xBlock*12 +7)
    square = returnSquare(horizontal+self.xBlock*6, vertical, self.xBlock, self.yBlock)
    self.pixmap.draw_polygon(self.color[1], True, square)#black border
    self.pixmap.draw_polygon(self.color[3], False, square)
    layout.set_text("Limited Speed")
    self.pixmap.draw_layout(self.color[3], horizontal+self.xBlock*7+horSpacer, vertical+verSpacer, layout)
    #Off
    self.xStartStop2 = (horizontal+self.xBlock*13 + 7, horizontal+self.xBlock*15 +7)
    square = returnSquare(horizontal+self.xBlock*13 + 7, vertical, self.xBlock+1, self.yBlock+1)
    self.pixmap.draw_polygon(self.color[3], True, square)
    layout.set_text("Off")
    self.pixmap.draw_layout(self.color[3], horizontal+self.xBlock*14+horSpacer+7, vertical+verSpacer, layout)
    #push the drawings into the queue
    self.drawing_area.queue_draw_area(horizontal, vertical, square[1][0], square[2][1])
    
  def update_label(self, hour, dayNum, x, y):
    """responsible for writing the day/time for a given block the user hovers over"""
    if hour is not None and x > 30 and y < (self.height - self.legendOffset): #since None > 0 
      week = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
      text = "%s, %s:00 - %s:59" % (week[dayNum], hour, hour)
    elif self.xStartStop0[0] < x < self.xStartStop0[1]:
      text = "Will run as fast as possible!"
    elif self.xStartStop1[0] < x < self.xStartStop1[1]:
      text = "Will run at limited speeds."
    elif self.xStartStop2[0] < x < self.xStartStop2[1]:
      text = "Won't upload or download."
    else:
      text = ""
    self.label.set_text(text)
  
  def expose_event(self, widget, event):
    """Redraw the screen from the backing pixmap"""
    if not self.pixmap:
      self.pixmap = gtk.gdk.Pixmap(widget.window, self.width, self.height)
      style = self.drawing_area.get_style()
      self.color = [style.white_gc, style.bg_gc[gtk.STATE_PRELIGHT], style.fg_gc[gtk.STATE_PRELIGHT], style.black_gc] #white, grey, something, and black
      self.pixmap.draw_rectangle(self.color[0], True, 0, 0, self.width, self.height)
      self.pixmap.draw_polygon(self.color[3], False, ((0, 0), (self.width-1, 0), (self.width-1, self.height-1), (0, self.height-1)))
      if not self.initialized:
        self.init_drawing_area()
        self.initialized = True
      self.draw_grid()
      self.draw_text()
      self.draw_legend()
    
    x, y, width, height = event.area
    widget.window.draw_drawable(widget.get_style().fg_gc[gtk.STATE_NORMAL], self.pixmap, x, y, x, y, width, height)
    return False
    
  def toggle_mapping(self, hour, day):
    """updates our mapping of setting to time and returns a state, ie color"""
    if hour >= 24 or day >= 7:
      return None
    if self.mapping[day][hour] == 0:
      state = 1
    elif self.mapping[day][hour] == 1:
      state = 2
    elif self.mapping[day][hour] == 2:
      state = 0
    self.mapping[day][hour] = state
    return state
     
  def fillin_bucket(self, widget, x, y):
    """Draw a rectangle on the screen where the user clicked, and redraw the grid on top"""
    if x < self.textOffset: #no need to color over our text
      return True
    hBlock = int((x-self.textOffset)/self.xBlock) #corresponds to the block where the user clicked
    vBlock = int(y/self.yBlock) #corresponds to the block where the user clicked
    rect = (hBlock * self.xBlock+self.textOffset, vBlock * self.yBlock, self.xBlock, self.yBlock)
    color = self.toggle_mapping(hBlock, vBlock) #update our list list
    if color is not None:
      self.pixmap.draw_rectangle(self.color[color], True, rect[0], rect[1], rect[2], rect[3])
      widget.queue_draw_area(rect[0], rect[1], rect[2], rect[3])
      self.draw_grid()
    return True
        
  def button_press_event(self, widget, event):
    """is alerted when the user presses the mouse"""
    if event.button == 1 and event.x > 30 and event.y < (self.height - self.legendOffset):
      now = time.time()
      if now - self.previousTime > .1: #sometimes double clicks are triggered- this is easier than figuring out why
        self.fillin_bucket(widget, event.x, event.y)
        self.previousBox = [int((event.x-self.textOffset)/self.xBlock), int(event.y/self.yBlock)]
        self.previousTime = now
    return True
    
  def mouse_left(self, widget, event):
    """called when the cursor leaves the drawing area"""
    self.update_label(None, None, None, None)
    
  def motion_notify_event(self, widget, event):
    """called when the cursor is moved inside the drawing area"""
    if event.is_hint:
      x, y, state = event.window.get_pointer()
    else:
      x = event.x
      y = event.y
      state = event.state
    hour = int((x-self.textOffset)/self.xBlock) #and the event was....
    dayNum = int(y/self.yBlock)
    if state & gtk.gdk.BUTTON1_MASK: #the mouse 1 button is depressed :( 
      if self.previousBox != [hour, dayNum]:
        self.previousBox = [hour, dayNum]
        self.fillin_bucket(widget, x, y)
    #if x > 30 and y < (self.height - self.legendOffset): 
    self.update_label(hour, dayNum, x, y)
    return True