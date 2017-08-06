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
        self.tid = tid  # Thread id number
        self.auth_token = ''  # Stores the current auth token. Should be re-scraped after every step of checkout
        self.ship_data = None  # You can preset some of these values to maybe save 0.5 seconds during checkout
        self.total_cost = None
        self.gateway_id = None
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
        log(self.tid, 'shopify ATC by Alex++ @edzart/@573supreme')  # gang gang

    def refresh_poll(self):
        # sleeps a set amount of time. see config
        log(self.tid, 'waiting {} second(s) before refreshing'.format(self.c['poll_time']))
        sleep(self.c['poll_time'])
        return

    def is_sold_out(self, url):
        # returns true if sold out, otherwise returns false
        if 'stock_problems' in url:
            log(self.tid, 'sold out')
            return True
        return False

    def get_auth_token(self, source):
        # scrapes a fresh auth token from page source
        self.auth_token = re.findall('name="authenticity_token" value="(.*?)"', source)[2]
        log(self.tid, 'got new auth token {}'.format(self.auth_token))
        return

    def get_total_cost(self, source):
        log(self.tid, 'getting order total')
        self.total_cost = re.findall('data-checkout-payment-due-target="(.*?)"', source)[0]
        log(self.tid, 'found order total {}'.format(self.total_cost))
        return

    def get_gateway_id(self, source):
        log(self.tid, 'getting payment gateway id')
        self.gateway_id = re.findall('data-brand-icons-for-gateway="(.*?)"', source)
        log(self.tid, 'found payment gateway id {}'.format(self.gateway_id))
        return

    def get_shipping_info(self, checkout_url):
        log(self.tid, 'gathering shipping info')
        r = self.S.get(
            checkout_url,
            headers=self.headers
        )
        r.raise_for_status()
        self.ship_data = re.findall('data-backup="(.*?)"', r.text)[0]
        log(self.tid, 'found shipping method {}'.format(self.ship_data))
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
        # adds a selected variant object to cart and returns the new checkout url
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
        # opens the checkout url to scrape auth token and check for sold out
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
        # submits customer information then returns the latest checkout url
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
            self.get_shipping_info(r.url)
        return r.url

    def submit_shipping_info(self, checkout_url):
        log(self.tid, 'submitting shipping info')
        payload = {
            '_method': 'patch',
            'authenticity_token': self.auth_token,
            'button': '',
            'checkout[shipping_rate][id]': self.ship_data,
            'previous_step': 'shipping_method',
            'step': 'payment_method',
            'utf8': '✓'
        }
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        print '\n\n{}\n\n'.format(r.text)
        r.raise_for_status()
        if self.is_sold_out(r.url):
            return False
        self.get_auth_token(r.text)
        self.get_total_cost(r.text)
        if self.gateway_id is None:
            while (self.gateway_id is None) or (self.gateway_id == []):
                self.S.get(r.url, headers=self.headers)
                sleep(5)
                self.get_gateway_id(r.text)
                sleep(5)
        return r.url

    def submit_payment_info(self):
        log(self.tid, 'submitting cc information')
        headers = {
            'Accept': 'application/json',
            'Origin': 'https://checkout.shopifycs.com',
            'Referrer': 'https://checkout.shopifycs.com',
            'Content-Type': 'application/json',
            'Upgrade-Insecure-Requests': '1',
            'Accept-Encoding': 'gzip, deflate, sdch',
            'Accept-Language': 'en-US,en;q=0.8',
            'Cache-Control': 'no-cache',
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_12_4) AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/58.0.3029.81 Safari/537.36'
        }
        payload = {
            "credit_card": {
                "number": self.c['checkout']['cc'],
                "name": self.c['checkout']['fname'] + " " + self.c['checkout']['lname'],
                "month": self.c['checkout']['exp_m'],
                "year": self.c['checkout']['exp_y'],
                "verification_value": self.c['checkout']['cvv']
            }
        }
        r = self.S.request(
            'POST',
            'https://elb.deposit.shopifycs.com/sessions',
            json=payload,
            headers=headers
        )
        r.raise_for_status()
        try:
            log(self.tid, 'getting payment id')
            return r.json()['id']
        except KeyError:
            raise Exception('key error finding payment id')

    def submit_order(self, checkout_url, payment_id):
        log(self.tid, 'submitting order with payment id {}'.format(payment_id))
        payload = {
            '_method': 'patch',
            'authenticity_token': self.auth_token,
            'checkout[billing_address][address1]': '',
            'checkout[billing_address][address2]': '',
            'checkout[billing_address][city]': '',
            'checkout[billing_address][country]': 'United States',
            'checkout[billing_address][first_name]': '',
            'checkout[billing_address][last_name]': '',
            'checkout[billing_address][phone]': '',
            'checkout[billing_address][province]': self.c['checkout']['state'],
            'checkout[billing_address][zip]': '',
            'checkout[client_details][browser_height]': '640',
            'checkout[client_details][browser_width]': '1280',
            'checkout[client_details][javascript_enabled]': '1',
            'checkout[credit_card][vault]': 'false',
            'checkout[different_billing_address]': 'false',
            'checkout[payment_gateway]': self.gateway_id,
            'checkout[total_price]': self.total_cost,
            'complete': '1',
            'previous_step': 'payment_method',
            's': payment_id,
            'step': '',
            'utf8': '✓'
        }
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()

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
        checkout_url = self.submit_customer_info(checkout_url)
        checkout_url = self.submit_shipping_info(checkout_url)
        payment_id = self.submit_payment_info()
        if self.submit_order(checkout_url, payment_id):
            log(self.tid, 'order submitted successfully. check email {}'.format(self.c['checkout']['email']))
            log(self.tid, 'time to return {} sec'.format(abs(self.start_time-time())))

