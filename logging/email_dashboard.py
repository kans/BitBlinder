#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""An automated reporter of the health of all servers, and the statistics that we currently care about optimizing"""

import subprocess
import os
import sys
import time
import copy
import socket
import smtplib
from email.mime.text import MIMEText

from serverCommon import DbAccessConfig
DbAccessConfig.database = "logging"
from serverCommon import cyborg_db as db
from logging_common import calculate_email_conversion

def send_email(toAddress, title, text):
  fromAddress = "devserver"
  
  #Create a text/plain message
  msg = MIMEText(text)
  msg['Subject'] = title
  msg['From'] = fromAddress
  msg['To'] = toAddress

  #Send the message via our own SMTP server, but don't include the envelope header.
  s = smtplib.SMTP("localhost")
  s.sendmail(fromAddress, [toAddress], msg.as_string())
  s.quit()
  
def _make_row(columnWidth, rowString):
  rowVals = rowString.split("|")
  newRowString = ""
  for val in rowVals:
    newRowString += val + (" "*(columnWidth-len(val)))
  newRowString += "\n"
  return newRowString

def get_server_health_summary(cur, startTime, endTime):
  """@returns:  string (a summary of any errors that happened in server reachability"""
  cur.execute("SELECT COUNT(*), url FROM serverdown_events WHERE eventtime >= %s and eventtime < %s GROUP BY url", (startTime, endTime))
  serverResults = cur.fetchall()
  summary = ""
  for failureCount, url in serverResults:
    summary += "%s was down for %s hours!!\n" % (url, failureCount)
  if summary == "":
    summary = "Everything is fine"
  return summary

