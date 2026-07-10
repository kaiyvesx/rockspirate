# Rockspirate

Rockspirate is a WooCommerce scanner and detection tool. It provides a Command Line Interface (CLI) and enhanced FastAPI applications for scanning and detecting WooCommerce websites, identifying installed payment gateways, and verifying checkout functionality.

## Features

- **WooCommerce Detection**: Accurately detects WooCommerce installations on target websites.
- **Payment Gateway Scanning**: Uses dynamic signatures (`signatures.json`) to scan for active payment gateways (e.g., Stripe, PayPal, Braintree).
- **Checkout Verification**: Simulates adding products to the cart to verify the checkout process.
- **API Access**: Provides robust FastAPI endpoints (`dork.py` and `woocc.py`) to access detection logic via REST API.
- **Resilient Requests**: Built-in support for rotating user-agents and handling resilient sessions for improved scanning reliability.

## Project Structure

- `wooc.py` - Core CLI tool for running website scans and detecting WooCommerce and payment gateways.
- `dork.py` - Enhanced FastAPI wrapper with background task handling and self-learning user agents.
- `woocc.py` - Clean FastAPI wrapper with improved country detection for API-driven scans.
- `signatures.json` - Configurable payment gateway signatures.
- `requirements.txt` - Project dependencies.

## Installation

1. Ensure you have Python 3.11+ installed.
2. Clone the repository if you haven't already:
   ```bash
   git clone https://github.com/kaiyvesx/rockspirate
   cd rockspirate
   ```
3. Install the required dependencies using pip:
   ```bash
   pip install -r requirements.txt
   ```

## Usage

### CLI Scanner

You can run the core scanning logic via the CLI script. Run the help command to see available options:

```bash
python wooc.py --help
```

### FastAPI Servers

To start the API server, you can run one of the FastAPI wrappers using `uvicorn`:

```bash
# Using the clean API version
uvicorn woocc:app --reload

# Using the enhanced API version
uvicorn dork:app --reload
```

The API will be accessible at `http://127.0.0.1:8000`. You can visit `http://127.0.0.1:8000/docs` to view the interactive API documentation (Swagger UI).
