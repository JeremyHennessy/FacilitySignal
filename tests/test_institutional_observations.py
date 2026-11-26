import sqlite3,unittest
from institutional_observations import setup,add_source,filters,validate,observation,RULES
class Tests(unittest.TestCase):
    def setUp(self):
        self.db=sqlite3.connect(":memory:");setup(self.db)
        self.pin={"release":"test","sha256":"test"}
    def tearDown(self):self.db.close()
    def rows(self,value="Yes"):
        return {("000001","NY"):({"Emergency Services":value},{"ccn":"000001","state":"NY"}),("000002","NJ"):({"Emergency Services":"No"},{"ccn":"000002","state":"NJ"})}
    def test_filter_and_counts(self):
        rows=self.rows();add_source(self.db,"hospital",self.pin,rows,"test")
        self.assertEqual(filters(self.db,"hospital","emergency_services","reported_yes"),[("000001","NY")])
        self.assertEqual(filters(self.db,"hospital","emergency_services","reported_yes","NJ"),[])
        self.assertEqual(validate(self.db,"hospital",rows,{"Emergency Services":{"Yes":1,"No":1}}),{"emergency_services":{"reported_yes":1,"reported_no":1}})
    def test_unknown_rolls_back(self):
        with self.assertRaises(ValueError):add_source(self.db,"hospital",self.pin,self.rows("Unknown"),"test")
        self.assertEqual(self.db.execute("SELECT count(*) FROM candidate_release").fetchone()[0],0)
    def test_scope_and_missing(self):
        self.assertEqual(observation(RULES["nursing"]["special_focus"],""),"not_reported")
        self.assertEqual(observation(RULES["nursing"]["sprinklers"],"Data Not Available"),"not_available")
        with self.assertRaises(ValueError):filters(self.db,"hospital","sprinklers","partial")
    def test_duplicate_rejected(self):
        add_source(self.db,"hospital",self.pin,self.rows(),"test")
        with self.assertRaises(sqlite3.IntegrityError):add_source(self.db,"hospital",self.pin,self.rows(),"test")