def get_unique_visitors():
  """We just parse the squid logs for this right now.
  FORMAT:  86.199.197.116 - - [23/Dec/2009:15:15:45 +0000] (more useless garbage)
  @returns:  int (the number of unique visitors yesterday)"""
  
  #only read the hits from yesterday
  curTime = list(time.localtime())
  curTime[2] = curTime[2] - 1
  endTime = time.strftime("%d/%b/%Y", curTime)
  p = subprocess.Popen('grep -e "\[%s:" data_live/squid/access.log' % (endTime), shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
  result, err = p.communicate()
  if p.returncode != 0:
    raise IOError(err)
  hitLines = result.split("\n")
  
  #find all the unique IP addresses:
  visitors = set()
  for line in hitLines:
    vals = line.split(" ", 1)
    if len(vals) <= 1:
      continue
    ipAddress, otherData = line.split(" ", 1)
    visitors.add(ipAddress)
    
  return len(visitors)
  
#TODO:  this is a hackish way to get this info
def get_web_signups(startTime, endTime):
  """@returns: int (number of people who submitted their email address for the beta)"""
  try:
    p = subprocess.Popen("""ssh -i /home/rtard/.ssh/innomikeypair.pem root@bitblinder.com""", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.PIPE)
    p.stdin.write("""psql bitblinderdb -t -c \"select count(*) from email_signup where time >= '%s' and time < '%s';\"""" % (startTime, endTime))
    result, err = p.communicate()
    if p.returncode != 0:
      raise IOError(err)
    return int(result.strip().split()[0])
  except Exception, e:
    raise e

def get_network_utilization(cur, startTime, endTime):
  """@returns:  string (a summary of the network utilization over the past 24 hours)"""
  try:
    #print the headers
    table = _make_row(10, "|".join(["time", "traffic(MB)", "relays", "% active", "utilization %"]))
    #get all the data
    cur.execute("SELECT time, value FROM avgpaymentsperhour_stats WHERE time >= %s and time < %s ORDER BY time DESC", (startTime, endTime))
    paymentResults = cur.fetchall()
    cur.execute("SELECT time, value FROM usersperhour_stats WHERE time >= %s and time < %s ORDER BY time DESC", (startTime, endTime))
    userResults = cur.fetchall()
    cur.execute("SELECT time, value FROM relaysperhour_stats WHERE time >= %s and time < %s ORDER BY time DESC", (startTime, endTime))
    relayResults = cur.fetchall()
    cur.execute("SELECT time, value FROM TotalRelayBandwidthPerHour_stats WHERE time >= %s and time < %s ORDER BY time DESC", (startTime, endTime))
    totalRelayBWResults = cur.fetchall()
    #print out each hour:
    while len(paymentResults) > 0:
      statTime, numPayments = paymentResults.pop(0)
      otherTime, numUsers = userResults.pop(0)
      assert statTime == otherTime, "Rows for statistics should be identical!"
      otherTime, numRelays = relayResults.pop(0)
      assert statTime == otherTime, "Rows for statistics should be identical!"
      hourString = str(statTime).split(" ")[1][:2]
      percentActive = 100.0 * float(numUsers) / float(numRelays)
      totalPayments = numPayments * numUsers
      otherTime, totalBWInKB = totalRelayBWResults.pop(0)
      totalBWInMBps = totalBWInKB / 1024.0
      networkHourlyCapacity = totalBWInMBps * 60 * 60
      totalTrafficInMB = totalPayments * 4
      utilization = 100.0 * float(totalTrafficInMB) / float(networkHourlyCapacity)
      table += _make_row(10, "%s:|%.1f|%.1f|%.1f|%.1f" % (hourString, totalTrafficInMB, numRelays, percentActive, utilization))
    return table
  except Exception, e:
    return "Failed to generate table: %s" % (e)
    
def get_daily_users(cur, startTime, endTime):
  """@returns:  int (the number of unique users in the past 24 hours)"""
  cur.execute("SELECT value FROM usersperday_stats WHERE time >= %s and time < %s", (startTime, endTime))
  return int(cur.fetchone()[0])
  
def get_cpu_utilization(cur, startTime, endTime):
  """@returns:  float (the max utilization in the time period)"""
  cur.execute("SELECT max(usage) FROM cpuusage_events WHERE eventtime >= %s and eventtime < %s", (startTime, endTime))
  result = cur.fetchone()[0]
  return float(result)
  
def get_conversion_summary(cur, variant):
  """@returns:  string (a summary of the conversion numbers over the past week)"""
  curTime = list(time.localtime())
  #print the headers
  table = _make_row(10, "Day|Sent|Open|Click|Create|Login")
  #for each day of the week in the past:
  for day in range(1, 8):
    startTime = copy.copy(curTime)
    startTime[2] = startTime[2] - day
    startTime = time.strftime("%Y-%m-%d 00:00:00", time.struct_time(startTime))
    endTime = copy.copy(curTime)
    endTime[2] = endTime[2] - (day-1)
    endTime = time.strftime("%Y-%m-%d 00:00:00", time.struct_time(endTime))
    (emailsSent, percentOpened, percentClicked, percentCreated, percentLoggedIn) = calculate_email_conversion(cur, startTime, endTime, variant)
    table += _make_row(10, "%s|%s|%.1f|%.1f|%.1f|%.1f" % (day, emailsSent, percentOpened, percentClicked, percentCreated, percentLoggedIn))
  return table
  
def do_update():
  conn = db.Pool.get_conn()
  cur = conn.cursor()
  curTime = list(time.localtime())
  startTime = copy.copy(curTime)
  startTime[2] = startTime[2] - 1
  startTime = time.strftime("%Y-%m-%d 00:00:00", startTime)
  endTime = time.strftime("%Y-%m-%d 00:00:00", curTime) 
  statLines = []

  #stats about the health of our network
  statLines.append("Server Status:\n%s" % (get_server_health_summary(cur, startTime, endTime)))
  statLines.append("Max CPU Usage:\t%.1f" % (get_cpu_utilization(cur, startTime, endTime)))

  #the metrics that we currently care about
  statLines.append("Website Uniques:\t%s" % (get_unique_visitors()))
  statLines.append("Website Signups:\t%s" % (get_web_signups(startTime, endTime)))
  statLines.append("Network Daily Users:\t%s" % (get_daily_users(cur, startTime, endTime)))
  
  statLines.append("\nInvite Conversions (old):\n%s" % (get_conversion_summary(cur, "invite_initial")))
  statLines.append("Invite Conversions (one day delay):\n%s" % (get_conversion_summary(cur, "invite_single_day_delay")))
  statLines.append("Network Utilization:\n%s" % (get_network_utilization(cur, startTime, endTime)))

  #print everything out or email it to us, as appropriate
  serverDataText = "\n".join(statLines)
  if len(sys.argv) > 1 and sys.argv[1] == "--debug":
    print serverDataText
  else:
    for emailAddress in ("jash@mail.bitblinder.com", "kans@mail.bitblinder.com"):
      send_email(emailAddress, "Daily BitBlinder Summary", serverDataText)
    
  cur.close()
  
do_update()
