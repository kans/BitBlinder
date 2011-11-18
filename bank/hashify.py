"""
Conversion utility tool

1 adds a column called hash of type bytea, 
2 salts and hashes the current password column and updates the hash column with the data
3 deletes the password column
4 renames hash column to password

"""
import Crypto.Hash.SHA256
from serverCommon import db
import psycopg2 as cyborg

def hashify(username, pw):
  """hashes the pw with a salt of the username"""
  print username, pw
  h = Crypto.Hash.SHA256.new(username)
  h.update(pw) #take salted hash
  return(h.digest())

print "you will need to close anything with an open connection (ie apache) to the database to change table structures!"

sql = 'alter table accounts add column hash bytea'
db.write(sql)

sql = "Select username, password from accounts"
a = db.read(sql, tup = None, fetch='fetchall')

tup=[]
sql = []
for item in a:
  username = item[0]
  pw = item[1]
  pw = hashify(username, pw)
  sql.append("update accounts set hash = %s where username = %s")
  tup.append((cyborg.Binary(pw), username))

print "writing"
db.write(sql, tup)

sql = ['alter table accounts drop column password','alter table rename column hash to password']
db.write(sql)
print "all done!"







