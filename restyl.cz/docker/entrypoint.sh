#!/bin/sh
set -eu

if [ ! -s /var/www/private/hash_salt ]; then
    mkdir -p /var/www/private
    php -r 'echo bin2hex(random_bytes(32)), PHP_EOL;' > /var/www/private/hash_salt
fi
mkdir -p /var/www/private/config_sync
chown -R www-data:www-data /var/www/private
chmod 0750 /var/www/private
chmod 0640 /var/www/private/hash_salt

exec docker-php-entrypoint "$@"
