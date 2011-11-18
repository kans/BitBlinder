import re, os
import matplotlib
matplotlib.use('Cairo')
import matplotlib.pyplot as plt

def compare(x, y):
  x=x.split('.')
  if len(x) == 1:
    #ie, consensus
    return 1
  else:
    x=int(x[1])
  y = y.split('.')
  if len(y) == 1:
    return -1
  else:
    y=int(y[1])
  if x > y:
    return 1
  elif x==y:
    return 0
  else: #x < y:
    return -1

times =[]
bandwidth=[]
exits=[]

validAfterRe = re.compile('valid-after (\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}):\d{2}')
bandwidthRe = re.compile('w Bandwidth=(\d{1,10})')
exitRe = re.compile('s Exit')

os.chdir('/home/stats/')
cons = os.listdir('consensi')
cons.sort(compare)
cons.pop() #kill the unenumerated one

for c in cons:
  handle = open('consensi/%s'%(c), 'r')
  c = handle.read()
  handle.close()
  #get time
  t = validAfterRe.search(c)
  validAfterDate = t.group(1)
  validAfterTime = t.group(2)
  times.append(validAfterTime)

  #get bandwidth
  total = 0
  allBandwidths = bandwidthRe.findall(c)
  for b in allBandwidths:
    total+= int(b)
  bandwidth.append(total)

  exits.append(len(exitRe.findall(c)))

#convert times to base 10 cause trying to graph times otherwise with the built in plot_date is a trainwreck
day = 0
minsDay= 24*60
previousTime = 0
for position, t in enumerate(times):
  tup = t.split(":")
  hour = int(tup[0])
  min = int(tup[1])
  base10TimeFromEpoch = (hour*60. + min)/minsDay
  if base10TimeFromEpoch < previousTime: #the day rolled over...
    day +=1
  previousTime=base10TimeFromEpoch
  base10TimeFromEpoch+=day #add the day...
  times[position]="%.3f"%(base10TimeFromEpoch)  

plt.figure(1)
plt.subplot(211)
plt.plot(times, bandwidth, 'r')
plt.title('Total Estimated Bandwidth Available vs. Time base 10')
plt.ylabel('Bandwidth in KB/s')
plt.subplot(212)
plt.plot(times, exits, 'bo')
plt.title('Number of Exits vs. Time base 10')
plt.xlabel('crazy time starting from 6-10-09 @ 8:45 gm')
plt.ylabel('Number of Exit Relays')
plt.savefig('/home/web/media/stats.png')


print 'Huge Success!'
print('consensi from times %s to %s were analyzed for a total of %s consensisisisisi!'%(times[0], times[len(times)-1], len(times))) 
