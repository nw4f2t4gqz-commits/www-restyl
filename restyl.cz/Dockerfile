FROM composer:2 AS drupal-build

WORKDIR /app
COPY composer.json composer.lock ./
RUN composer install --no-dev --prefer-dist --no-interaction --no-progress \
    --ignore-platform-req=ext-gd
COPY . /context/
RUN for path in web/modules/custom/restyl_site web/themes/custom/restyl; do \
        if [ -d "/context/${path}" ]; then \
            mkdir -p "/app/$(dirname "${path}")"; \
            cp -a "/context/${path}" "/app/${path}"; \
        fi; \
    done

FROM php:8.3-apache

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libpng-dev \
        libzip-dev \
    && docker-php-ext-configure gd --with-freetype --with-jpeg \
    && docker-php-ext-install -j"$(nproc)" gd mysqli opcache pdo_mysql zip \
    && a2enmod headers rewrite \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /var/www/html
COPY --from=drupal-build --chown=www-data:www-data /app/ /var/www/html/
COPY docker/apache-vhost.conf /etc/apache2/sites-available/000-default.conf
COPY docker/php.ini /usr/local/etc/php/conf.d/zz-drupal.ini
COPY docker/settings.php /var/www/html/web/sites/default/settings.php
COPY docker/entrypoint.sh /usr/local/bin/restyl-entrypoint

RUN chmod 0755 /usr/local/bin/restyl-entrypoint \
    && mkdir -p /var/www/html/web/sites/default/files \
    && chown -R www-data:www-data /var/www/html/web/sites/default/files \
    && chown www-data:www-data /var/www/html/web/sites/default/settings.php

ENTRYPOINT ["restyl-entrypoint"]
CMD ["apache2-foreground"]
