#!/usr/bin/python

import os
import re
import glob

#make a list of all logs
fileNames = glob.glob("/mnt/logs/consensus/consensus_events.out.*")
#replace the text on each line
for fileName in fileNames:
  #read all lines
  fileHandle = open(fileName, "rb")
  lines = fileHandle.readlines()
  fileHandle.close()
  #do a replace on each line (NewConsensusEvent -> NewConsensus), and print it right back out to the same file name
  fileHandle = open(fileName, "wb")
  for line in lines:
    line = line.replace("NewConsensusEvent", "NewConsensus")
    fileHandle.write(line)
  fileHandle.close()
