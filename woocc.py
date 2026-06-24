# wooc_api.py - Clean version with improved country detection

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel, HttpUrl
from typing import List, Optional, Dict, Any
import requests
from bs4 import BeautifulSoup
import urllib3
import json
import re
import socket
import os
import asyncio
import time
from urllib.parse import urljoin, urlparse
from datetime import datetime

# Disable SSL verification warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# ─── DYNAMIC SIGNATURES LOADER ──────────────────────────────────────

SIGNATURES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'signatures.json')

def load_signatures():
    """Loads payment gateway signatures from the signatures.json file."""
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

# ─── RESILIENT HTTP SESSION ─────────────────────────────────────────

try:
    from curl_cffi import requests as _cffi_requests
    _HAS_CURL_CFFI = True
except Exception:
    _HAS_CURL_CFFI = False

class ResilientSession:
    """Drop-in replacement for requests.Session with curl_cffi fallback."""
    
    def __init__(self):
        self._session = requests.Session()
        self._cffi = _cffi_requests.Session(impersonate="chrome") if _HAS_CURL_CFFI else None
        self.headers = self._session.headers

    def _looks_like_tls_error(self, err):
        msg = str(err).lower()
        tls_markers = [
            'ssl', 'tls', 'tlsv1', 'handshake', 'sslv3', 'connection aborted',
            'max retries exceeded', 'wrong version number', 'certificate',
        ]
        return any(m in msg for m in tls_markers)

    def get(self, url, **kwargs):
        try:
            return self._session.get(url, **kwargs)
        except Exception as err:
            if not self._cffi or not self._looks_like_tls_error(err):
                raise
            allowed = {k: kwargs[k] for k in ('headers', 'timeout', 'verify', 'allow_redirects', 'params', 'cookies') if k in kwargs}
            try:
                return self._cffi.get(url, **allowed)
            except Exception:
                raise err

    def post(self, url, **kwargs):
        try:
            return self._session.post(url, **kwargs)
        except Exception as err:
            if not self._cffi or not self._looks_like_tls_error(err):
                raise
            allowed = {k: kwargs[k] for k in ('headers', 'timeout', 'verify', 'allow_redirects', 'params', 'cookies', 'data', 'json') if k in kwargs}
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

# ─── SCANNER CORE LOGIC ─────────────────────────────────────────────

def detect_country(domain, soup, url=""):
    """
    Detects the country code using multiple methods.
    Priority: 1. Checkout form, 2. Domain TLD, 3. IP geolocation
    """
    
    # 1. Try to get country from checkout form fields (most accurate)
    try:
        if soup:
            # Check for billing country select
            select = soup.find('select', attrs={'name': 'billing_country'})
            if select:
                selected = select.find('option', selected=True)
                if selected and selected.get('value'):
                    return selected.get('value').upper()
                for opt in select.find_all('option'):
                    if opt.has_attr('selected') and opt.get('value'):
                        return opt.get('value').upper()
            
            # Check for hidden country field
            country_input = soup.find('input', attrs={'name': 'billing_country'})
            if country_input and country_input.get('value'):
                return country_input.get('value').upper()
    except Exception:
        pass

    # 2. Try to detect from domain TLD
    try:
        # Check if domain ends with country-specific TLD
        tld = domain.split('.')[-1].upper()
        # Common country TLDs
        country_tlds = {
            'US': ['US'],
            'UK': ['UK', 'GB'],
            'CA': ['CA'],
            'AU': ['AU'],
            'DE': ['DE'],
            'FR': ['FR'],
            'IT': ['IT'],
            'ES': ['ES'],
            'NL': ['NL'],
            'BR': ['BR'],
            'IN': ['IN'],
            'JP': ['JP'],
            'CN': ['CN'],
            'RU': ['RU'],
            'ZA': ['ZA'],
            'SG': ['SG'],
            'MY': ['MY'],
        }
        for country, tlds in country_tlds.items():
            if tld in tlds:
                return country
    except Exception:
        pass

    # 3. Fallback to IP Geolocation
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
    """Checks if Cloudflare is active on the server response."""
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
    """Detects Captcha indicators."""
    captcha_keywords = ['recaptcha', 'hcaptcha', 'turnstile', 'g-recaptcha', 'cf-turnstile', 'h-captcha']
    html_lower = html_text.lower()
    for kw in captcha_keywords:
        if kw in html_lower:
            return "YES"
    if re.search(r'\bcaptcha\b', html_lower):
        return "YES"
    return "NO"

