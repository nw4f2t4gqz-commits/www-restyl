<?php

$databases['default']['default'] = [
  'database' => getenv('DB_NAME') ?: 'restyl',
  'username' => getenv('DB_USER') ?: 'restyl',
  'password' => getenv('DB_PASSWORD') ?: 'restyl_local_dev_only',
  'host' => getenv('DB_HOST') ?: 'database',
  'port' => getenv('DB_PORT') ?: '3306',
  'driver' => 'mysql',
  'prefix' => '',
  'collation' => 'utf8mb4_general_ci',
];

$settings['hash_salt'] = trim(file_get_contents('/var/www/private/hash_salt'));
$settings['config_sync_directory'] = '/var/www/private/config_sync';

$reverse_proxy_address = getenv('RESTYL_REVERSE_PROXY_ADDRESS');
if ($reverse_proxy_address !== FALSE && $reverse_proxy_address !== '') {
  if (filter_var($reverse_proxy_address, FILTER_VALIDATE_IP) === FALSE) {
    throw new \InvalidArgumentException('RESTYL_REVERSE_PROXY_ADDRESS must be an IP address.');
  }
  $settings['reverse_proxy'] = TRUE;
  $settings['reverse_proxy_addresses'] = [$reverse_proxy_address];
  $settings['reverse_proxy_trusted_headers'] = \Symfony\Component\HttpFoundation\Request::HEADER_X_FORWARDED_PROTO;
}

$config['system.site']['mail'] = getenv('RESTYL_MAIL_FROM') ?: '';
$config['system.mail']['interface'] = [
  'default' => 'symfony_mailer',
];
$config['system.mail']['mailer_dsn'] = [
  'scheme' => 'smtp',
  'host' => getenv('MAIL_HOST') ?: 'mailpit',
  'port' => (int) (getenv('MAIL_PORT') ?: 1025),
];
