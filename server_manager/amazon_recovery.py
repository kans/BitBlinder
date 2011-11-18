#!/usr/bin/python
"""For restarting all the services on amazon when it is rebooted."""
from common.utils import Build

syscall = Build.syscall

#to run at startup:
#add to /etc/rc.local
#commands:
#IDEA:  send an email to ourselves whenever the server restarts
#doesnt work on amazon:
#date | mail -s "SERVER RESTARTED" kans@mail.bitblinder.com
#does work:
(echo "Subject: SERVER RESTARTED"; date) | sendmail kans@mail.bitblinder.com
squid
pushd /home/authorities
nohup python LAUNCH_AUTHORITIES.py 174.129.199.15 >& temp.out &
popd
pushd /home/bank
#NOTE:  need keyless bank as well
popd

##actually, have to kill  :(  
##or better yet, make sure it doesnt start automatically?
##or even better, make this run automatically?
##also strip the password out of that key file so that it comes up properly  <---DONE
#syscall("/etc/init.d/apache2 stop")
#syscall("/etc/init.d/apache2 start")

#squid
#authorities:
#nohup python LAUNCH_AUTHORITIES.py 174.129.199.15 >& temp.out &
#in:  /home/authority

#bank
#login
#ftp
#cpu