def detect_woocommerce(soup, html_text):
    """Analyzes content to detect WooCommerce installation."""
    reasons = []
    
    gen_tag = soup.find('meta', attrs={'name': 'generator'})
    if gen_tag and 'woocommerce' in gen_tag.get('content', '').lower():
        reasons.append(f"Generator Meta: {gen_tag.get('content')}")
    
    if '/wp-content/plugins/woocommerce/' in html_text:
        reasons.append("Asset path contains '/wp-content/plugins/woocommerce/'")
    
    body = soup.find('body')
    if body:
        classes = body.get('class', [])
        wc_classes = [c for c in classes if 'woocommerce' in c]
        if wc_classes:
            reasons.append(f"Body Class matches: {', '.join(wc_classes)}")

    wc_js_params = ['wc_add_to_cart_params', 'woocommerce_params', 'wc_cart_fragments_params']
    for param in wc_js_params:
        if param in html_text:
            reasons.append(f"Global JS parameter detected: {param}")
    
    if 'wc-ajax' in html_text or '/?wc-ajax=' in html_text:
        reasons.append("WooCommerce Ajax endpoint 'wc-ajax' found in page contents")

    if len(reasons) >= 2:
        return True, "High", reasons
    elif len(reasons) == 1:
        return True, "Medium", reasons
    
    if 'woocommerce-layout.css' in html_text or 'woocommerce.css' in html_text:
        reasons.append("WooCommerce CSS stylesheet layout loaded")
        return True, "Medium", reasons
        
    return False, "Low", []

def scan_for_gateways(html_text):
    """Scans HTML for payment gateway signatures."""
    detected = set()
    signatures = load_signatures()
    for slug, info in signatures.items():
        for pattern in info.get("patterns", []):
            if pattern.lower() in html_text.lower():
                detected.add(slug)
                break
    return detected

def find_product_id(soup, html_text):
    """Finds a WooCommerce product ID from page elements."""
    match = re.search(r'href=["\'](?:[^"\']*\?|^\?)add-to-cart=(\d+)', html_text)
    if match:
        return match.group(1)
    
    add_to_cart_input = soup.find(attrs={"name": "add-to-cart"})
    if add_to_cart_input:
        val = add_to_cart_input.get('value')
        if val and val.isdigit():
            return val
    
    add_to_cart_btn = soup.find(attrs={"data-product_id": True})
    if add_to_cart_btn:
        val = add_to_cart_btn.get('data-product_id')
        if val and val.isdigit():
            return val
    
    return None

def find_product_link(soup, base_url):
    """Searches for product page links."""
    for a in soup.find_all('a', href=True):
        href = a['href']
        if '/product/' in href:
            return urljoin(base_url, href)
    loop_link = soup.find('a', class_='woocommerce-LoopProduct-link')
    if loop_link and loop_link.get('href'):
        return urljoin(base_url, loop_link.get('href'))
    return None

