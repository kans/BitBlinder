#!/usr/bin/python
#Copyright 2008-2009 InnomiNet
"""Create an account in response to a request from the python client"""
#TODO:  more stringently check that cyborg.IntegrityError's are from a duplicate primary key

import os
import struct
import time
import subprocess

from twisted.internet import defer
from twisted.internet import utils
import psycopg2 as cyborg

from common.utils.Basic import log_msg, log_ex, _ # pylint: disable-msg=W0611
from common.utils import Basic
from common import Globals
from serverCommon.Events import AccountCreated
from serverCommon import EventLogging
from serverCommon import DBUtil
from serverCommon import DbAccessConfig

#TODO:  this whole bunch of sql code doesnt do much really.  It should be replaced with a unique constraint on email addresses once we've moved to all lower case emails.
#ensure that certain necessary functions are in place before running:
process = subprocess.Popen("psql -v 'ON_ERROR_STOP=on' -1 -f account_functions.sql %s" % (DbAccessConfig.database), shell=True)
returnCode = process.wait()
assert returnCode == 0, "Failed to install necessary sql functions with code %s, login server will not run." % (returnCode)

#: the location on the filesystem of the phpbb3 register script
PHP_REGISTER_SCRIPT = "/home/web/accounts/php/register.php"
assert os.path.exists(PHP_REGISTER_SCRIPT), "Cannot find %s, will not be able to create accounts properly!" % (PHP_REGISTER_SCRIPT)
#: how many tokens to start an account with
STARTING_BALANCE = 1000
#: how long, in seconds, to allow the IP-to-invite mappings to be valid for
CACHE_ENTRY_LIFETIME = 60 * 60 * 24 * 7
#: a mapping from reason for failure -> response code for accoun creation
RESPONSE_CODES = {"SUCCESS":        0,
                  "BAD_USERNAME":   1,
                  "BAD_PASSWORD":   2,
                  "BAD_EMAIL":      3,
                  "USERNAME_TAKEN": 4,
                  "UNKNOWN_ERROR":  5}
                  
