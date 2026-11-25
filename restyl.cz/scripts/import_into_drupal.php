<?php

use Drupal\Core\File\FileSystemInterface;
use Drupal\Core\Language\LanguageInterface;
use Drupal\node\Entity\Node;
use Drupal\node\Entity\NodeType;
use Drupal\Component\Utility\Xss;

/**
 * Import the sanitized public snapshot into editable Drupal Basic pages.
 *
 * Run from the Drupal project root with Drush php:script. This intentionally
 * never deletes content and never overwrites a page that no longer matches
 * the last content written by this importer.
 */
if (!class_exists('\Drupal')) {
  throw new RuntimeException('Run this script through Drush after Drupal has bootstrapped.');
}

$project_root = dirname(__DIR__);
$manifest_path = getenv('RESTYL_IMPORT_MANIFEST') ?: $project_root . '/content/pages.json';
$dry_run = getenv('RESTYL_IMPORT_DRY_RUN') === '1';

if (!is_file($manifest_path) || !is_readable($manifest_path)) {
  throw new RuntimeException("Import manifest is not readable: {$manifest_path}");
}
$manifest = json_decode(file_get_contents($manifest_path), TRUE, 512, JSON_THROW_ON_ERROR);
if (($manifest['schema_version'] ?? NULL) !== 1 || !is_array($manifest['pages'] ?? NULL)) {
  throw new RuntimeException('Unsupported or invalid public content manifest.');
}

$page_type = NodeType::load('page');
if (!$page_type) {
  $message = 'The Drupal Basic page content type is not available.';
  if (!$dry_run) {
    throw new RuntimeException($message);
  }
  print "WARNING: {$message} Dry-run will only check snapshot and path conflicts.\n";
}
$format_name = 'restyl_html';
$format = \Drupal::entityTypeManager()->getStorage('filter_format')->load($format_name);
$format_spec = $project_root . '/scripts/format/filter.format.restyl_html.yml';
if (!is_readable($format_spec)) {
  throw new RuntimeException('The proposed Restyl format specification is missing.');
}
$format_data = \Symfony\Component\Yaml\Yaml::parseFile($format_spec);
$safe_filter_settings = $format_data['filters']['filter_html']['settings'];
if (!$format || !$format->status() || !$format->filters('filter_html')->status || $format->filters('filter_html')->settings['allowed_html'] !== $safe_filter_settings['allowed_html']) {
  $message = 'The exact enabled restyl_html format with its allowlist is not configured; see scripts/README.md.';
  if (!$dry_run) {
    throw new RuntimeException($message);
  }
  print "WARNING: {$message} Dry-run continues using the proposed filter in memory.\n";
}
$safe_filter = \Drupal::service('plugin.manager.filter')->createInstance('filter_html', ['settings' => $safe_filter_settings]);

$allowed_tags = [
  'a', 'b', 'blockquote', 'br', 'caption', 'div', 'em', 'figcaption', 'figure',
  'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li', 'ol', 'p', 'span',
  'strong', 'table', 'tbody', 'td', 'th', 'tfoot', 'thead', 'tr', 'u', 'ul',
];
$file_system = \Drupal::service('file_system');
$public_directory = 'public://restyl-import';
if (!$dry_run && !$file_system->prepareDirectory($public_directory, FileSystemInterface::CREATE_DIRECTORY | FileSystemInterface::MODIFY_PERMISSIONS)) {
  throw new RuntimeException('Could not prepare the public media directory.');
}
$public_realpath = $dry_run ? NULL : $file_system->realpath($public_directory);
if (!$dry_run && !is_string($public_realpath)) {
  throw new RuntimeException('Could not resolve the Drupal public media directory.');
}

