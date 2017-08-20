# coding=utf-8
import datetime
import json
import re
import threading
from time import time, sleep
from urllib import quote

import requests
from selenium import webdriver

from classes.logger import Logger
from classes.product import Product
from classes.variant import Variant


class Shopify(threading.Thread):
    def __init__(self, config_filename, tid):
        threading.Thread.__init__(self)
        logger = Logger(tid)
        self.log = logger.log
        self.slack_log = logger.slack_product
        self.start_time = time()
        with open(config_filename) as config:
            self.c = json.load(config)
        self.tid = tid  # Thread id number
        self.auth_token = ''  # Stores the current auth token. Should be re-scraped after every step of checkout
        self.ship_data = None
        self.total_cost = None
        self.gateway_id = None
        self.captcha_task = False
        self.sitekey = None
        self.cap_response = None
        self.S = requests.Session()
        self.driver = webdriver.Chrome()
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
        if self.config_check(self.c):
            self.log('config check passed')
        else:
            exit(-1)

    def config_check(self, config):
        self.log('validating config file')
        if config['checkout_mode'] not in {'2cap', 'dummy_bypass'}:
            self.log('unrecognized checkout_mode')
            return False
        if config['shipping_get_method'] not in {'normal', 'advanced'}:
            self.log('unrecognized shipping_get_method')
            return False
        if config['product_scrape_method'] not in {'atom', 'json', 'xml', 'oembed'}:
            self.log('unrecognized product_scrape_method')
            return False
        if (config['checkout_mode'] == '2cap') and (config['2cap_api_key'] in {'YOURAPIKEYHERE', None, ''}):
            self.log('checkout mode set to use 2captcha but no api key provided')
            return False
        if (config['checkout_mode'] == 'dummy_bypass') and (config['dummy_variant'] in {None, ''}):
            self.log('checkout mode set to bypass but no dummy variant provided')
            return False
        if (config['checkout_mode'] == 'dummy_bypass') and (config['cap_harvest_time'] in {None, ''}):
            self.log('WARNING: checkout mode set to dummy_bypass but no captcha harvest time provided\n'
                     'if a captcha is present after drop time {} then the program will fail because it will not have\n'
                     'a harvested captcha to use. Set captcha harvest time to ~2 mins before drop time')
            return False
        return True

    def refresh_poll(self):
        # sleeps a set amount of time. see config
        self.log('waiting {} second(s) before refreshing'.format(self.c['poll_time']))
        sleep(self.c['poll_time'])
        return

    def sold_out(self, url):
        # returns true if sold out, otherwise returns false
        while 'stock_problems' in url:
            self.log('sold out :(')
            self.refresh_poll()
            r = self.S.get(
                url.split('stock_problems')[0],
                headers=self.headers
            )
            r.raise_for_status()
            url = r.url
        return

    def password(self, url):
        # returns true if the request lands on password, and refreshes base url until through
        while 'password' in url:
            self.log('password page is up')
            self.refresh_poll()
            r = self.S.get(
                self.c['site'],
                headers=self.headers
            )
            r.raise_for_status()
            url = r.url
        return

    def queue(self, url):
        # returns true once the url is through the queue
        # TODO: make this fx poll the js instead of the checkout page
        while 'queue' in url:
            self.log('in queue...polling until through')
            self.refresh_poll()
            r = self.S.get(
                url,
                headers=self.headers
            )
            r.raise_for_status()
            url = r.url
        return

    def is_captcha(self, source):
        # checks page response for captcha presence and returns true if so
        if 'g-recaptcha' in source:
            self.log('detected captcha in page source')
            return True
        return False

    def get_sitekey(self, source):
        # finds the captcha site key from the page source
        self.log('finding captcha sitekey')
        return re.findall('sitekey: "(.*?)"', source)[0]

    def get_captcha_token(self, sitekey, host_url):
        # returns a usable captcha token based from the sitekey
        host = 'https://' + host_url.split('/')[2]
        self.log('getting captcha response for sitekey {} and host {}'.format(sitekey, host))
        # TODO: make this use a captcha class that starts ~5 threads to get a quicker response
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
            self.log('checking 2captcha response')
            if 'ERROR' in answer:
                raise Exception('error: {}'.format(answer))
            sleep(5)
            answer = s.get(
                'http://2captcha.com/res.php?key={}&action=get&id={}'.format(
                    self.c['2cap_api_key'],
                    captcha_id)
            ).text
        token = answer.split('|')[1]
        self.log('got token {}'.format(token))
        return token

    def get_auth_token(self, source):
        # scrapes a fresh auth token from page source
        self.auth_token = re.findall('name="authenticity_token" value="(.*?)"', source)[2]
        self.log('got new auth token {}'.format(self.auth_token))
        return

    def get_total_cost(self, source):
        self.log('getting order total')
        self.total_cost = re.findall('data-checkout-payment-due-target="(.*?)"', source)[0]
        self.log('found order total {}'.format(self.total_cost))
        return

    def get_gateway_id(self, source):
        self.log('getting payment gateway id')
        self.gateway_id = re.findall('data-brand-icons-for-gateway="(.*?)"', source)[0]
        self.log('found payment gateway id {}'.format(self.gateway_id))
        return

    def get_shipping_info(self, checkout_url):
        if self.c['shipping_get_method'] == 'normal':
            self.log('gathering shipping info (normal method)')
            r = self.S.get(
                checkout_url,
                headers=self.headers
            )
            r.raise_for_status()
            self.ship_data = re.findall('data-backup="(.*?)"', r.text)[0]
        elif self.c['shipping_get_method'] == 'advanced':
            # JSON SHIPPING METHOD (USE FOR SITES THAT DONT HAVE PRODUCTS LOADED)
            self.log('gathering shipping info (advanced method)')
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
            raise Exception('malformed shipping get method in config \n'
                            'acceptable configurations: "normal" or "advanced"')
        self.log('found shipping method {}'.format(self.ship_data))
        return

    def get_products(self):
        # scrapes all products on the site
        # returns a list of product objects
        if self.c['product_scrape_method'] == 'atom':
            self.log('fetching product list (atom method)')
            r = self.S.get(
                self.c['site'] + '/collections/footwear.atom',
                headers=self.headers,
                allow_redirects=False
            )
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.log('atom method got http error, switching to xml method')
                self.c['product_scrape_method'] = 'xml'
                return self.get_products()
            product_urls = re.findall('<link rel="alternate" type="text/html" href="(.*?)"/>', r.text)
            product_urls.pop(0)  # Remove first link from list (map base link)
            product_titles = re.findall('<title>(.*?)</title>\s*<s:type', r.text)
            product_objects = []
            if len(product_urls) != len(product_titles):
                raise Exception('mismatched product indices')
            self.log('scraped {} products'.format(len(product_urls)))
            for i in range(0, len(product_urls)):
                # self.log('{}'.format(product_titles[i]))
                product_objects.append(Product(product_titles[i], product_urls[i]))
            return product_objects
        elif self.c['product_scrape_method'] == 'json':
            # TODO: complete json scrape method
            self.log('fetching product list (json method)')
            r = self.S.get(
                self.c['site'] + '/products.json',
                headers=self.headers,
                allow_redirects=False
            )
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.log('json method got http error, switching to xml method')
                self.c['product_scrape_method'] = 'xml'
                return self.get_products()
            r = r.json()
        elif self.c['product_scrape_method'] == 'xml':
            # TODO: complete xml scrape method
            self.log('fetching product list (xml method)')
            r = self.S.get(
                self.c['site'] + '/sitemap_products_1.xml',
                headers=self.headers,
                allow_redirects=False
            )
            r.raise_for_status()
            # TODO: simplify this regex expression
            expression = '<loc>(.*)</loc>\s.*</lastmod>\s.*\s.*\s.*\s.*\s.*\s.*<image:title>(.*)</image:title>'
            products = re.findall(expression, r.text)
            product_objects = []
            for prod in products:
                product_objects.append(Product(prod[1], prod[0]))
            return product_objects
        elif self.c['product_scrape_method'] == 'oembed':
            # TODO: complete oembed scrape method
            self.log('fetching product list (oembed method)')
            r = self.S.get(
                self.c['site'] + '/collections/all.oembed',
                headers=self.headers,
                allow_redirects=False
            )
            try:
                r.raise_for_status()
            except requests.exceptions.HTTPError:
                self.log('oembed method got http error, switching to xml method')
                self.c['product_scrape_method'] = 'xml'
                return self.get_products()
            r = r.json()
            product_objects = []
            if len(r['products']) < 1:
                # TODO: make this retry a different category if 'all' fails
                self.log('error no products found, trying xml method')
                self.c['product_scrape_method'] = 'xml'
                return self.get_products()
            for prod in r['products']:
                variant_objects = []
                for var in prod['offers']:
                    variant_objects.append(Variant(var['offer_id'], var['title'], stock=var['in_stock']))
                product_objects.append(Product(prod['title'], None, variants=variant_objects))
            return product_objects
        else:
            raise Exception('malformed product scrape method in config\n'
                            'acceptable configurations: "atom", "xml", "json", or "oembed"')

    def check_products(self, product_list):
        # compares a list of product objects against keywords
        # returns a single product object
        self.log('comparing product list against keywords')
        if len(product_list) < 1:
            raise Exception('cant check empty product list')
        for prod in product_list:
            match = True
            for key in self.c['product']['positive_kw'].lower().split(','):
                if key not in prod.name.lower():
                    match = False
            for key in self.c['product']['negative_kw'].lower().split(','):
                if key in prod.name.lower():
                    match = False
            if match:
                return prod
        return None

    def get_product_info(self, product):
        # oembed method already scrapes vars
        if self.c['product_scrape_method'] == 'oembed':
            return None
        # take a product and returns a list of variant objects
        self.log('getting product info')
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
        self.log('title: {} :: price: ${}'.format(r['product'][size_field], r['product']['variants'][0]['price']))
        for var in r['product']['variants']:
            self.log('{} :: {}'.format(var['id'], var[size_field]))
            variant_objects.append(Variant(var['id'], var[size_field]))
        self.slack_log(product, variant_objects)
        return variant_objects

    def check_variants(self, variant_list):
        # takes a list of variants and searches for a matching size
        self.log('comparing variants against configured size')
        selected_variant = None
        for var in variant_list:
            if self.c['product']['size'] == var.size:
                self.log('found matching variant - {}'.format(var.id))
                selected_variant = var
        while selected_variant is None:
            # if a match isnt found, have the user select the size manually
            self.log('couldnt match variant against selected size, please pick numerically\n')
            i = 0
            for v in variant_list:
                print '#{} - SIZE {}'.format(str(i).zfill(2), v.size)
                i += 1
            x = raw_input('please enter a product index #\n> ')
            try:
                if 0 <= int(x) < len(variant_list):
                    selected_variant = variant_list[int(x)]
                else:
                    self.log('error selection {} not in range'.format(x))
            except ValueError:
                self.log('error please enter a number')
        return selected_variant

    def add_to_cart(self, variant):
        # adds a selected variant object to cart and returns the new checkout url
        self.log('adding variant to cart', slack=True)
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
        self.log('getting checkout page')
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
        self.log('removing {} item from position {}'.format(quantity, position))
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
        self.log('current cart quantity: {}'.format(r['item_count']))
        return

    def open_checkout(self, checkout_url):
        # opens the checkout url to scrape auth token and check for sold out
        self.log('opening checkout page {}'.format(checkout_url), slack=True)
        r = self.S.get(
            checkout_url,
            headers=self.headers
        )
        r.raise_for_status()
        self.queue(r.url)
        self.sold_out(r.url)
        if self.is_captcha(r.text):
            self.captcha_task = True
            self.sitekey = self.get_sitekey(r.text)
            # self.cap_response = self.get_captcha_token(self.sitekey, checkout_url)
        self.get_auth_token(r.text)
        return r.url

    def submit_customer_info(self, checkout_url):
        # submits customer information then returns the latest checkout url
        self.log('submitting customer info', slack=True)
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
        # NOTE: Moved this to the final step, to support bypass method. Should still be effective.
        # if self.cap_response is not None:
        #     # adds captcha response to payload if we have one
        #     payload['g-recaptcha-response'] = self.cap_response
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()
        self.sold_out(r.url)
        self.get_auth_token(r.text)
        self.get_shipping_info(r.url)
        return r.url

    def submit_shipping_info(self, checkout_url):
        self.log('submitting shipping info', slack=True)
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
        self.sold_out(r.url)
        self.get_auth_token(r.text)
        self.get_total_cost(r.text)
        self.get_gateway_id(r.text)
        return r.url

    def submit_payment_info(self):
        self.log('submitting cc information')
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
            'credit_card': {
                'number': self.c['checkout']['cc'],
                'name': self.c['checkout']['fname'] + ' ' + self.c['checkout']['lname'],
                'month': self.c['checkout']['exp_m'],
                'year': self.c['checkout']['exp_y'],
                'verification_value': self.c['checkout']['cvv']
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
            self.log('getting payment id')
            return r.json()['id']
        except KeyError:
            raise Exception('key error finding payment id')

    def submit_order(self, checkout_url, payment_id):
        self.log('submitting order with payment id {}'.format(payment_id))
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
        if self.cap_response is not None:
            # adds captcha response to payload if we have one
            payload['g-recaptcha-response'] = self.cap_response
        r = self.S.post(
            checkout_url,
            headers=self.form_headers,
            data=payload
        )
        r.raise_for_status()
        return True

    def run(self):
        if self.c['checkout_mode'] == '2cap':
            self.log('selected 2captcha checkout mode (no bypass)', slack=True)
            while True:
                product_list = self.get_products()
                product_match = self.check_products(product_list)
                if product_match is not None:
                    self.log('found matching product - {}'.format(product_match.url), slack=True)
                    break
                self.refresh_poll()
            product_variants = self.get_product_info(product_match)
            selected_variant = self.check_variants(product_variants)
            try:
                checkout_url = self.add_to_cart(selected_variant)
                checkout_url = self.open_checkout(checkout_url)
                checkout_url = self.submit_customer_info(checkout_url)
                checkout_url = self.submit_shipping_info(checkout_url)
                payment_id = self.submit_payment_info()
                if self.submit_order(checkout_url, payment_id):
                    self.log('order submitted successfully. check email {}'.format(self.c['checkout']['email']), slack=True)
                    self.log('time to return {} sec'.format(abs(self.start_time - time())), slack=True)
            except requests.exceptions.MissingSchema:
                raise Exception('error: a request was passed a null url')
        elif self.c['checkout_mode'] == 'dummy_bypass':
            self.log('selected dummy bypass mode', slack=True)
            self.log('adding dummy product to cart', slack=True)
            # add and start dummy product checkout
            try:
                checkout_url = self.add_to_cart(Variant(self.c['dummy_variant'], None))
                checkout_url = self.open_checkout(checkout_url)
                checkout_url = self.submit_customer_info(checkout_url)
            except requests.exceptions.MissingSchema:
                raise Exception('error: a request was passed a null url', slack=True)
            # wait for timer
            self.log('waiting for drop time {}...'.format(self.c['drop_timer']), slack=True)
            while True:
                if self.captcha_task:
                    if datetime.datetime.now().strftime('%H:%M:%S') >= self.c['cap_harvest_time']:
                        self.log('starting captcha harvest', slack=True)
                        # TODO: start a captcha thread(s) here
                        self.cap_response = self.get_captcha_token(self.sitekey, checkout_url)
                        self.log('got captcha response, waiting for drop time', slack=True)
                if datetime.datetime.now().strftime('%H:%M:%S') >= self.c['drop_timer']:
                    self.log('drop timer passed. continuing with checkout', slack=True)
                    break
                sleep(1)
            # find the actual product
            while True:
                product_list = self.get_products()
                product_match = self.check_products(product_list)
                if product_match is not None:
                    self.log('found matching product - {}'.format(product_match.url), slack=True)
                    break
                self.refresh_poll()
            product_variants = self.get_product_info(product_match)
            selected_variant = self.check_variants(product_variants)
            self.add_to_cart(selected_variant)  # dont use the new checkout url
            # remove dummy product from cart
            self.remove_from_cart(0, 2)
            # refresh the checkout page
            params = {
                'previous_step': 'shipping_method',
                'step': 'payment_method'
            }
            r = self.S.get(
                checkout_url,
                params=params,
                headers=self.headers
            )
            r.raise_for_status()
            # finish checkout
            checkout_url = self.submit_shipping_info(checkout_url)
            payment_id = self.submit_payment_info()
            if self.submit_order(checkout_url, payment_id):
                self.log('order submitted successfully. check email {}'.format(self.c['checkout']['email']), slack=True)
                self.log('time to return {} sec'.format(abs(self.start_time - time())), slack=True)
        else:
            raise Exception('malformed checkout mode in config\n'
                            'acceptable configurations: "2cap" or "dummy_bypass"')
