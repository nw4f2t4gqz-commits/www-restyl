<?php

use Drupal\ckeditor5\Plugin\Editor\CKEditor5;
use Drupal\editor\Entity\Editor;
use Drupal\filter\Entity\FilterFormat;
use Symfony\Component\Yaml\Yaml;

$directory = __DIR__ . '/format/';
$filter_data = Yaml::parseFile($directory . 'filter.format.restyl_html.yml');
$editor_data = Yaml::parseFile($directory . 'editor.editor.restyl_html.yml');
$format = FilterFormat::create($filter_data);
$editor = Editor::create($editor_data);
(new ReflectionObject($editor))->getProperty('filterFormat')->setValue($editor, $format);
$violations = CKEditor5::validatePair($editor, $format);
if (count($violations)) {
  foreach ($violations as $violation) {
    print $violation->getPropertyPath() . ': ' . strip_tags((string) $violation->getMessage()) . "\n";
  }
  throw new RuntimeException('CKEditor and proposed text format are incompatible.');
}

$filter = \Drupal::service('plugin.manager.filter')->createInstance('filter_html', [
  'settings' => $filter_data['filters']['filter_html']['settings'],
]);
$input = '<div class="vc_row jumbotron unknown" onclick="alert(1)" style="color:red">'
  . '<p class="jumbotron">Not an allowed jumbotron element</p>'
  . '<div class="wpb_column vc_col-md-6 vc_col-md-99">'
  . '<div class="rev_slider_wrapper wpb_wrapper" id="untrusted">Content</div></div></div>'
  . '<img src="/test.png" alt="Test" data-entity-uuid="12345678-1234-1234-1234-123456789abc" data-entity-type="file" onerror="alert(1)">'
  . '<script>danger()</script><a href="javascript:alert(1)">link</a>';
$output = $filter->process($input, 'cs')->getProcessedText();
foreach (['class="vc_row jumbotron"', 'class="wpb_column vc_col-md-6"', 'class="rev_slider_wrapper wpb_wrapper"', 'data-entity-uuid="12345678-1234-1234-1234-123456789abc"', 'data-entity-type="file"'] as $required) {
  if (!str_contains($output, $required)) {
    throw new RuntimeException("Safe structure did not survive Drupal filter: {$required}");
  }
}
foreach (['unknown', 'onclick', 'onerror', 'style=', 'vc_col-md-99', ' id=', '<script', 'javascript:', '<p class="jumbotron">'] as $forbidden) {
  if (str_contains($output, $forbidden)) {
    throw new RuntimeException("Unsafe markup survived Drupal filter: {$forbidden}");
  }
}
print "CKEditor/format compatibility and Drupal HTML sanitization passed.\n";
