import csv
import io
import unittest

from scripts import qualify_hai_aggregate as q

def stream(header, rows):
    f = io.StringIO(newline="")
    writer = csv.writer(f)
    writer.writerow(header)
    writer.writerows(rows)
    f.seek(0)
    return f

def refs():
    return [[code, "reference", "1", "", *q.WINDOW] for code in sorted(q.CODES)]

class HAIQualificationTests(unittest.TestCase):
    def test_reference_grain(self):
        self.assertEqual(q.national(stream(q.NATIONAL_HEADER, refs()))["unit_reference_rows"], 6)

    def test_reference_not_pooled(self):
        rows = refs()
        rows[0][2] = "0.7"
        with self.assertRaisesRegex(ValueError, "reference changed"):
            q.national(stream(q.NATIONAL_HEADER, rows))

    def test_missing_reference_and_period(self):
        with self.assertRaisesRegex(ValueError, "coverage"):
            q.national(stream(q.NATIONAL_HEADER, refs()[:-1]))
        rows = refs()
        rows[0][-1] = "12/31/2024"
        with self.assertRaisesRegex(ValueError, "period"):
            q.national(stream(q.NATIONAL_HEADER, rows))

    def test_provider_aggregate_only(self):
        row = ["012345", "private example", "street", "city", "AA", "00000",
               "", "telephone", "HAI_1_SIR", "example", "", "0", "", *q.WINDOW]
        second = row.copy()
        second[11] = "Not Available"
        out = q.provider(stream(q.PROVIDER_HEADER, [row, second]), 2)
        self.assertEqual(out["repeated_provisional_keys"], 1)
        self.assertEqual(out["score_states"], {"reported_zero": 1, "missing": 1})
        self.assertNotIn("012345", str(out))
        self.assertNotIn("private example", str(out))
        with self.assertRaisesRegex(ValueError, "row count"):
            q.provider(stream(q.PROVIDER_HEADER, [row]), 2)

    def test_schema_gate(self):
        with self.assertRaisesRegex(ValueError, "header drift"):
            q.national(stream(q.NATIONAL_HEADER[:-1], refs()))

if __name__ == "__main__":
    unittest.main()
