# Shopify

Shopify ATC. Full checkout with captcha/queue bypass. Built by Alex++.

If you like what I've done or if this helps you cop, throw me a shout out on Twitter: [@edzart](https://twitter.com/edzart)

# Requirements

* Python 2.7
* Requests
* Selenium (includes chromedriver 2.31 in ```bin``` folder)

# Config

See config.example.json for more help. Most stuff should be pretty self explanatory. 

```checkout_mode``` set to '2cap' or 'dummy_bypass'

```shipping_get_method``` set to 'normal' or 'advanced'

```product_scrape_method``` set to 'atom', 'json', 'xml', or 'oembed'

```drop_timer``` is H:M:S. Currently only used for dummy bypass method

```size_field``` is the variant size field in product json. Probably 'title'

# Usage

After editing ```config.example.json``` and renaming to something else:
```
$ pip install -r requirements.txt

$ python main.py
```

# Known Issues

* Bypass method doesnt work w/ captcha. Captcha must be solved after the latest cart update time.
* 2Cap solving is slow

# Roadmap

*[X] OEMBED scraping method
*[ ] Implement anticaptcha solving
*[ ] Implement threaded captcha solving for 3rd party services
*[ ] Implement scraping dictionaries to account for variant nomenclature changes (e.g. Haven)