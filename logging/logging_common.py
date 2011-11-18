#!/usr/bin/python


def calculate_email_conversion(cur, timeStart, timeEnd, variant):
  _make_conversion_tables(cur, timeStart, timeEnd, variant)
  #how many emails were sent in the first place?
  cur.execute("SELECT COUNT(*) FROM emails_sent;")
  emailsSent = cur.fetchone()[0]
  percentOpened = 0
  percentClicked = 0
  percentCreated = 0
  percentLoggedIn = 0
  if emailsSent > 0:
    #get the base count for opened emails:
    cur.execute("SELECT COUNT(*) FROM emails_opened;")
    emailsOpened = cur.fetchone()[0]
    #now add in the visitors that clicked on the link, but did not display images in the email:
    cur.execute("SELECT COUNT(hexkey) FROM email_link_visits WHERE hexkey NOT IN (SELECT hexkey FROM emails_opened);")
    emailsOpened += cur.fetchone()[0]
    #ok, now simply how many clicked the link:
    cur.execute("SELECT COUNT(*) FROM email_link_visits;")
    linksClicked = cur.fetchone()[0]
    #of those, how many created accounts?
    cur.execute("SELECT COUNT(*) FROM accounts_created;")
    accountsCreated = cur.fetchone()[0]
    #finally, how many of those users have ever logged in?
    cur.execute("SELECT COUNT(*) FROM accounts_created WHERE username IN (SELECT DISTINCT username FROM banklogin_events);")
    logins = cur.fetchone()[0]
  
    #time to calculate the actual statistics:
    percentOpened = 100.0 * float(emailsOpened) / float(emailsSent)
    percentClicked = 100.0 * float(linksClicked) / float(emailsSent)
    percentCreated = 100.0 * float(accountsCreated) / float(emailsSent)
    percentLoggedIn = 100.0 * float(logins) / float(emailsSent)
  
  _cleanup_conversion_tables(cur)  
  return (emailsSent, percentOpened, percentClicked, percentCreated, percentLoggedIn)
  
def _cleanup_conversion_tables(cur):
  cur.execute("DROP TABLE IF EXISTS emails_sent")
  cur.execute("DROP TABLE IF EXISTS emails_opened")
  cur.execute("DROP TABLE IF EXISTS email_link_visits")
  cur.execute("DROP TABLE IF EXISTS accounts_created")

def _make_conversion_tables(cur, timeStart, timeEnd, variant):
  #make a table for the emails that were sent in the time period that we care about:
  sql = "CREATE TEMPORARY TABLE emails_sent AS SELECT DISTINCT ON (hexkey) * FROM emailsent_events WHERE eventTime >= %s AND eventTime < %s AND variant = %s;"
  cur.execute(sql, (timeStart, timeEnd, variant))
  #how many emails were sent in the first place?
  cur.execute("SELECT COUNT(*) FROM emails_sent;")
  emailsSent = cur.fetchone()[0]
  if emailsSent > 0:
    #of those, how many were opened?  first, lets create a temporary table of them
    cur.execute("CREATE TEMPORARY TABLE emails_opened AS SELECT DISTINCT ON (hexkey) emails_sent.hexkey as hexkey, emailopened_events.eventTime as eventTime FROM emails_sent, emailopened_events WHERE emailopened_events.hexkey = emails_sent.hexkey;")
    #then make the temporary table for the links visited
    cur.execute("CREATE TEMPORARY TABLE email_link_visits AS SELECT DISTINCT ON (hexkey) emails_sent.hexkey as hexkey, emaillinkvisit_events.eventTime as eventTime FROM emails_sent, emaillinkvisit_events WHERE emaillinkvisit_events.hexkey = emails_sent.hexkey;")
    #of those, how many created accounts?
    cur.execute("CREATE TEMPORARY TABLE accounts_created AS SELECT DISTINCT ON (hexkey) email_link_visits.hexkey as hexkey, accountcreated_events.eventTime, accountcreated_events.username as username FROM email_link_visits, accountcreated_events WHERE email_link_visits.hexkey = accountcreated_events.hexkey;")
    
