# coding=utf-8
import json
import threading
import re
from time import time, sleep
from urllib import quote

from datetime import datetime
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
        if not self.config_check(self.c):
            raise Exception('malformed config file. check your set up')
        self.tid = tid  # Thread id number
        self.auth_token = ''  # Stores the current auth token. Should be re-scraped after every step of checkout
        self.ship_data = None
        self.total_cost = None
        self.gateway_id = None
        self.cap_response = None
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

    def config_check(self, config):
        log(self.tid, 'validating config file')
        if config['checkout_mode'] != ('dummy_bypass' or '2cap'):
            log(self.tid, 'unrecognized checkout_mode')
            return False
        if config['shipping_get_method'] != ('normal' or 'advanced'):
            log(self.tid, 'unrecognized shipping_get_method')
            return False
        if config['product_scrape_method'] != ('atom' or 'json' or 'xml' or 'oembed'):
            log(self.tid, 'unrecognized product_scrape_method')
            return False
        if (config['checkout_mode'] == '2cap') and (config['2cap_api_key'] == ('YOURAPIKEYHERE' or None or '')):
            log(self.tid, 'checkout mode set to use 2captcha but no api key provided')
            return False
        if (config['checkout_mode'] == 'dummy_bypass') and (config['dummy_variant'] == (None or '')):
            log(self.tid, 'checkout mode set to bypass but no dummy variant provided')
            return False

    def refresh_poll(self):
        # sleeps a set amount of time. see config
        log(self.tid, 'waiting {} second(s) before refreshing'.format(self.c['poll_time']))
        sleep(self.c['poll_time'])
        return

    def is_sold_out(self, url):
        # returns true if sold out, otherwise returns false
        if 'stock_problems' in url:
            log(self.tid, 'sold out :(')
            return True
        return False

    def is_in_queue(self, url):
        # returns true once the url is through the queue
        # TODO: make this fx poll the js instead of the checkout page
        while 'queue' in url:
            log(self.tid, 'in queue...polling until through')
            self.S.get(url, headers=self.headers)
            sleep(1)
        return True

    def is_captcha(self, source):
        # checks page response for captcha presence and returns true if so
        if 'g-recaptcha' in source:
            log(self.tid, 'detected captcha in page source')
            return True
        return False

    def get_sitekey(self, source):
        # finds the captcha site key from the page source
        log(self.tid, 'finding captcha sitekey')
        return re.findall('sitekey: "(.*?)"', source)[0]

    def get_captcha_token(self, sitekey, host_url):
        # returns a usable captcha token based from the sitekey
        host = 'https://' + host_url.split('/')[2]
        log(self.tid, 'getting captcha response for sitekey {} and host {}'.format(sitekey, host))
        if self.c['checkout_mode'] == '2cap':
            s = requests.Session()
            captcha_id = s.post(
                'http://2captcha.com/in.php?key={}&method=userrecaptcha&googlekey={}&pageurl={}'.format(
                    self.c['2cap_api_key'],
                    sitekey,
                    host
                )
            ).text.split('|')[1]
            answer = s.get(
                'http://2captcha.com/res.php?key={}&action=get&id={}'.format(
                    self.c['2cap_api_key'],
                    captcha_id)
            ).text
            while 'CAPCHA_NOT_READY' in answer:
                log(self.tid, 'checking 2captcha response')
                if 'ERROR' in answer:
                    log(self.tid, 'error: {}'.format(answer))
                    exit(-1)
                sleep(5)
                answer = s.get(
                    'http://2captcha.com/res.php?key={}&action=get&id={}'.format(
                        self.c['2cap_api_key'],
                        captcha_id)
                ).text
            token = answer.split('|')[1]
            log(self.tid, 'got token {}'.format(token))
            return token
        else:
            log(self.tid, 'error: checkout mode is set to {}'.format(self.c['checkout_mode']))
            log(self.tid, 'if bypass is turned on, get_captcha_token() shoudnt be called')
            exit(-1)

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
        self.gateway_id = re.findall('data-brand-icons-for-gateway="(.*?)"', source)[0]
        log(self.tid, 'found payment gateway id {}'.format(self.gateway_id))
        return

    def get_shipping_info(self, checkout_url):
        if self.c['shipping_get_method'] == 'normal':
            log(self.tid, 'gathering shipping info (normal method)')
            r = self.S.get(
                checkout_url,
                headers=self.headers
            )
            r.raise_for_status()
            self.ship_data = re.findall('data-backup="(.*?)"', r.text)[0]
        elif self.c['shipping_get_method'] == 'advanced':
            # JSON SHIPPING METHOD (USE FOR SITES THAT DONT HAVE PRODUCTS LOADED)
            log(self.tid, 'gathering shipping info (advanced method)')
            params = {
                'shipping_address[zip]': self.c['checkout']['zip'],
                'shipping_address[country]': 'United States',
                'shipping_address[province]': self.c['checkout']['state']
            }
            r = self.S.get(
                self.c['site'] + '/cart/shipping_rates.json',
                params=params,
                headers=self.headers
            )
            r.raise_for_status()
            r = r.json()
            self.ship_data = '{}-{}-{}'.format(
                r['shipping_rates'][0]['source'],
                r['shipping_rates'][0]['code'],
                r['shipping_rates'][0]['price']
            )
            self.ship_data = quote(self.ship_data, safe='()')
        else:
            log(self.tid, 'malformed shipping get method in config')
            log(self.tid, 'acceptable configurations: "normal" or "advanced"')
            exit(-1)
        log(self.tid, 'found shipping method {}'.format(self.ship_data))
        return

    def get_products(self):
        # scrapes all products on the site
        # returns a list of product objects
        if self.c['product_scrape_method'] == 'atom':
            log(self.tid, 'fetching product list (atom method)')
            url = self.c['site'] + '/collections/footwear.atom'
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
        elif self.c['product_scrape_method'] == 'json':
            log(self.tid, 'fetching product list (json method)')

        elif self.c['product_scrape_method'] == 'xml':
            log(self.tid, 'fetching product list (xml method)')

        elif self.c['product_scrape_method'] == 'oembed':
            log(self.tid, 'fetching product list (oembed method)')

        else:
            log(self.tid, 'malformed product scrape method in config')
            log(self.tid, 'acceptable configurations: "atom", "xml", "json", or "oembed"')
            exit(-1)

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

    def remove_from_cart(self, quantity, position):
        # changes the quantity/position of an item in the cart.
        log(self.tid, 'removing {} item from position {}'.format(quantity, position))
        payload = {
            'quantity': quantity,
            'line': position
        }
        r = self.S.post(
            self.c['site'] + '/cart/change.js',
            data=payload,
            headers=self.form_headers
        )
        r.raise_for_status()
        r = r.json()
        log(self.tid, 'current cart quantity: {}'.format(r['item_count']))
        return

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
        if self.is_captcha(r.text):
            sitekey = self.get_sitekey(r.text)
            self.cap_response = self.get_captcha_token(sitekey, checkout_url)
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
            'checkout[client_details][browser_height]': '1903',
            'checkout[client_details][browser_width]': '960',
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
        if self.cap_response is not None:
            # adds captcha response to payload if we have one
            payload['g-recaptcha-response'] = self.cap_response
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()
        if self.is_sold_out(r.url):
            return False
        self.get_auth_token(r.text)
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
        self.form_headers['Referrer'] = checkout_url
        self.form_headers['Origin'] = checkout_url
        r = self.S.post(
            checkout_url + '/shipping_rates?step=shipping_method',
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()
        if self.is_sold_out(r.url):
            return False
        self.get_auth_token(r.text)
        self.get_total_cost(r.text)
        self.get_gateway_id(r.text)
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
        return True

    def run(self):
        if self.c['checkout_mode'] == '2cap':
            log(self.tid, 'selected 2captcha checkout mode (no bypass)')
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
                # if a match isnt found, have the user select the size manually
                log(self.tid, 'couldnt match variant against selected size, please pick numerically\n')
                i = 0
                for v in product_variants:
                    print '#{} - SIZE {}'.format(str(i).zfill(2), v.size)
                    i += 1
                x = raw_input('please enter a product index #\n> ')
                try:
                    if 0 < int(x) < len(product_variants):
                        selected_variant = product_variants[int(x)]
                    else:
                        log(self.tid, 'error selection {} not in range'.format(x))
                except ValueError:
                    log(self.tid, 'error please enter a number')
            try:
                checkout_url = self.add_to_cart(selected_variant)
                checkout_url = self.open_checkout(checkout_url)
                checkout_url = self.submit_customer_info(checkout_url)
                checkout_url = self.submit_shipping_info(checkout_url)
                payment_id = self.submit_payment_info()
                if self.submit_order(checkout_url, payment_id):
                    log(self.tid, 'order submitted successfully. check email {}'.format(self.c['checkout']['email']))
                    log(self.tid, 'time to return {} sec'.format(abs(self.start_time-time())))
            except requests.exceptions.MissingSchema:
                log(self.tid, 'error: a request was passed a null url')
                exit(-1)
        elif self.c['checkout_mode'] == 'dummy_bypass':
            log(self.tid, 'selected dummy bypass mode')
            log(self.tid, 'adding dummy product to cart')
            # add and start dummy product checkout
            try:
                checkout_url = self.add_to_cart(Variant(self.c['dummy_variant'], None))  # Kith jason markk cleaning shit
                checkout_url = self.open_checkout(checkout_url)
                checkout_url = self.submit_customer_info(checkout_url)
            except requests.exceptions.MissingSchema:
                log(self.tid, 'error: a request was passed a null url')
                exit(-1)
            # wait for timer
            log(self.tid, 'waiting for drop time {}'.format(self.c['drop_timer']))
            while True:
                if datetime.now().strftime('%H:%M:%S') >= self.c['drop_timer']:
                    log(self.tid, 'drop timer passed...continuing with checkout')
                    break
                sleep(1)
            # find the actual product
            while True:
                product_list = self.get_products()
                product_match = self.check_products(product_list)
                if product_match is not None:
                    log(self.tid, 'found matching product - {}'.format(product_match.url))
                    break
                self.refresh_poll()
            product_variants = self.get_product_info(product_match)
            selected_variant = self.check_variants(product_variants)
            self.add_to_cart(selected_variant)  # dont use the new checkout url
            # remove dummy product from cart
            self.remove_from_cart(0, 2)
            # refresh the checkout page
            r = self.S.get(
                checkout_url,
                headers=self.headers
            )
            r.raise_for_status()
            # finish checkout
            checkout_url = self.submit_shipping_info(checkout_url)
            payment_id = self.submit_payment_info()
            if self.submit_order(checkout_url, payment_id):
                log(self.tid, 'order submitted successfully. check email {}'.format(self.c['checkout']['email']))
                log(self.tid, 'time to return {} sec'.format(abs(self.start_time - time())))
        else:
            log(self.tid, 'malformed checkout mode in config')
            log(self.tid, 'acceptable configurations: "2cap" or "dummy_bypass"')
            exit(-1)

