import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from import_public_content import ALLOWED_CLASSES, PageSanitizer, TreeParser, internal_url


class PublicContentSanitizerTests(unittest.TestCase):
    def render(self, source, url="https://www.restyl.cz/elektro/"):
        parser = TreeParser()
        parser.feed(source)
        sanitizer = PageSanitizer(url, Path("content/assets"), {}, [])
        form_url = "/formular/energy" if "/energy/" in url else "/formular/elektro"
        return sanitizer.render(parser.root, form_url)

    def test_removes_active_content_and_form_controls_but_keeps_form_link(self):
        rendered = self.render(
            '<p onclick="alert(1)">A</p><script>bad()</script>'
            '<form class="wpcf7-form cf7-style" action="https://production.example/submit"><input name="email"></form>'
        )
        self.assertIn("<p>A</p>", rendered)
        self.assertNotIn("alert", rendered)
        self.assertNotIn("bad()", rendered)
        self.assertNotIn("<form", rendered)
        self.assertNotIn("<input", rendered)
        self.assertIn('href="/formular/elektro"', rendered)

    def test_localizes_internal_links_and_rejects_javascript_urls(self):
        rendered = self.render(
            '<a href="https://www.restyl.cz/elektro/nn-elektroinstalace/">Detail</a>'
            '<a href="javascript:alert(1)">unsafe</a>'
        )
        self.assertIn('href="/elektro/nn-elektroinstalace/"', rendered)
        self.assertNotIn("javascript:", rendered)
        self.assertNotIn("alert(1)", rendered)

    def test_energy_form_uses_module_route(self):
        rendered = self.render(
            '<form class="wpcf7-form cf7-style"></form>',
            "https://www.restyl.cz/energy/kontaktni_formular_energy/",
        )
        self.assertIn('href="/formular/energy"', rendered)
        self.assertIn("formulář ENERGY", rendered)

    def test_search_form_is_skipped_not_replaced_with_contact_link(self):
        parser = TreeParser()
        parser.feed(
            '<p>Text před hledáním</p><form role="search" method="get" '
            'id="searchform" action="https://www.restyl.cz/"><input name="s"></form>'
            '<p>Text za hledáním</p>'
        )
        warnings = []
        sanitizer = PageSanitizer("https://www.restyl.cz/elektro/", Path("content/assets"), {}, warnings)
        rendered = sanitizer.render(parser.root, "/formular/elektro")
        self.assertIn("Text před hledáním", rendered)
        self.assertIn("Text za hledáním", rendered)
        self.assertNotIn("<form", rendered)
        self.assertNotIn("<input", rendered)
        self.assertNotIn("/formular/", rendered)
        self.assertEqual(warnings, ["Skipped search form on https://www.restyl.cz/elektro/"])

    def test_unrecognized_form_is_skipped_and_reported(self):
        parser = TreeParser()
        parser.feed('<form action="/submit"><input name="email" value="sensitive"></form>')
        warnings = []
        sanitizer = PageSanitizer("https://www.restyl.cz/plan/", Path("content/assets"), {}, warnings)
        rendered = sanitizer.render(parser.root, "/formular/elektro")
        self.assertEqual(rendered, "")
        self.assertEqual(warnings, ["Skipped unrecognized form on https://www.restyl.cz/plan/"])
        self.assertNotIn("sensitive", str(warnings))

    def test_search_marker_overrides_contact_class(self):
        rendered = self.render('<form role="search" class="wpcf7-form"><input name="s"></form>')
        self.assertNotIn("/formular/", rendered)

    def test_home_slider_contact_is_a_working_link(self):
        source = '<div class="tp-caption rev-btn" data-actions="ignored">KONTAKT </div>'
        rendered = self.render(source, "https://www.restyl.cz/")
        self.assertIn('<a class="tp-caption rev-btn" href="/kontakt/">KONTAKT</a>', rendered)
        self.assertNotIn("data-actions", rendered)
        self.assertNotIn('href="/kontakt/"', self.render(source))

    def test_counter_uses_safe_numeric_target(self):
        rendered = self.render(
            '<span class="counter-number" data-to="2598">0</span>'
            '<span class="counter-number" data-to="unsafe">0</span>'
        )
        self.assertIn("<span>2598</span>", rendered)
        self.assertIn("<span>0</span>", rendered)
        self.assertNotIn("data-to", rendered)

    def test_only_exact_contact_form_class_is_recognized(self):
        rendered = self.render('<form class="wpcf7-form-fake"></form><form class="wpcf7-form"></form>')
        self.assertEqual(rendered.count('href="/formular/elektro"'), 1)

    def test_internal_absolute_url_becomes_local_path(self):
        self.assertEqual(
            internal_url("https://www.restyl.cz/kontakt/?from=home#map", "https://www.restyl.cz/"),
            "/kontakt/?from=home#map",
        )

    def test_contact_links_are_preserved(self):
        self.assertEqual(
            internal_url("mailto:info@example.cz?subject=Dotaz", "https://www.restyl.cz/"),
            "mailto:info@example.cz?subject=Dotaz",
        )
        self.assertEqual(
            internal_url("tel:+420123456789", "https://www.restyl.cz/"),
            "tel:+420123456789",
        )

    def test_preserves_only_structural_class_allowlist(self):
        rendered = self.render(
            '<div class="vc_row vc_row-fluid unknown" onclick="alert(1)" style="display:none">'
            '<div class="wpb_column vc_col-md-6 vc_col-md-600">'
            '<div class="rev_slider_wrapper wpb_wrapper" id="danger">Text</div></div></div>'
        )
        self.assertIn('<div class="vc_row vc_row-fluid">', rendered)
        self.assertIn('<div class="wpb_column vc_col-md-6">', rendered)
        self.assertIn('<div class="rev_slider_wrapper wpb_wrapper">', rendered)
        for forbidden in ("unknown", "onclick", "style=", "vc_col-md-600", 'id='):
            self.assertNotIn(forbidden, rendered)

    def test_jumbotron_class_is_preserved_only_on_divs(self):
        rendered = self.render('<div class="jumbotron"><p class="jumbotron">Text</p></div>')
        self.assertEqual(rendered, '<div class="jumbotron"><p>Text</p></div>')

    def test_sidebar_wrapper_is_retained_without_unsafe_attributes(self):
        rendered = self.render(
            '<div class="row"><div class="col-md-9">Content</div>'
            '<aside class="sidebar sidebar-right col-md-3" onclick="bad()">'
            '<div>Menu</div><div>Contact</div></aside></div>'
        )
        self.assertIn('<div class="col-md-3"><div>Menu</div><div>Contact</div></div>', rendered)
        self.assertNotIn("onclick", rendered)
        self.assertNotIn("sidebar-right", rendered)

    def test_injected_class_values_and_unsafe_attributes_are_removed(self):
        rendered = self.render(
            '<div class="vc_row&quot; onmouseover=&quot;bad() vc_col-md-12" '
            'data-evil="x" style="background:url(javascript:x)">safe</div>'
        )
        self.assertNotIn("onmouseover", rendered)
        self.assertNotIn("javascript", rendered)
        self.assertNotIn("data-evil", rendered)
        self.assertNotIn("style", rendered)
        self.assertIn("vc_col-md-12", rendered)

    def test_drupal_allowlist_matches_sanitizer(self):
        config = Path(__file__).parent / "format/filter.format.restyl_html.yml"
        tags = re.findall(r"<([a-z0-9]+)([^>]*)>", config.read_text())
        self.assertGreater(len(tags), 20)
        for tag, attrs in tags:
            if tag != "tfoot":
                match = re.search(r'class="([^"]+)"', attrs)
                self.assertIsNotNone(match, tag)
                expected_classes = ALLOWED_CLASSES if tag == "div" else ALLOWED_CLASSES - {"jumbotron"}
                self.assertEqual(set(match.group(1).split()), expected_classes, tag)


if __name__ == "__main__":
    unittest.main()
