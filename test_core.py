import os, tempfile, unittest
os.environ['SUDANCARE_DB_PATH']=tempfile.mktemp(suffix='.db')
from app.core import init_db,password_hash,password_matches,db
class CoreTests(unittest.TestCase):
 def setUp(self): init_db()
 def test_password_hash_round_trip(self):
  stored=password_hash('a sufficiently long password')
  self.assertTrue(password_matches('a sufficiently long password',stored))
  self.assertFalse(password_matches('wrong password',stored))
 def test_schema_has_outbox(self):
  with db() as c: self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='outbox'").fetchone())