$asset_urls = [];
foreach (($manifest['assets'] ?? []) as $name => $asset) {
  if (!is_string($name) || !preg_match('/\A[a-f0-9]{20}\.(?:avif|gif|jpe?g|pdf|png|webp)\z/i', $name)) {
    throw new RuntimeException('Unsafe media filename in the import manifest.');
  }
  $relative_path = $asset['file'] ?? '';
  if ($relative_path !== 'assets/' . $name) {
    throw new RuntimeException("Unexpected media path for {$name}.");
  }
  $source_path = $project_root . '/content/' . $relative_path;
  $real_source = realpath($source_path);
  $real_asset_root = realpath($project_root . '/content/assets');
  if (!$real_source || !$real_asset_root || !str_starts_with($real_source, $real_asset_root . DIRECTORY_SEPARATOR) || !is_file($real_source)) {
    throw new RuntimeException("Media file is missing or outside content/assets: {$name}");
  }
  $actual_hash = hash_file('sha256', $real_source);
  if (!hash_equals((string) ($asset['sha256'] ?? ''), $actual_hash)) {
    throw new RuntimeException("Media checksum mismatch: {$name}");
  }
  $uri = $public_directory . '/' . $name;
  $destination_path = $file_system->realpath($uri);
  if (!$dry_run && is_string($destination_path) && is_file($destination_path)) {
    if (!str_starts_with($destination_path, $public_realpath . DIRECTORY_SEPARATOR)) {
      throw new RuntimeException("Media path resolves outside the Drupal public directory: {$name}");
    }
    $existing_hash = hash_file('sha256', $destination_path);
    if (!is_string($existing_hash) || !hash_equals($actual_hash, $existing_hash)) {
      throw new RuntimeException("Existing Drupal media differs from the snapshot; refusing to replace it: {$name}");
    }
  }
  elseif (!$dry_run) {
    if (file_exists($uri)) {
      throw new RuntimeException("Drupal media destination is not a regular file: {$name}");
    }
    $file_system->copy($real_source, $uri, FileSystemInterface::EXISTS_ERROR);
    $copied_path = $file_system->realpath($uri);
    if (!is_string($copied_path) || !str_starts_with($copied_path, $public_realpath . DIRECTORY_SEPARATOR) || !is_file($copied_path) || !hash_equals($actual_hash, hash_file('sha256', $copied_path))) {
      throw new RuntimeException("Copied Drupal media failed verification: {$name}");
    }
  }
  $asset_urls[$name] = \Drupal::service('file_url_generator')->generateString($uri);
}

$state = \Drupal::state();
$state_key = 'restyl_public_import.records';
$records = $state->get($state_key, []);
$alias_storage = \Drupal::entityTypeManager()->getStorage('path_alias');
$node_storage = \Drupal::entityTypeManager()->getStorage('node');
$alias_manager = \Drupal::service('path_alias.manager');
$langcode = \Drupal::languageManager()->getDefaultLanguage()->getId() ?: LanguageInterface::LANGCODE_NOT_SPECIFIED;
$counts = ['created' => 0, 'updated' => 0, 'unchanged' => 0, 'conflict' => 0, 'skipped' => 0];
$seen_paths = [];

