#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Easily define an ordered set of attributes for comparison."""

import sys

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic

class EasyComparableMixin(object):
  """Define an ordered set of attributes to be compared for ordering."""
  def __cmp__(self, other):
    #order to compare the pieces of this class:
    for attr in self.COMPARISON_ORDER:
      selfVal = getattr(self, attr)
      otherVal = getattr(other, attr)
      if selfVal != otherVal:
        if selfVal == None:
          return 1
        if otherVal == None:
          return -1
        if type(selfVal) is str:
          if selfVal < otherVal:
            return -1
          if selfVal > otherVal:
            return 1
        else:
          return selfVal.__cmp__(otherVal)
    return 0
  
  def __hash__(self):
    """Basically XOR everything together"""
    result = 0L
    for attr in self.COMPARISON_ORDER:
      val = Basic.bytes_to_long(str(getattr(self, attr)))
      result = result.__xor__(val)
    #TODO:  this is probably not exactly the right way to convert to an integer...
    INT_MAX = sys.maxint
    result = (result % (2*INT_MAX)) - INT_MAX
    return result
    