# coding=utf-8
import json
import threading
import re
from time import time, sleep

import requests

from classes.product import Product
from classes.variant import Variant
from classes.logger import Logger

log = Logger().log


class Shopify(threading.Thread):
    def __init__(self, config_filename, tid):
        self.start_time = time()
        threading.Thread.__init__(self)
        with open(config_filename) as config:
            self.c = json.load(config)
        self.tid = tid
        self.auth_token = ''
        self.ship_data = None  # preset shipping info data. leave None if you want to scrape the first method instead
        self.S = requests.Session()
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/58.0.3029.81 Safari/537.36',
            'Content-Type': '',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Host': self.c['site'].split('//')[1],
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'
        }
        self.form_headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/58.0.3029.81 Safari/537.36',
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Cache-Control': 'max-age=0',
            'Connection': 'keep-alive',
            'Host': self.c['site'].split('//')[1],
            'Upgrade-Insecure-Requests': '1',
            'DNT': '1'
        }
        log(self.tid, 'shopify ATC by Alex++ @edzart/@573supreme')

    def refresh_poll(self):
        log(self.tid, 'waiting {} second(s) before refreshing'.format(self.c['poll_time']))
        sleep(self.c['poll_time'])

    def is_sold_out(self, url):
        # returns true if sold out, otherwise returns false
        if 'stock_problems' in url:
            log(self.tid, 'sold out')
            return True
        return False

    def get_auth_token(self, source):
        self.auth_token = re.findall('name="authenticity_token" value="(.*?)"', source)[2]
        log(self.tid, 'got new auth token {}'.format(self.auth_token))
        return

    def get_products(self):
        # scrapes all products on the site
        # returns a list of product objects
        log(self.tid, 'fetching product list')
        url = self.c['site'] + '/collections/all.atom'
        r = self.S.get(
            url,
            headers=self.headers,
            allow_redirects=False
        )
        r.raise_for_status()
        product_urls = re.findall('<link rel="alternate" type="text/html" href="(.*?)"/>', r.text)
        product_urls.pop(0)  # Remove first link from list (map base link)
        product_titles = re.findall('<title>(.*?)</title>\s*<s:type', r.text)
        product_objects = []
        if len(product_urls) != len(product_titles):
            raise Exception('mismatched product indices')
        log(self.tid, 'scraped {} products'.format(len(product_urls)))
        for i in range(0, len(product_urls)):
            # log(self.tid, '{}'.format(product_titles[i]))
            product_objects.append(Product(product_titles[i], product_urls[i]))
        return product_objects

    def check_products(self, product_list):
        # compares a list of product objects against keywords
        # returns a single product object
        log(self.tid, 'comparing product list against keywords')
        if len(product_list) < 1:
            raise Exception('cant check empty product list')
        for prod in product_list:
            match = True
            for key in self.c['product']['positive_kw'].split(','):
                if key not in prod.name.lower():
                    match = False
            for key in self.c['product']['negative_kw'].split(','):
                if key in prod.name.lower():
                    match = False
            if match:
                return prod
        return None

    def get_product_info(self, product):
        # take a product and returns a list of variant objects
        log(self.tid, 'getting product info')
        if product is None:
            raise Exception('cant open empty product')
        r = self.S.get(
            product.url + '.json',
            headers=self.headers,
            allow_redirects=False
        )
        r.raise_for_status()
        try:
            r = r.json()
        except ValueError:
            raise Exception('got non-json response while opening product')
        variant_objects = []
        size_field = self.c['size_field']
        log(self.tid, 'title: {} :: price: ${}'.format(r['product'][size_field], r['product']['variants'][0]['price']))
        for var in r['product']['variants']:
            log(self.tid, '{} :: {}'.format(var['id'], var[size_field]))
            variant_objects.append(Variant(var['id'], var[size_field]))
        return variant_objects

    def check_variants(self, variant_list):
        # takes a list of variants and searches for a matching size
        log(self.tid, 'comparing variants against configured size')
        for var in variant_list:
            if self.c['product']['size'] == var.size:
                log(self.tid, 'found matching variant - {}'.format(var.id))
                return var
        return None

    def add_to_cart(self, variant):
        # adds a selected variant object to cart and returns the checkout url
        log(self.tid, 'adding variant to cart')
        if variant is None:
            raise Exception('cant add empty variant to cart')
        payload = {
            'id': variant.id,
            'quantity': '1'
        }
        r = self.S.post(
            self.c['site'] + '/cart/add.js',
            headers=self.form_headers,
            data=payload,
            allow_redirects=False
        )
        r.raise_for_status()
        log(self.tid, 'getting checkout page')
        r = self.S.post(
            self.c['site'] + '/cart',
            headers=self.form_headers,
            data='updates%5B%5D=1&note=&checkout=Check+Out',
            allow_redirects=False
        )
        r.raise_for_status()
        return r.text.split('"')[1]

    def open_checkout(self, checkout_url):
        log(self.tid, 'opening checkout page {}'.format(checkout_url))
        r = self.S.get(
            checkout_url,
            headers=self.headers
        )
        r.raise_for_status()
        if self.is_sold_out(r.url):
            return False
        self.get_auth_token(r.text)
        return r.url

    def submit_customer_info(self, checkout_url):
        log(self.tid, 'submitting customer info')
        payload = {
            '_method': 'patch',
            'authenticity_token': self.auth_token,
            'button': '',
            'checkout[buyer_accepts_marketing]': '1',
            'checkout[client_details][browser_height]': '640',
            'checkout[client_details][browser_width]': '497',
            'checkout[client_details][javascript_enabled]': '1',
            'checkout[email]': self.c['checkout']['email'],
            'checkout[remember_me]': 'false',
            'checkout[shipping_address][address1]': self.c['checkout']['addr1'],
            'checkout[shipping_address][address2]': self.c['checkout']['addr2'],
            'checkout[shipping_address][city]': self.c['checkout']['city'],
            'checkout[shipping_address][country]': 'United States',
            'checkout[shipping_address][first_name]': self.c['checkout']['fname'],
            'checkout[shipping_address][last_name]': self.c['checkout']['lname'],
            'checkout[shipping_address][phone]': self.c['checkout']['phone'],
            'checkout[shipping_address][province]': self.c['checkout']['state'],
            'checkout[shipping_address][zip]': self.c['checkout']['zip'],
            'previous_step': 'contact_information',
            'step': 'shipping_method',
            'utf8': '✓'
        }
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()
        if self.is_sold_out(r.url):
            return False
        self.get_auth_token(r.text)
        if self.ship_data is None:
            self.ship_data = self.get_shipping_info(r.text)
        return r.url

    def get_shipping_info(self, source):
        log(self.tid, 'gathering shipping info')
        return re.findall('data-backup="(.*?)"', source)[0]

    def submit_shipping_info(self,):

    def run(self):
        while True:
            product_list = self.get_products()
            product_match = self.check_products(product_list)
            if product_match is not None:
                log(self.tid, 'found matching product - {}'.format(product_match.url))
                break
            self.refresh_poll()
        product_variants = self.get_product_info(product_match)
        selected_variant = self.check_variants(product_variants)
        while selected_variant is None:
            log(self.tid, 'couldnt match variant against selected size, please pick numerically\n')
            i = 0
            for v in product_variants:
                print '{} :: {}'.format(i, v.title)
                i += 1
            exit(-1)
        checkout_url = self.add_to_cart(selected_variant)
        checkout_url = self.open_checkout(checkout_url)