$managed_hash = static function (string $title, string $body, string $format, string $alias): string {
  return hash('sha256', json_encode([$title, $body, $format, $alias], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
};

$transaction = $dry_run ? NULL : \Drupal::database()->startTransaction();
try {
  foreach ($manifest['pages'] as $page) {
    if (!is_array($page)) {
      throw new RuntimeException('Invalid page entry in the manifest.');
    }
    $alias = $page['path'] ?? '';
    $title = $page['title'] ?? '';
    $body = $page['body'] ?? '';
    if (!is_string($alias) || !preg_match('#\A/(?:[A-Za-z0-9._~-]+/)*\z#', $alias) || str_contains($alias, '..') || !is_string($title) || trim($title) === '' || !is_string($body)) {
      throw new RuntimeException('Invalid title, body, or Drupal path in the manifest.');
    }
    if (isset($seen_paths[$alias])) {
      throw new RuntimeException("Duplicate Drupal path in manifest: {$alias}");
    }
    $seen_paths[$alias] = TRUE;
    $body = preg_replace_callback(
      '/\b(src|href)=(["\'])restyl-asset:([a-f0-9]{20}\.(?:avif|gif|jpe?g|pdf|png|webp))\2/i',
      static function (array $match) use ($asset_urls): string {
        if (!isset($asset_urls[$match[3]])) {
          throw new RuntimeException("Unknown local media asset: {$match[3]}");
        }
        return $match[1] . '=' . $match[2] . htmlspecialchars($asset_urls[$match[3]], ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8') . $match[2];
      },
      $body
    );
    if (preg_match('/\b(?:src|href)=(["\'])restyl-asset:/i', $body)) {
      throw new RuntimeException("Malformed local media reference in {$alias}.");
    }
    $body = Xss::filter($body, $allowed_tags);
    $body = $safe_filter->process($body, $langcode)->getProcessedText();
    $source_hash = hash('sha256', json_encode([
      $title,
      $body,
      $format_name,
      $page['description'] ?? '',
      $page['source_lastmod'] ?? '',
    ], JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES | JSON_THROW_ON_ERROR));
    $body_format = $format_name;
    $drupal_alias = $alias === '/' ? NULL : rtrim($alias, '/');

    $record = $records[$alias] ?? NULL;
    $node = NULL;
    if (is_array($record) && !empty($record['uuid'])) {
      $matches = $node_storage->loadByProperties(['uuid' => $record['uuid']]);
      $node = $matches ? reset($matches) : NULL;
      if (!$node) {
        $counts['skipped']++;
        print "SKIP {$alias}: previously imported page was deleted; it will not be recreated.\n";
        continue;
      }
      if ($node->bundle() !== 'page' || !$node->hasField('body')) {
        $counts['conflict']++;
        print "CONFLICT {$alias}: imported node type or body field changed.\n";
        continue;
      }
      $current_alias = $alias_manager->getAliasByPath('/node/' . $node->id(), $node->language()->getId());
      $current_hash = $managed_hash($node->label(), (string) $node->get('body')->value, (string) $node->get('body')->format, $current_alias);
      if (!hash_equals((string) ($record['managed_hash'] ?? ''), $current_hash) && $drupal_alias !== NULL && $current_alias === $drupal_alias) {
        // Earlier imports recorded the public trailing slash, which Drupal
        // automatically strips from path alias entities.
        $current_hash = $managed_hash($node->label(), (string) $node->get('body')->value, (string) $node->get('body')->format, $alias);
      }
      if (!hash_equals((string) ($record['managed_hash'] ?? ''), $current_hash)) {
        $counts['conflict']++;
        print "CONFLICT {$alias}: Drupal page or path alias was edited; leaving it untouched.\n";
        continue;
      }
      if (!isset($record['revision_id'])) {
        $counts['conflict']++;
        print "CONFLICT {$alias}: older import record has no revision baseline; review the page manually.\n";
        continue;
      }
      if ((int) $record['revision_id'] !== (int) $node->getRevisionId()) {
        $counts['conflict']++;
        print "CONFLICT {$alias}: Drupal page has a new revision; leaving it untouched.\n";
        continue;
      }
      if (hash_equals((string) ($record['source_hash'] ?? ''), $source_hash)) {
        $counts['unchanged']++;
        print "UNCHANGED {$alias}\n";
        if ($alias === '/') {
          print "FRONT PAGE: configure system.site page.front to /node/{$node->id()} after review; current value is " . \Drupal::config('system.site')->get('page.front') . ".\n";
        }
        continue;
      }
      if (!$dry_run) {
        $node->setTitle($title);
        $node->set('body', ['value' => $body, 'format' => $body_format]);
        $node->setNewRevision(TRUE);
        $node->setRevisionLogMessage('Public content snapshot refreshed; no local edits detected.');
        $node->save();
      }
      $counts['updated']++;
      $node_uuid = $record['uuid'];
      print ($dry_run ? 'WOULD UPDATE ' : 'UPDATED ') . "{$alias}\n";
    }
    else {
      $collisions = $drupal_alias === NULL ? [] : $alias_storage->loadByProperties(['alias' => $drupal_alias]);
      if ($collisions) {
        $counts['conflict']++;
        print "CONFLICT {$alias}: path alias already belongs to existing content; leaving it untouched.\n";
        continue;
      }
      if (!$dry_run) {
        $node = Node::create([
          'type' => 'page',
          'title' => $title,
          'uid' => \Drupal::currentUser()->id(),
          'langcode' => $langcode,
          'status' => 1,
          'created' => !empty($page['source_lastmod']) ? (strtotime($page['source_lastmod']) ?: \Drupal::time()->getRequestTime()) : \Drupal::time()->getRequestTime(),
          'body' => ['value' => $body, 'format' => $body_format],
        ]);
        $node->save();
        if ($drupal_alias !== NULL) {
          $alias_storage->create([
            'path' => '/node/' . $node->id(),
            'alias' => $drupal_alias,
            'langcode' => $langcode,
          ])->save();
        }
        $node_uuid = $node->uuid();
      }
      else {
        $node_uuid = 'dry-run';
      }
      $counts['created']++;
      print ($dry_run ? 'WOULD CREATE ' : 'CREATED ') . "{$alias}\n";
    }

    $managed_alias = $drupal_alias ?? ($dry_run ? '/node/DRY_RUN' : '/node/' . $node->id());
    $records[$alias] = [
      'uuid' => $node_uuid,
      'source_hash' => $source_hash,
      'managed_hash' => $managed_hash($title, $body, $body_format, $managed_alias),
      'revision_id' => $dry_run ? NULL : (int) $node->getRevisionId(),
      'source_url' => $page['source_url'] ?? '',
      'source_lastmod' => $page['source_lastmod'] ?? '',
      'description' => $page['description'] ?? '',
    ];
    if ($alias === '/') {
      print $dry_run
        ? "FRONT PAGE: configure system.site page.front to the new homepage node path after import; current value is " . \Drupal::config('system.site')->get('page.front') . ".\n"
        : "FRONT PAGE: configure system.site page.front to /node/{$node->id()} after review; current value is " . \Drupal::config('system.site')->get('page.front') . ".\n";
    }
  }
  if (!$dry_run) {
    $state->set($state_key, $records);
  }
}
catch (Throwable $exception) {
  if ($transaction) {
    $transaction->rollBack();
  }
  throw $exception;
}

print ($dry_run ? 'Dry run complete. ' : 'Import complete. ') . json_encode($counts, JSON_UNESCAPED_UNICODE) . "\n";
