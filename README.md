# Shopify
Shopify ATC. Full checkout with captcha/queue bypass. Built by Alex++.

# Requirements

* Python 2.7
* Requests

# Config

See config.example.json for more help. Most stuff should be pretty self explanatory. 

```checkout_mode``` set to '2cap' or 'dummy_bypass'

```shipping_get_method``` set to 'normal' or 'advanced'

```product_scrape_method``` set to 'atom', 'json', 'xml', or 'oembed'

```drop_timer``` is H:M:S. Currently only used for dummy bypass method

```size_field``` is the variant size field in product json. Probably 'title'

# Usage

```buildoutcfg
pip install -r requirements.txt

python main.py
```