def attempt_find_product_id_across_pages(session, base_url, headers):
    """Checks Homepage and Shop page for a product ID."""
    try:
        r = session.get(base_url, headers=headers, timeout=10, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            prod_id = find_product_id(soup, r.text)
            if prod_id:
                return prod_id, "Found on Homepage"
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

    shop_url = base_url.rstrip('/') + '/shop/'
    try:
        r = session.get(shop_url, headers=headers, timeout=10, verify=False)
        if r.status_code == 200:
            soup = BeautifulSoup(r.text, 'html.parser')
            prod_id = find_product_id(soup, r.text)
            if prod_id:
                return prod_id, "Found on Shop Page"
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
    """Sends a request to add product to cart."""
    add_url = base_url.rstrip('/') + f"/?add-to-cart={prod_id}"
    try:
        session.get(add_url, headers=headers, timeout=10, verify=False)
        return True, f"Successfully executed add-to-cart query for ID {prod_id}"
    except Exception as e:
        return False, f"Failed to execute add-to-cart: {str(e)}"

# ─── FASTAPI APP ─────────────────────────────────────────────────────

app = FastAPI(
    title="WooCommerce Payment Gateway Checker API",
    description="Detects WooCommerce stores and their payment gateways with cart simulation",
    version="1.0.0"
)

# ─── MODELS ──────────────────────────────────────────────────────────

class ScanRequest(BaseModel):
    urls: List[HttpUrl]
    timeout: Optional[int] = 30

class CleanScanResult(BaseModel):
    url: str
    platform: str
    payment_methods: List[str]
    country: str
    captcha: str
    cloudflare: str
    time_taken: float
    ip: Optional[str] = None

class ScanResponse(BaseModel):
    results: List[CleanScanResult]

# ─── SCAN FUNCTION ──────────────────────────────────────────────────

def perform_scan(url: str, timeout: int = 30) -> Dict[str, Any]:
    """Perform a full website scan and return clean results."""
    
    start_time = time.time()
    
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:115.0) Gecko/20100101 Firefox/115.0',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
    }

    script_gateways = set()
    input_gateways = set()
    is_wooc = False
    confidence = "Low"
    
    parsed_url = urlparse(url)
    domain_name = parsed_url.netloc or url.split('/')[0]
    # Initialize country with IP fallback, will be updated from checkout if available
    country = detect_country(domain_name, None, url)
    cloudflare = "NO"
    captcha = "NO"
    ip_address = None

    # Get IP address
    try:
        ip_address = socket.gethostbyname(domain_name)
    except:
        pass

    session = ResilientSession()
    checkout_scanned = False

    try:
        r = session.get(url, headers=headers, timeout=12, verify=False, allow_redirects=False)
        visited = set()
        max_redirects = 10

        for _ in range(max_redirects):
            if 300 <= r.status_code < 400 and 'Location' in r.headers:
                location = r.headers['Location']
                next_url = urljoin(r.url, location)
                normalized = urlparse(next_url)
                redirect_key = f"{normalized.scheme}://{normalized.netloc}{normalized.path}"
                if redirect_key in visited:
                    r = session.get(next_url, headers=headers, timeout=12, verify=False, allow_redirects=False)
                    break
                visited.add(redirect_key)
                r = session.get(next_url, headers=headers, timeout=12, verify=False, allow_redirects=False)
            else:
                break

        if 300 <= r.status_code < 400:
            raise requests.TooManyRedirects(f"Infinite redirect loop detected after {max_redirects} hops")

        r.raise_for_status()
        homepage_html = r.text
        homepage_url = r.url
        soup_home = BeautifulSoup(homepage_html, 'html.parser')
        
        is_wooc_home, confidence_home, _ = detect_woocommerce(soup_home, homepage_html)
        if is_wooc_home:
            is_wooc = True
            confidence = confidence_home
            
        script_gateways.update(scan_for_gateways(homepage_html))
        cloudflare = detect_cloudflare(r, homepage_html)
        captcha = detect_captcha(homepage_html)

    except Exception as e:
        session.close()
        return {
            "platform": "Unknown",
            "payment_methods": [],
            "country": country,
            "captcha": "NO",
            "cloudflare": "NO",
            "time_taken": time.time() - start_time,
            "ip": ip_address,
            "error": str(e)
        }

    parsed = urlparse(homepage_url)
    base_url = f"{parsed.scheme}://{parsed.netloc}"

    product_id = None
    target_parsed = urlparse(url)
    if '/product/' in target_parsed.path:
        try:
            pr = session.get(url, headers=headers, timeout=12, verify=False)
            if pr.status_code == 200:
                soup_target = BeautifulSoup(pr.text, 'html.parser')
                product_id = find_product_id(soup_target, pr.text)
        except Exception:
            pass

    if not product_id:
        product_id, _ = attempt_find_product_id_across_pages(session, base_url, headers)
    
    if product_id:
        add_product_to_cart(session, base_url, product_id, headers)

    checkout_url = base_url.rstrip('/') + '/checkout/'
    try:
        r = session.get(checkout_url, headers=headers, timeout=12, verify=False)
        if r.status_code == 200:
            checkout_html = r.text
            soup_checkout = BeautifulSoup(checkout_html, 'html.parser')
            checkout_scanned = True
            
            cloudflare = detect_cloudflare(r, checkout_html)
            captcha = detect_captcha(checkout_html)
            
            # Update country from checkout page (more accurate)
            checkout_country = detect_country(domain_name, soup_checkout, url)
            if checkout_country:
                country = checkout_country
            
            checkout_gateways = scan_for_gateways(checkout_html)
            script_gateways.update(checkout_gateways)
            
            inputs = soup_checkout.find_all('input', attrs={'name': 'payment_method'})
            for ip in inputs:
                val = ip.get('value')
                if val:
                    input_gateways.add(val.lower())
    except Exception:
        pass

    session.close()

    # Determine payment methods - KEEP RAW SLUGS
    if input_gateways:
        detected_gateways = input_gateways
    else:
        detected_gateways = script_gateways

    # Return raw slugs exactly as detected
    payment_methods = list(detected_gateways)

    # If not WooCommerce, clear everything
    if not is_wooc:
        payment_methods = []

    if not checkout_scanned:
        payment_methods = []

    return {
        "platform": "WooCommerce" if is_wooc else "Unknown",
        "payment_methods": payment_methods,
        "country": country,
        "captcha": captcha,
        "cloudflare": cloudflare,
        "time_taken": round(time.time() - start_time, 2),
        "ip": ip_address,
        "error": None
    }

