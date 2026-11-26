import unittest
from legacy_pos_dictionary_crosswalk import parse

class LegacyLayoutCrosswalkTests(unittest.TestCase):
    def test_scope_page_and_continuation(self):
        text="""DATE: 04/02/2023 POS RECORD LAYOUT
PAGE: 1
 Hospital, CATEGORY = "01" (SEE POSITIONS 3-4)
    Facility Name                  50   67  116
VARCHAR2
   Description: Name of the provider
\fDATE: 04/02/2023 POS RECORD LAYOUT
PAGE: 2
 Hospital, CATEGORY = "01" (SEE POSITIONS 3-4)
    participating in Medicare.
    SAS Name: FAC_NAME
    COBOL Name: FAC-NAME
    Test code                       1   117 117 CHAR
    Description: Meaning for hospital
    SAS Name: TEST_CD
    COBOL Name: TEST-CD
    VALUES: 1=Staff
            2=Arrangement
\fPAGE: 3
 CLIA Laboratory, CATEGORY = "22" (SEE POSITIONS 3-4)
    Test code                       1   117 117 CHAR
    Description: Meaning for laboratory
    SAS Name: TEST_CD
"""
        parsed,categories=parse(text)
        self.assertEqual(parsed["FAC_NAME"][0]["description_candidate"],
                         "Name of the provider participating in Medicare.")
        self.assertEqual(parsed["FAC_NAME"][0]["physical_pdf_page"],2)
        self.assertEqual(parsed["FAC_NAME"][0]["category_code"],"01")
        self.assertEqual(parsed["TEST_CD"][0]["code_examples"],[["1","Staff"],["2","Arrangement"]])
        self.assertEqual(parsed["TEST_CD"][1]["category_code"],"22")
        self.assertEqual(set(categories),{"01","22"})
if __name__=="__main__":unittest.main()