class AccountCreation():
  def __init__(self, data, ipAddress, db, reply_func):
    """Unpack the data from the request and start dealing with it"""
    log_msg("Received account creation request from %s" % (ipAddress))
    
    self.reply_func = reply_func
    self.db = db
    self.ipAddress = ipAddress
    self.curTime = time.ctime()
    
    #for now, let's just unpack, validate, and respond accordingly
    (username, password, email, shouldAddToMailingList) = struct.unpack('!50s50s150sB', data)
    
    #strip out the null padding characters
    self.username = username.replace('\x00', '')
    self.password = password.replace('\x00', '')
    self.email = email.replace('\x00', '').lower()
    self.hexKey = None
    self.saltedPassword = None
    self.shouldAddToMailingList = shouldAddToMailingList == 1
    
    self._start()
    
  def _start(self):
    """Validate the data, then try to get the matching invite token from the database"""
    #validate data:
    if not Globals.USERNAME_REGEX.match(self.username):
      self._reply(RESPONSE_CODES["BAD_USERNAME"])
      return
    if not Globals.PASSWORD_REGEX.match(self.password):
      self._reply(RESPONSE_CODES["BAD_PASSWORD"])
      return
    
    #if no email was provided, look in our cache
    if not self.email:
      sql = "SELECT hexkey, eventtime FROM download_id_cache WHERE address = %s"
      inj = (self.ipAddress,)
      cacheLookupDeferred = self.db.read(sql, inj)
      cacheLookupDeferred.addCallback(self._on_learned_hexkey)
      cacheLookupDeferred.addErrback(self._handle_error)
    
    #if email was provided, validate it then use it to find the invite
    else:
      if not Globals.EMAIL_REGEX.match(self.email):
        self._reply(RESPONSE_CODES["BAD_EMAIL"])
        return
      sql = "SELECT value, email FROM email_signup_keys WHERE redeemed = FALSE AND email = %s"
      inj = (self.email,)
      redeemedDeferred = self.db.read(sql, inj)
      redeemedDeferred.addCallback(self._on_learned_invite)
      redeemedDeferred.addErrback(self._handle_error)
      
  def _on_learned_hexkey(self, result):
    """Called when the sql query to retrieve the invite hexkey from the IP cache finishes"""
    #if there was no entry in the cache
    if not result:
      self._reply(RESPONSE_CODES["BAD_EMAIL"])
      return
    
    #unpack the db result
    hexKey, eventTime = result[0]
    eventTime = eventTime.ctime()
    
    #if the cache entry is too old
    if DBUtil.ctime_to_int(eventTime) - DBUtil.ctime_to_int(self.curTime) > CACHE_ENTRY_LIFETIME:
      self._reply(RESPONSE_CODES["BAD_EMAIL"])
      return
      
    #otherwise, check if this invite has been redeemed yet
    sql = "SELECT value, email FROM email_signup_keys WHERE redeemed = FALSE AND value = %s"
    inj = (hexKey,)
    redeemedDeferred = self.db.read(sql, inj)
    redeemedDeferred.addCallback(self._on_learned_invite)
    redeemedDeferred.addErrback(self._handle_error)
    
  def _on_learned_invite(self, result):
    """Called when the sql query to retrieve the invite hexkey and email out of the database finishes"""
    #fail if we couldnt find an invite
    if not result:
      self._reply(RESPONSE_CODES["BAD_EMAIL"])
      return
      
    #unpack the database response
    self.hexKey, self.email = result[0]

    #everything checks out, time to actually insert the user
    self.saltedPassword = DBUtil.format_auth(self.username, self.password)
    sql = "INSERT INTO accounts (username, balance, email, time, password) VALUES (%s, %s, %s, %s, %s) RETURNING username"
    inj = (self.username, STARTING_BALANCE, self.email, self.curTime, cyborg.Binary(self.saltedPassword))
    creationDeferred = self.db.Pool.conn_pool.runQuery(sql, inj)
    creationDeferred.addCallback(self._on_account_creation_succeeded)
    creationDeferred.addErrback(self._on_account_creation_failed)
    
  def _on_account_creation_failed(self, failure):
    """Called when we fail to create an account in the main database.
    If it was because the username is taken, respond accordingly, otherwise this is an error."""
    if not failure.check(cyborg.IntegrityError):
      self._handle_error(failure)
    else:
      self._reply(RESPONSE_CODES["USERNAME_TAKEN"])
    
  def _on_account_creation_succeeded(self, result):
    """Make sure the row was inserted, then do secondary account creation tasks
    (add the phpbb user account, redeem the invite, and add to the mailing list if necessary)"""
    
    #This should only happen if your email is non-unique:
    if len(result) != 1:
      self._reply(RESPONSE_CODES["BAD_EMAIL"])
      return
    assert result[0][0] == self.username, "That's pretty bizarre, how did we get %s from the account insert?" % (result)
    
    #do secondary account creation tasks
    deferreds = []
    deferreds.append(self._set_phpbb3_user())
    deferreds.append(self._mark_invite_as_used())
    if self.shouldAddToMailingList:
      deferreds.append(self._add_to_mailing_list())
    else:
      deferreds.append(defer.succeed(True))
    finishedDeferred = defer.DeferredList(deferreds)
    finishedDeferred.addCallback(self._on_finished)
    finishedDeferred.addErrback(self._handle_error)
    
  def _mark_invite_as_used(self):
    sql = "UPDATE email_signup_keys SET redeemed = true WHERE value = %s"
    inj = (self.hexKey,)
    redeemDeferred = self.db.write(sql, inj)
    def handle_errors(failure):
      """Should be pretty impossible to get here"""
      log_ex(failure, "Failed to mark the invite for %s as redeemed!" % (self.hexKey))
    redeemDeferred.addErrback(handle_errors)
    return redeemDeferred
    
  def _add_to_mailing_list(self):
    """If the user wanted to be informed of BitBlinder updates via email, add them to the mailing list"""
    sql = "INSERT INTO mailing_list (email, created_on) VALUES (%s, %s)"
    inj = (self.email, self.curTime)
    mailingDeferred = self.db.write(sql, inj)
    def handle_errors(failure):
      """IntegrityError's are ok because they indicate that the user already exists on the mailing list.
      Log any other failures."""
      if not failure.check(cyborg.IntegrityError):
        log_ex(failure, "Failed to add user %s to the mailing list" % (self.email))
    mailingDeferred.addErrback(handle_errors)
    return mailingDeferred
    
  def _set_phpbb3_user(self):
    """Attempts to add a phpbb3 user account by calling a php wrapper around the native phpbb3 function.
    @returns:  Deferred (will be triggered when the user has been added or not (bool result))"""
    args = [PHP_REGISTER_SCRIPT]
    for info in (self.username, self.saltedPassword, self.email, self.ipAddress):
      args.append(info.encode('hex'))
    output = utils.getProcessOutput("/usr/bin/php", args=args, errortoo=True)
    
    def validate_php_output(response):
      """The script should return an integer.  Anything else indicates a failure."""
      try:
        response = int(response)
        return True
      except Exception, e:
        log_ex(e, "PHP account creation failed:  %s\n%s" % (response, args))
      return False
    output.addCallback(validate_php_output)
    
    def error_handler(failure):
      """Log an error if the script did not finish cleanly."""
      log_ex(failure, "PHP script had an error:")
    output.addErrback(error_handler)
    
    return output
      
  def _on_finished(self, results):
    """Everything worked (well enough).
    Log the event and return the SUCCESS code reply"""
    EventLogging.save_event(AccountCreated(hexkey=self.hexKey, username=self.username, mailinglist=self.shouldAddToMailingList))
    self._reply(RESPONSE_CODES["SUCCESS"])
      
  def _reply(self, code):
    """Send an appropriately encoded reply to the client"""
    self.reply_func(Basic.write_byte(1) + Basic.write_byte(code))
    if code == RESPONSE_CODES["SUCCESS"]:
      log_msg("Account %s created for %s" % (self.username, self.ipAddress))
    else:
      log_msg("Account creation attempt failed with code = %s" % (code))
  
  def _handle_error(self, reason):
    """Log the error, and reply with UKNOWN_ERROR.
    Note that this is obviously only for unexpected errors.  Other errors should have their own error codes."""
    log_ex(reason, "Unhandled error during account creation")
    self._reply(RESPONSE_CODES["UNKNOWN_ERROR"])
    