# ─── ENDPOINTS ──────────────────────────────────────────────────────

@app.get("/")
def index():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "WooCommerce Payment Gateway Checker API",
        "version": "1.0.0",
        "endpoints": {
            "/scan": "POST - Scan multiple URLs",
            "/scan-live": "POST - Scan with real-time progress",
            "/gateways": "GET - List supported gateways"
        }
    }

@app.post("/scan", response_model=ScanResponse)
def scan_urls(request: ScanRequest):
    """Scan multiple URLs for WooCommerce and payment gateways."""
    results = []
    for url in request.urls:
        result = perform_scan(str(url), timeout=request.timeout)
        results.append(CleanScanResult(
            url=str(url),
            platform=result.get("platform", "Unknown"),
            payment_methods=result.get("payment_methods", []),
            country=result.get("country", "US"),
            captcha=result.get("captcha", "NO"),
            cloudflare=result.get("cloudflare", "NO"),
            time_taken=result.get("time_taken", 0.0),
            ip=result.get("ip")
        ))
    
    return ScanResponse(results=results)

@app.post("/scan-live")
async def scan_urls_live(request: ScanRequest):
    """Scan multiple URLs with real-time progress updates."""
    
    async def generate():
        total = len(request.urls)
        
        yield f"data: {json.dumps({'type': 'start', 'total': total, 'message': f'Starting scan of {total} URLs...'})}\n\n"
        
        for idx, url in enumerate(request.urls, 1):
            result = perform_scan(str(url), timeout=request.timeout)
            
            clean_result = {
                'type': 'progress',
                'current': idx,
                'total': total,
                'url': str(url),
                'platform': result.get('platform', 'Unknown'),
                'payment_methods': result.get('payment_methods', []),
                'country': result.get('country', 'US'),
                'captcha': result.get('captcha', 'NO'),
                'cloudflare': result.get('cloudflare', 'NO'),
                'time_taken': result.get('time_taken', 0.0),
                'ip': result.get('ip')
            }
            
            yield f"data: {json.dumps(clean_result)}\n\n"
            
            await asyncio.sleep(0.1)
        
        yield f"data: {json.dumps({'type': 'complete', 'message': 'All scans completed!'})}\n\n"
    
    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

@app.get("/gateways")
def list_gateways():
    """List all supported payment gateways."""
    signatures = load_signatures()
    return {
        "gateways": [
            {"slug": slug, "name": info.get("name", slug)}
            for slug, info in signatures.items()
        ],
        "count": len(signatures)
    }

# ─── MAIN ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    print("="*60)
    print("🚀 WooCommerce Payment Gateway Checker API")
    print("="*60)
    print("📡 Endpoints:")
    print("   POST /scan       - Scan multiple URLs (clean output)")
    print("   POST /scan-live  - Scan with real-time progress")
    print("   GET  /gateways   - List supported gateways")
    print("="*60)
    print("🌐 Access at: http://127.0.0.1:8000")
    print("📚 Docs at: http://127.0.0.1:8000/docs")
    print("="*60)
    uvicorn.run("woocc:app", host="127.0.0.1", port=8000, reload=True)