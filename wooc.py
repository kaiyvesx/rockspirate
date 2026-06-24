import os
import sys
import json
import urllib3
import requests
import re
import socket
import argparse
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Disable SSL verification warnings to keep console output clean
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Reconfigure stdout and stderr to UTF-8 to avoid encoding errors on Windows console
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except AttributeError:
    pass

# --- TERMINAL COLORS ---
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'

# Conditionally enable ANSI support on Windows Command Prompt
if sys.platform == 'win32':
    os.system('')

# --- DYNAMIC SIGNATURES LOADER ---
SIGNATURES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signatures.json')

def load_signatures():
    """
    Loads payment gateway signatures from the signatures.json file.
    Creates a signatures.json with defaults if the file does not exist.
    """
    if not os.path.exists(SIGNATURES_FILE):
        default_signatures = {
            "stripe": {
                "name": "Stripe",
                "slug": "stripe",
                "patterns": [
                    "stripe.js", "js.stripe.com/v3", "stripe-payment-request", "wc-stripe", 
                    "stripe_checkout", "woocommerce-gateway-stripe", "stripe_payment_form",
                    "stripe-card-element"
                ]
            },
            "ppcp": {
                "name": "PayPal Commerce Platform",
                "slug": "ppcp",
                "patterns": [
                    "woocommerce-paypal-payments", "paypal.com/sdk/js", "ppcp-gateways",
                    "wc-paypal", "paypal_commerce_platform", "paypal_connect", "paypal-smart-buttons",
                    "wcPPCPSettings", "pymntpl-paypal-woocommerce"
                ]
            },
            "paypal": {
                "name": "PayPal Standard/Express",
                "slug": "paypal",
                "patterns": [
                    "paypal-for-woocommerce", "woocommerce-gateway-paypal-express",
                    "paypal_express", "paypal_checkout", "paypal_standard", "www.paypalobjects.com"
                ]
            },
            "authnet": {
                "name": "Authorize.Net",
                "slug": "authnet",
                "patterns": [
                    "woocommerce-gateway-authorizenet", "Accept.js", "AcceptCore.js",
                    "wc-authorize-net", "authorizenet_acceptjs", "authorizenet-aim"
                ]
            },
            "square": {
                "name": "Square",
                "slug": "square",
                "patterns": [
                    "woocommerce-gateway-square", "squareup.com/v2/paymentform",
                    "square-payment-form", "wc-square", "square_credit_card"
                ]
            },
            "braintree": {
                "name": "Braintree",
                "slug": "braintree",
                "patterns": [
                    "woocommerce-gateway-braintree", "js.braintreegateway.com",
                    "wc-braintree", "braintree-payment-gateway", "braintree-dropin"
                ]
            },
            "adyen": {
                "name": "Adyen",
                "slug": "adyen",
                "patterns": [
                    "adyen-woocommerce", "adyen.com", "wc-adyen", "adyen-checkout"
                ]
            },
            "klarna": {
                "name": "Klarna",
                "slug": "klarna",
                "patterns": [
                    "klarna-checkout-for-woocommerce", "klarna-payments-for-woocommerce",
                    "klarna-sdk", "klarna_payments", "klarnapayments"
                ]
            },
            "mollie": {
                "name": "Mollie",
                "slug": "mollie",
                "patterns": [
                    "mollie-payments-for-woocommerce", "mollie.com", "mollie-wc"
                ]
            },
            "razorpay": {
                "name": "Razorpay",
                "slug": "razorpay",
                "patterns": [
                    "razorpay-payments-for-woocommerce", "checkout.razorpay.com",
                    "razorpay-wc", "razorpay.js"
                ]
            },
            "paystack": {
                "name": "Paystack",
                "slug": "paystack",
                "patterns": [
                    "wc-paystack", "paystack-woocommerce", "paystack.co", "paystack.js"
                ]
            },
            "wcpay": {
                "name": "WooCommerce Payments",
                "slug": "wcpay",
                "patterns": [
                    "woocommerce-payments", "wcpay-", "wc-payments", "public.jetpack.com"
                ]
            },
            "payflow": {
                "name": "PayPal Payflow",
                "slug": "payflow",
                "patterns": [
                    "woocommerce-gateway-paypal-pro", "payflow-pro", "paypal-pro-classic"
                ]
            },
            "affirm": {
                "name": "Affirm",
                "slug": "affirm",
                "patterns": [
                    "woocommerce-gateway-affirm", "affirm.com/js", "affirmInlineCheckout", "affirm-checkout"
                ]
            },
            "bacs": {
                "name": "Direct Bank Transfer",
                "slug": "bacs",
                "patterns": []
            },
            "cheque": {
                "name": "Check Payments",
                "slug": "cheque",
                "patterns": []
            },
            "cod": {
                "name": "Cash on Delivery",
                "slug": "cod",
                "patterns": []
            }
        }
        try:
            with open(SIGNATURES_FILE, 'w') as f:
                json.dump(default_signatures, f, indent=4)
        except Exception as e:
            print(f"Error creating signatures.json: {e}")
            return default_signatures

    try:
        with open(SIGNATURES_FILE, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading signatures.json: {e}")
        return {}

# --- HELPER PRINT FUNCTION ---
def print_step(step_num, text, status="pending"):
    """
    Prints styled pipeline step progress.
    Uses ANSI clear-line escape to fully overwrite any previous pending text.
    """
    if status == "success":
        print(f"\033[2K\r  [{Colors.GREEN}✓{Colors.ENDC}] Step {step_num}: {text}")
    elif status == "fail":
        print(f"\033[2K\r  [{Colors.FAIL}✗{Colors.ENDC}] Step {step_num}: {text}")
    else:
        print(f"  [{Colors.CYAN}•{Colors.ENDC}] Step {step_num}: {text}...", end="", flush=True)

def print_error_banner(error_type, details=""):
    """
    Prints a styled error banner for critical scan failures.
    error_type: one of "MISSING PRODUCT ID", "ADD TO CART ERROR", "PAYMENT METHOD FAILED TO CAPTURE"
    details: optional extra context string appended below the banner
    """
    print(f"\n  {Colors.FAIL}{Colors.BOLD}┌─────────────────────────────────────────────────────────────────────────┐{Colors.ENDC}")
    print(f"  {Colors.FAIL}{Colors.BOLD}│{Colors.ENDC}  {Colors.FAIL}{Colors.BOLD}⚠  {error_type}{Colors.ENDC}")
    print(f"  {Colors.FAIL}{Colors.BOLD}└─────────────────────────────────────────────────────────────────────────┘{Colors.ENDC}")
    if details:
        print(f"    {Colors.WARNING}→ {details}{Colors.ENDC}")
    print()

# --- RESILIENT HTTP SESSION (curl_cffi fallback for TLS fingerprinting) ---
# Some servers / WAFs reject the standard Python `requests` TLS fingerprint with
# errors like "tlsv1 alert internal error". `curl_cffi` can impersonate a real
# Chrome browser's TLS handshake, which bypasses most of these blocks. We wrap
# a normal requests.Session and transparently fall back to curl_cffi on failure.

try:
    from curl_cffi import requests as _cffi_requests  # type: ignore
    _HAS_CURL_CFFI = True
except Exception:
    _HAS_CURL_CFFI = False


class ResilientSession:
    """
    A drop-in replacement for requests.Session that falls back to curl_cffi
    (Chrome impersonation) whenever the standard requests call raises a TLS /
    SSL / connection error. Exposes the same .get() signature callers already use.
    """

    def __init__(self):
        self._session = requests.Session()
        # curl_cffi keeps its own session so cookies persist across fallbacks
        self._cffi = _cffi_requests.Session(impersonate="chrome") if _HAS_CURL_CFFI else None
        self.headers = self._session.headers

    def _looks_like_tls_error(self, err):
        """Heuristic: should we retry this exception via curl_cffi?"""
        msg = str(err).lower()
        tls_markers = [
            'ssl', 'tls', 'tlsv1', 'handshake', 'sslv3', 'connection aborted',
            'max retries exceeded', 'wrong version number', 'certificate',
        ]
        return any(m in msg for m in tls_markers)

    def get(self, url, **kwargs):
        # Standard path first
        try:
            return self._session.get(url, **kwargs)
        except Exception as err:
            if not self._cffi or not self._looks_like_tls_error(err):
                raise
            # Fall back to Chrome-impersonated TLS
            # curl_cffi does not accept every kwarg requests does, so we filter.
            allowed = {}
            for k in ('headers', 'timeout', 'verify', 'allow_redirects', 'params', 'cookies'):
                if k in kwargs:
                    allowed[k] = kwargs[k]
            try:
                return self._cffi.get(url, **allowed)
            except Exception:
                # If curl_cffi also fails, surface the original error
                raise err

    def post(self, url, **kwargs):
        try:
            return self._session.post(url, **kwargs)
        except Exception as err:
            if not self._cffi or not self._looks_like_tls_error(err):
                raise
            allowed = {}
            for k in ('headers', 'timeout', 'verify', 'allow_redirects', 'params', 'cookies', 'data', 'json'):
                if k in kwargs:
                    allowed[k] = kwargs[k]
            try:
                return self._cffi.post(url, **allowed)
            except Exception:
                raise err

    def close(self):
        try:
            self._session.close()
        except Exception:
            pass
        if self._cffi:
            try:
                self._cffi.close()
            except Exception:
                pass


# --- SCANNER CORE LOGIC ---
def detect_country(domain, soup):
    """
    Detects the country code of the website by looking at checkout form fields
    and falling back to free IP geolocation.
    """
    # 1. Try to get default country from billing_country select in checkout HTML
    try:
        select = soup.find('select', attrs={'name': 'billing_country'})
        if select:
            selected = select.find('option', selected=True)
            if selected and selected.get('value'):
                return selected.get('value').upper()
            # Check all options for selected attribute
            for opt in select.find_all('option'):
                if opt.has_attr('selected') and opt.get('value'):
                    return opt.get('value').upper()
    except Exception:
        pass

    # 2. Fallback: IP Geo lookup
    try:
        ip = socket.gethostbyname(domain)
        r = requests.get(f"http://ip-api.com/json/{ip}", timeout=5)
        if r.status_code == 200:
            res = r.json()
            if res.get('status') == 'success' and res.get('countryCode'):
                return res.get('countryCode').upper()
    except Exception:
        pass

    return "US"

def detect_cloudflare(response, html_text):
    """
    Checks if Cloudflare is active on the server response.
    """
    cf_headers = ['cf-ray', 'cf-cache-status', 'cf-request-id', 'cf-bgj', 'cf-polished', 'cf-visitor']
    for h in cf_headers:
        if h in response.headers:
            return "YES"
            
    server = response.headers.get('server', '').lower()
    if 'cloudflare' in server:
        return "YES"
        
    if '/cdn-cgi/' in html_text or 'cloudflare-static' in html_text:
        return "YES"
        
    return "NO"

def detect_captcha(html_text):
    """
    Detects Captcha indicators (reCAPTCHA, hCaptcha, Turnstile).
    """
    captcha_keywords = ['recaptcha', 'hcaptcha', 'turnstile', 'g-recaptcha', 'cf-turnstile', 'h-captcha']
    html_lower = html_text.lower()
    for kw in captcha_keywords:
        if kw in html_lower:
            return "YES"
            
    if re.search(r'\bcaptcha\b', html_lower):
        return "YES"
        
    return "NO"

def detect_woocommerce(soup, html_text):
    """
    Analyzes BeautifulSoup parsed content to detect WooCommerce installation.
    Returns (detected: bool, confidence_score: str, reasons: list)
    """
    reasons = []
    
    # 1. Check Generator Tag
    gen_tag = soup.find('meta', attrs={'name': 'generator'})
    if gen_tag and 'woocommerce' in gen_tag.get('content', '').lower():
        reasons.append(f"Generator Meta: {gen_tag.get('content')}")
        
    # 2. Check Plugins Path in links/scripts
    if '/wp-content/plugins/woocommerce/' in html_text:
        reasons.append("Asset path contains '/wp-content/plugins/woocommerce/'")
        
    # 3. Check for standard woocommerce class names in body tag
    body = soup.find('body')
    if body:
        classes = body.get('class', [])
        wc_classes = [c for c in classes if 'woocommerce' in c]
        if wc_classes:
            reasons.append(f"Body Class matches: {', '.join(wc_classes)}")

    # 4. Check for WooCommerce Global JavaScript Parameters
    wc_js_params = ['wc_add_to_cart_params', 'woocommerce_params', 'wc_cart_fragments_params']
    for param in wc_js_params:
        if param in html_text:
            reasons.append(f"Global JS parameter detected: {param}")
            
    # 5. Check for standard Ajax Endpoints
    if 'wc-ajax' in html_text or '/?wc-ajax=' in html_text:
        reasons.append("WooCommerce Ajax endpoint 'wc-ajax' found in page contents")

    if len(reasons) >= 2:
        return True, "High", reasons
    elif len(reasons) == 1:
        return True, "Medium", reasons
    
    # Fallback to WooCommerce asset links
    if 'woocommerce-layout.css' in html_text or 'woocommerce.css' in html_text:
        reasons.append("WooCommerce CSS stylesheet layout loaded")
        return True, "Medium", reasons
        
    return False, "Low", []

def scan_for_gateways(html_text):
    """
    Scans a given text (HTML source) for payment gateway signatures.
    Returns a set of slugs.
    """
    detected = set()
    signatures = load_signatures()
    for slug, info in signatures.items():
        for pattern in info.get("patterns", []):
            if pattern.lower() in html_text.lower():
                detected.add(slug)
                break
    return detected

def find_product_id(soup, html_text):
    """
    Finds a WooCommerce product ID from elements or links in the page html.
    """
    # 1. Search for any link containing ?add-to-cart=ID or &add-to-cart=ID
    match = re.search(r'href=["\'](?:[^"\']*\?|^\?)add-to-cart=(\d+)', html_text)
    if match:
        return match.group(1)
        
    # 2. Search in submit inputs/buttons (product single page forms)
    add_to_cart_input = soup.find(attrs={"name": "add-to-cart"})
    if add_to_cart_input:
        val = add_to_cart_input.get('value')
        if val and val.isdigit():
            return val
            
    # 3. Look for buttons with data-product_id attribute
    add_to_cart_btn = soup.find(attrs={"data-product_id": True})
    if add_to_cart_btn:
        val = add_to_cart_btn.get('data-product_id')
        if val and val.isdigit():
            return val
            
    return None

def find_product_link(soup, base_url):
    """
    Searches for product page links (e.g. URLs containing '/product/') to fetch details.
    """
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/product/' in href:
            return urljoin(base_url, href)
            
    loop_link = soup.find('a', class_='woocommerce-LoopProduct-link')
    if loop_link and loop_link.get('href'):
        return urljoin(base_url, loop_link.get('href'))
        
    return None

def attempt_find_product_id_across_pages(session, base_url, headers):
    """
    Checks the Homepage, product links, and shop page to extract a valid product ID.
    """
    # 1. Check Homepage content
    try:
        r = session.get(base_url, headers=headers, timeout=10, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            prod_id = find_product_id(soup, r.text)
            if prod_id:
                return prod_id, "Found on Homepage"
                
            # Try product detail link
            prod_link = find_product_link(soup, base_url)
            if prod_link:
                rp = session.get(prod_link, headers=headers, timeout=10, verify=False)
                if rp.status_code == 200:
                    soup_p = BeautifulSoup(rp.text, 'html.parser')
                    prod_id_p = find_product_id(soup_p, rp.text)
                    if prod_id_p:
                        return prod_id_p, f"Found on Product Link ({prod_link})"
    except Exception:
        pass

    # 2. Check Shop Page
    shop_url = base_url.rstrip('/') + '/shop/'
    try:
        r = session.get(shop_url, headers=headers, timeout=10, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            prod_id = find_product_id(soup, r.text)
            if prod_id:
                return prod_id, "Found on Shop Page"
                
            # Try product link on Shop Page
            prod_link = find_product_link(soup, base_url)
            if prod_link:
                rp = session.get(prod_link, headers=headers, timeout=10, verify=False)
                if rp.status_code == 200:
                    soup_p = BeautifulSoup(rp.text, 'html.parser')
                    prod_id_p = find_product_id(soup_p, rp.text)
                    if prod_id_p:
                        return prod_id_p, f"Found on Shop-Product Page ({prod_link})"
    except Exception:
        pass
        
    return None, None

def add_product_to_cart(session, base_url, prod_id, headers):
    """
    Sends a query request to add the product to the active cookies session.
    """
    add_url = base_url.rstrip('/') + f"/?add-to-cart={prod_id}"
    try:
        session.get(add_url, headers=headers, timeout=10, verify=False)
        return True, f"Successfully executed add-to-cart query for ID {prod_id}"
    except Exception as e:
        return False, f"Failed to execute add-to-cart: {str(e)}"

def perform_website_scan(target_url, quiet=False):
    """
    Runs the full web-scanning pipeline on target_url.
    Prints status step-by-step unless quiet is True.
    """
    if not quiet:
        print_step(1, "Validating Website URL & Normalizing Format", "pending")
    
    # Ensure proper schema
    if not target_url.startswith(('http://', 'https://')):
        target_url = 'https://' + target_url

    if not quiet:
        print_step(1, f"URL validated and normalized: {target_url}", "success")

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    script_gateways = set()
    input_gateways = set()
    is_wooc = False
    confidence = "Low"
    reasons = []
    
    # Pre-parse domain for initial country geolocation
    parsed_url = urlparse(target_url)
    domain_name = parsed_url.netloc or target_url.split('/')[0]
    country = detect_country(domain_name, None)
    cloudflare = "NO"
    captcha = "NO"

    # Persistent Session for Cookies (like Cart / User Session)
    # Uses ResilientSession which falls back to curl_cffi (Chrome TLS impersonation)
    # when standard requests fails on TLS handshake errors.
    session = ResilientSession()

    # Track whether checkout was successfully scanned (required for accurate gateway detection)
    checkout_scanned = False

    # Step 1: Scan Homepage
    if not quiet:
        print_step(2, "Accessing Homepage & Detecting WooCommerce Signatures", "pending")
    
    try:
        # Disable requests' built-in redirect following so we can detect loops ourselves
        r = session.get(target_url, headers=headers, timeout=12, verify=False, allow_redirects=False)
        visited = set()
        max_redirects = 10

        # Manually follow redirects with loop detection
        for _ in range(max_redirects):
            if 300 <= r.status_code < 400 and 'Location' in r.headers:
                location = r.headers['Location']
                next_url = urljoin(r.url, location)

                # Strip trailing slash variation for loop detection
                normalized = urlparse(next_url)
                redirect_key = f"{normalized.scheme}://{normalized.netloc}{normalized.path}"
                if redirect_key in visited:
                    # Redirect loop detected — try final URL once more to grab any landing page
                    r = session.get(next_url, headers=headers, timeout=12, verify=False, allow_redirects=False)
                    break
                visited.add(redirect_key)

                r = session.get(next_url, headers=headers, timeout=12, verify=False, allow_redirects=False)
            else:
                break

        if 300 <= r.status_code < 400:
            # Still redirecting after maxRedirects — site has an infinite loop
            raise requests.TooManyRedirects(f"Infinite redirect loop detected after {max_redirects} hops")

        r.raise_for_status()
        homepage_html = r.text
        homepage_url = r.url
        soup_home = BeautifulSoup(homepage_html, 'html.parser')
        
        # Detect platform from homepage
        is_wooc_home, confidence_home, reasons_home = detect_woocommerce(soup_home, homepage_html)
        if is_wooc_home:
            is_wooc = True
            confidence = confidence_home
            reasons.extend(reasons_home)
            
        # Extract homepage gateways
        script_gateways.update(scan_for_gateways(homepage_html))
        
        # Check cloudflare and captcha on homepage as initial values
        cloudflare = detect_cloudflare(r, homepage_html)
        captcha = detect_captcha(homepage_html)
        
        if not quiet:
            print_step(2, f"Homepage scanned (WooCommerce: {'Yes' if is_wooc_home else 'No'}, Gateways: {len(script_gateways)})", "success")
            
    except requests.TooManyRedirects:
        # Infinite redirect loop on https — try http as fallback
        if target_url.startswith('https://'):
            fallback_url = target_url.replace('https://', 'http://', 1)
            try:
                if not quiet:
                    print_step(2, "HTTPS redirect loop detected, retrying with HTTP...", "pending")
                r = session.get(fallback_url, headers=headers, timeout=12, verify=False)
                r.raise_for_status()
                homepage_html = r.text
                homepage_url = r.url
                soup_home = BeautifulSoup(homepage_html, 'html.parser')

                is_wooc_home, confidence_home, reasons_home = detect_woocommerce(soup_home, homepage_html)
                if is_wooc_home:
                    is_wooc = True
                    confidence = confidence_home
                    reasons.extend(reasons_home)
                script_gateways.update(scan_for_gateways(homepage_html))
                
                # Check cloudflare and captcha on HTTP fallback homepage
                cloudflare = detect_cloudflare(r, homepage_html)
                captcha = detect_captcha(homepage_html)

                if not quiet:
                    print_step(2, f"Homepage scanned via HTTP fallback (WooCommerce: {'Yes' if is_wooc_home else 'No'}, Gateways: {len(script_gateways)})", "success")
            except Exception:
                if not quiet:
                    print(f"\033[2K\r", end="")
                    print_step(2, "Infinite redirect loop on both HTTPS and HTTP", "fail")
                    print_error_banner("PRODUCT PAGE ERROR",
                        f"This site ({target_url}) has an infinite redirect loop and could not be reached. "
                        "The server may be misconfigured, behind a broken proxy, or blocking automated requests.")
                return {
                    "status": "error",
                    "url": target_url,
                    "error": f"Infinite redirect loop — site unreachable at {target_url}"
                }
        else:
            if not quiet:
                print_error_banner("PRODUCT PAGE ERROR",
                    f"This site ({target_url}) has an infinite redirect loop and could not be reached. "
                    "The server may be misconfigured, behind a broken proxy, or blocking automated requests.")
            return {
                "status": "error",
                "url": target_url,
                "error": f"Infinite redirect loop — site unreachable at {target_url}"
            }
    except requests.exceptions.HTTPError as e:
        if not quiet:
            print(f"\033[2K\r", end="")
            print_step(2, f"Homepage returned HTTP {e.response.status_code}", "fail")
            print_error_banner("PRODUCT PAGE ERROR",
                f"The homepage responded with HTTP {e.response.status_code}. "
                "The site may be temporarily down, in maintenance mode, or blocking automated requests.")
        return {
            "status": "error",
            "url": target_url,
            "error": f"HTTP {e.response.status_code} from Homepage"
        }
    except Exception as e:
        # If this is a TLS/SSL handshake error, try falling back to HTTP before giving up.
        # Some servers have a broken HTTPS endpoint but a working HTTP endpoint (e.g. inkprint.com.au).
        err_msg = str(e).lower()
        is_tls_error = any(m in err_msg for m in ('ssl', 'tls', 'handshake'))
        used_http_fallback = False

        if is_tls_error and target_url.startswith('https://'):
            fallback_url = target_url.replace('https://', 'http://', 1)
            try:
                if not quiet:
                    print(f"\033[2K\r", end="")
                    print_step(2, "TLS handshake failed on HTTPS, retrying with HTTP...", "pending")
                r = session.get(fallback_url, headers=headers, timeout=12, verify=False)
                r.raise_for_status()
                homepage_html = r.text
                homepage_url = r.url
                soup_home = BeautifulSoup(homepage_html, 'html.parser')

                is_wooc_home, confidence_home, reasons_home = detect_woocommerce(soup_home, homepage_html)
                if is_wooc_home:
                    is_wooc = True
                    confidence = confidence_home
                    reasons.extend(reasons_home)
                script_gateways.update(scan_for_gateways(homepage_html))

                cloudflare = detect_cloudflare(r, homepage_html)
                captcha = detect_captcha(homepage_html)
                used_http_fallback = True

                if not quiet:
                    print_step(2, f"Homepage scanned via HTTP fallback after TLS error (WooCommerce: {'Yes' if is_wooc_home else 'No'}, Gateways: {len(script_gateways)})", "success")
            except Exception:
                used_http_fallback = False

        if not used_http_fallback:
            if not quiet:
                print(f"\033[2K\r", end="")
                print_step(2, f"Connection to Homepage failed: {str(e)}", "fail")
                print_error_banner("PRODUCT PAGE ERROR",
                    f"Could not connect to {target_url}: {str(e)}. "
                    "The site may be offline, DNS may be failing, or the connection was refused.")
            return {
                "status": "error",
                "url": target_url,
                "error": f"Failed to connect to Homepage: {str(e)}"
            }

    # Get the root domain URL to ensure /checkout/ is resolved correctly
    parsed = urlparse(homepage_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    # Step 2: Product Finding & Add-to-Cart logic
    if not quiet:
        print_step(3, "Searching for WooCommerce Store Products to add to Cart", "pending")

    # If the user supplied a product URL directly, use that product instead of guessing from the homepage
    product_id = None
    method = None
    target_parsed = urlparse(target_url)
    if '/product/' in target_parsed.path:
        try:
            pr = session.get(target_url, headers=headers, timeout=12, verify=False)
            if pr.status_code == 200:
                soup_target = BeautifulSoup(pr.text, 'html.parser')
                product_id = find_product_id(soup_target, pr.text)
                if product_id:
                    method = f"Found on Target Product URL ({target_url})"
        except Exception:
            pass

    # Fallback: scan homepage/shop if no product ID yet
    if not product_id:
        product_id, method = attempt_find_product_id_across_pages(session, base_url, headers)
    
    if product_id:
        reasons.append(f"WooCommerce Product Detected: ID {product_id} ({method})")
        if not quiet:
            print_step(3, f"Product found! ID {product_id} ({method})", "success")
            print_step(4, "Adding Product to Cart Session & Requesting Checkout", "pending")
            
        success, cart_msg = add_product_to_cart(session, base_url, product_id, headers)
        reasons.append(cart_msg)
        
        if not quiet:
            if success:
                print_step(4, "Product successfully loaded into shopping cart", "success")
            else:
                print_step(4, f"Failed to add product: {cart_msg}", "fail")
                print_error_banner("ADD TO CART ERROR",
                    f"The add-to-cart request for product ID {product_id} did not complete successfully. "
                    "The server may have blocked the request, the product may be disabled, or a connection error occurred. "
                    "Checkout gateways that require an active cart may not be fully detected.")
    else:
        reasons.append("No active store products found to populate the shopping cart session")
        if not quiet:
            print_step(3, "No product found (skipping cart simulation)", "fail")
            print_error_banner("MISSING PRODUCT ID",
                "Could not locate a valid WooCommerce product ID on the Homepage, product pages, or Shop page. "
                "The checkout scan will proceed with an empty cart — some payment gateways may not render without an active cart session.")
            print_step(4, "Cart simulation bypassed (empty cart checkout model)", "success")

    # Step 3: Scan Checkout Page (using the session cookie with populated cart)
    if not quiet:
        print_step(5, "Analyzing Checkout Scripts & Compiling Gateway Slugs", "pending")
        
    checkout_url = base_url.rstrip('/') + '/checkout/'
    try:
        r = session.get(checkout_url, headers=headers, timeout=12, verify=False)
        if r.status_code == 200:
            checkout_html = r.text
            soup_checkout = BeautifulSoup(checkout_html, 'html.parser')
            checkout_scanned = True
            
            # Update cloudflare, captcha and country based on checkout data
            cloudflare = detect_cloudflare(r, checkout_html)
            captcha = detect_captcha(checkout_html)
            country = detect_country(domain_name, soup_checkout)
            
            # Recheck WooCommerce indicators on the Checkout page
            is_wooc_check, confidence_check, reasons_check = detect_woocommerce(soup_checkout, checkout_html)
            if is_wooc_check:
                is_wooc = True
                confidence = confidence_check
                reasons.extend(reasons_check)
                
            # Scan Checkout page scripts/inputs
            checkout_gateways = scan_for_gateways(checkout_html)
            script_gateways.update(checkout_gateways)
            
            # Map input elements directly (100% accurate fallback for rendered payment options)
            inputs = soup_checkout.find_all('input', attrs={'name': 'payment_method'})
            input_slugs = []
            for ip in inputs:
                val = ip.get('value')
                if val:
                    slug_lower = val.lower()
                    input_gateways.add(slug_lower)
                    input_slugs.append(slug_lower)
            if input_slugs:
                reasons.append(f"Payment options rendered in HTML form: {', '.join(input_slugs)}")

            if checkout_gateways:
                reasons.append(f"Payment scripts loaded at checkout: {', '.join(checkout_gateways)}")
                
            if not quiet:
                print_step(5, f"Checkout analyzed (Found {len(checkout_gateways)} scripts, {len(input_slugs)} active form gateways)", "success")
        else:
            reasons.append(f"Checkout page responded with HTTP code: {r.status_code}")
            if not quiet:
                print_step(5, f"Checkout responded with HTTP code: {r.status_code}", "fail")
                if r.status_code == 429:
                    print_error_banner("PAYMENT METHOD FAILED TO CAPTURE",
                        "The checkout page returned HTTP 429 (Too Many Requests). The server rate-limited "
                        "this scan before the checkout could be analyzed. Gateway results from homepage/shop "
                        "pages alone are unreliable — payment methods may be disabled or restricted to checkout context only.")
                else:
                    print_error_banner("PAYMENT METHOD FAILED TO CAPTURE",
                        f"The checkout page returned HTTP {r.status_code} and could not be analyzed. Gateway "
                        "results from homepage/shop pages alone may be incomplete or inaccurate.")
    except Exception as e:
        reasons.append(f"Failed to scan Checkout endpoint: {str(e)}")
        if not quiet:
            print_step(5, f"Checkout connection failed: {str(e)}", "fail")
            print_error_banner("PAYMENT METHOD FAILED TO CAPTURE",
                f"Could not connect to the checkout endpoint: {str(e)}. Gateway results from homepage/shop "
                "pages alone may be incomplete or inaccurate.")

    # Determine final detected gateways set.
    # Set to input fields exclusively if found (to avoid false positive dependency script matches).
    # Otherwise fall back to script signature matches.
    if input_gateways:
        detected_gateways = input_gateways
    else:
        detected_gateways = script_gateways

    # If gateways are detected but WooCommerce wasn't explicitly flagged, check for WP clues
    if len(detected_gateways) > 0 and not is_wooc:
        if 'wp-content' in homepage_html:
            is_wooc = True
            confidence = "Medium"
            reasons.append("Detected WP structure with active gateway script references")

    # Format platform result
    platform_name = "WooCommerce" if is_wooc else "Not Detected"

    # Map slugs to rich display items
    gateway_list = []
    signatures = load_signatures()
    for slug in detected_gateways:
        if slug in signatures:
            gateway_list.append({
                "slug": slug,
                "name": signatures[slug].get("name", slug)
            })
        else:
            # Fallback for dynamic/unregistered slugs
            gateway_list.append({
                "slug": slug,
                "name": slug.upper() if len(slug) <= 4 else slug.capitalize()
            })

    # If WooCommerce is not detected, clear gateways to remain accurate
    if not is_wooc:
        confidence = "Low"
        gateway_list = []

    # If checkout could not be scanned, gateways from homepage/shop alone are unreliable — clear them
    if not checkout_scanned:
        confidence = "Low"
        gateway_list = []
        reasons.append("Checkout page was not successfully scanned — gateway detection is limited to homepage/shop scripts only")
        if is_wooc and not quiet:
            print_error_banner("PAYMENT METHOD FAILED TO CAPTURE",
                "WooCommerce was detected but the checkout page could not be accessed. Payment gateway "
                "detection requires the checkout page — results from homepage scripts alone cannot be trusted and have been discarded.")
    elif is_wooc and len(gateway_list) == 0 and not quiet:
        print_error_banner("PAYMENT METHOD FAILED TO CAPTURE",
            "WooCommerce was detected on this store and the checkout page was successfully loaded, "
            "but no payment gateway signatures were found. Possible causes: custom/obfuscated gateway scripts, "
            "gateway loaded via deferred JS not present in initial HTML, or all payment methods are currently disabled.")

    return {
        "status": "complete",
        "url": homepage_url,
        "platform": platform_name,
        "confidence": confidence,
        "detected_gateways": gateway_list,
        "raw_slugs": [g["slug"] for g in gateway_list],
        "cloudflare": cloudflare,
        "captcha": captcha,
        "country": country,
        "reasons": list(set(reasons))
    }

# --- MAIN CLI RUNNER ---
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="WooCommerce Payment Gateway Checker (WOOC)")
    parser.add_argument("url", nargs="?", help="The target store URL to analyze (e.g., https://example.com).")
    parser.add_argument("--json", action="store_true", help="Output raw JSON results only (ideal for scripts/piping).")
    parser.add_argument("--slugs", action="store_true", help="Output detected gateway slugs as a JSON array only.")
    
    args = parser.parse_args()

    # Determine quiet mode
    quiet_mode = args.json or args.slugs

    # ASCII Banner
    BANNER = rf"""{Colors.CYAN}
 __      __   ______     ______     ______        ______  __  __  ______  ______  __  __  ______  ______    
/\ \  __/\ \ /\  __ \   /\  __ \   /\  ___\      /\  ___//\ \_\ \/\  ___//\  ___//\ \/ / /\  ___//\  == \   
\ \ \/\ \ \ \\ \ \/\ \  \ \ \/\ \  \ \ \____     \ \ \___\ \  __ \ \  __\ \ \____\ \  _"-.\ \  __\ \  __<   
 \ \__/\ \__/ \ \_____\  \ \_____\  \ \_____\     \ \_____\ \_\ \_\ \_____\ \_____\ \_\ \_\\ \_____\ \_\ \_\ 
  \/_/  \/_/   \/_____/   \/_____/   \/_____/      \/_____/\/_/\/_/\/_____/\/_____/\/_/\/_/ \/_____/\/_/ /_/ 
{Colors.ENDC}
                    {Colors.BOLD}{Colors.HEADER}🐕 WooCommerce Payment Gateway Checker {Colors.ENDC}{Colors.CYAN}(WOOC-CLI){Colors.ENDC}
    """

    if not args.url:
        # URL argument was not supplied, display help banner and usage instructions
        print(BANNER)
        print(f"{Colors.WARNING}Error: Missing target URL.{Colors.ENDC}\n")
        print("Usage:")
        print("  python wooc.py <url>          Run standard visual scan")
        print("  python wooc.py <url> --json   Output scan results in raw JSON format")
        print("  python wooc.py <url> --slugs  Output detected gateway slugs as a JSON array")
        print("\nExamples:")
        print("  python wooc.py https://jingojump.com")
        print("  python wooc.py https://jingojump.com --json")
        sys.exit(1)

    target_url = args.url.strip()

    if not quiet_mode:
        print(BANNER)
        print(f"  {Colors.BOLD}Starting scan on:{Colors.ENDC} {target_url}")
        print("="*75)

    # Perform Scan
    result = perform_website_scan(target_url, quiet=quiet_mode)

    if args.json:
        # Print pure, parseable JSON
        print(json.dumps(result, indent=2))
    elif args.slugs:
        # Print pure raw slugs as a JSON array
        slugs = result.get("raw_slugs", []) if result.get("status") == "complete" else []
        print(json.dumps(slugs))
    else:
        # Beautifully formatted text report
        print("="*75)
        print(f"                       {Colors.BOLD}{Colors.HEADER}🔍 WOOC SCAN REPORT{Colors.ENDC}")
        print("="*75)
        
        if result.get("status") == "error":
            print(f"  {Colors.BOLD}Scan Status:{Colors.ENDC}      {Colors.FAIL}FAILED{Colors.ENDC}")
            print(f"  {Colors.BOLD}Target URL:{Colors.ENDC}       {result.get('url')}")
            print(f"  {Colors.BOLD}Error Details:{Colors.ENDC}    {Colors.FAIL}{result.get('error')}{Colors.ENDC}")
        else:
            platform = result.get("platform")
            confidence = result.get("confidence")
            
            # Platform Color styling
            p_color = Colors.GREEN if platform == "WooCommerce" else Colors.FAIL
            
            # Confidence Color styling
            c_color = Colors.GREEN if confidence == "High" else (Colors.WARNING if confidence == "Medium" else Colors.FAIL)

            print(f"  {Colors.BOLD}Target URL:{Colors.ENDC}       {result.get('url')}")
            print(f"  {Colors.BOLD}Platform:{Colors.ENDC}         {p_color}{Colors.BOLD}{platform}{Colors.ENDC}")
            print(f"  {Colors.BOLD}Confidence Score:{Colors.ENDC} {c_color}{Colors.BOLD}{confidence}{Colors.ENDC}")
            print(f"  {Colors.BOLD}Country 🌎:{Colors.ENDC}       {result.get('country')}")
            print(f"  {Colors.BOLD}Captcha 🔄:{Colors.ENDC}       {result.get('captcha')}")
            print(f"  {Colors.BOLD}Cloudflare ☁️:{Colors.ENDC}     {result.get('cloudflare')}")
            print("-"*75)
            
            # Active Gateways
            print(f"  {Colors.BOLD}{Colors.CYAN}💳 DETECTED PAYMENT GATEWAYS:{Colors.ENDC}")
            gateways = result.get("detected_gateways", [])
            if gateways:
                for gw in gateways:
                    print(f"   {Colors.GREEN}•{Colors.ENDC} {Colors.BOLD}{gw['name']}{Colors.ENDC} (Slug: {Colors.BLUE}{gw['slug']}{Colors.ENDC})")
            else:
                print(f"   {Colors.WARNING}No active payment gateways detected or store is not WooCommerce.{Colors.ENDC}")
            
            print("-"*75)
            
            # Detection Evidence
            print(f"  {Colors.BOLD}{Colors.CYAN}📝 EVIDENCE / DETECTION CLUES:{Colors.ENDC}")
            reasons = result.get("reasons", [])
            if reasons:
                for reason in reasons:
                    print(f"   {Colors.BLUE}-{Colors.ENDC} {reason}")
            else:
                print(f"   No specific WooCommerce clues found.")
                
        print("="*75)
        print(f"  Report generated on terminal. Run with {Colors.BOLD}--json{Colors.ENDC} to get parseable API output.")
        print("="*75 + "\n")
