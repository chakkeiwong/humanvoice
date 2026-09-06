import unittest

from collect_repec import ResultParser


class RePEcParserTests(unittest.TestCase):
    def test_extracts_result_metadata_without_ui_items(self):
        html = """
        <ol>
          <li class="list-group-item downfree">A. Author &amp; B. Author (2025):
            <a href="https://ideas.repec.org/p/test/paper1.html"><b>AI</b> and <b>writing</b></a>
            <hr>An abstract with a method and a result.<br><i>RePEc:test:paper:1</i>
            <span>Save to MyIDEAS</span>
          </li>
        </ol>
        """
        parser = ResultParser()
        parser.feed(html)
        self.assertEqual(len(parser.results), 1)
        row = parser.results[0]
        self.assertEqual(row["identifier"], "RePEc:test:paper:1")
        self.assertEqual(row["title"], "AI and writing")
        self.assertEqual(row["year"], "2025")
        self.assertNotIn("Save to MyIDEAS", row["abstract"])


if __name__ == "__main__":
    unittest.main()
